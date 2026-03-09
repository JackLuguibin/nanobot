"""State management for the console server.

This module provides a central state manager that bridges the FastAPI backend
with the nanobot core components (AgentLoop, SessionManager, ChannelManager, etc.).

Supports multiple bot instances, each with independent config and workspace.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop
    from nanobot.channels.manager import ChannelManager
    from nanobot.session.manager import SessionManager


def _count_session_messages_from_path(path: Path) -> int:
    """从 session JSONL 文件行数推算消息数（首行为 metadata，其余为消息）。Extension 补丁，不修改 nanobot。"""
    if not path.exists():
        return 0
    try:
        with open(path, encoding="utf-8") as f:
            return max(0, sum(1 for _ in f) - 1)
    except Exception:
        return 0


class BotState:
    """
    Central state manager for a single bot instance.

    Provides a unified interface to access nanobot's core components
    and their current state.
    """

    def __init__(self, bot_id: str = "default"):
        self.bot_id = bot_id
        self._agent_loop: AgentLoop | None = None
        self._session_manager: SessionManager | None = None
        self._channel_manager: ChannelManager | None = None
        self._start_time: float | None = None
        self._config: dict[str, Any] = {}
        self._config_path: Path | None = None
        self._workspace: Path | None = None
        self._messages_today: int = 0
        self._last_reset_date: str = ""
        self._tool_call_logs: list[dict] = []
        self._max_tool_logs: int = 1000
        self._lock = asyncio.Lock()

    def initialize(
        self,
        agent_loop: "AgentLoop | None" = None,
        session_manager: "SessionManager | None" = None,
        channel_manager: "ChannelManager | None" = None,
        config: dict[str, Any] | None = None,
        config_path: Path | None = None,
        workspace: Path | None = None,
    ) -> None:
        """Initialize the state with nanobot core components."""
        self._agent_loop = agent_loop
        self._session_manager = session_manager
        self._channel_manager = channel_manager
        self._config = config or {}
        self._config_path = config_path
        self._workspace = workspace
        self._start_time = time.time()
        self._reset_daily_stats()
        logger.info("BotState initialized for bot '{}'", self.bot_id)

    def _reset_daily_stats(self) -> None:
        """Reset daily message counter if it's a new day."""
        from datetime import date

        today = date.today().isoformat()
        if self._last_reset_date != today:
            self._messages_today = 0
            self._last_reset_date = today

    @property
    def agent_loop(self) -> AgentLoop | None:
        return self._agent_loop

    @property
    def session_manager(self) -> SessionManager | None:
        return self._session_manager

    @property
    def channel_manager(self) -> ChannelManager | None:
        return self._channel_manager

    @property
    def config(self) -> dict[str, Any]:
        return self._config

    @property
    def workspace(self) -> Path | None:
        return self._workspace

    @property
    def config_path(self) -> Path | None:
        return self._config_path

    @property
    def is_running(self) -> bool:
        return (
            self._agent_loop is not None
            and hasattr(self._agent_loop, "is_running")
            and self._agent_loop.is_running
        )

    @property
    def uptime_seconds(self) -> float:
        """Seconds the agent has been running. 0 when agent is not running."""
        if not self.is_running or self._start_time is None:
            return 0.0
        return time.time() - self._start_time

    def increment_messages(self) -> int:
        """Increment and return today's message count."""
        self._reset_daily_stats()
        self._messages_today += 1
        return self._messages_today

    @property
    def messages_today(self) -> int:
        self._reset_daily_stats()
        return self._messages_today

    def add_tool_call_log(self, log: dict) -> None:
        """Add a tool call log entry."""
        self._tool_call_logs.append(log)
        if len(self._tool_call_logs) > self._max_tool_logs:
            self._tool_call_logs = self._tool_call_logs[-self._max_tool_logs :]

    @property
    def tool_call_logs(self) -> list[dict]:
        return self._tool_call_logs.copy()

    async def get_status(self) -> dict[str, Any]:
        """Get comprehensive status information."""
        self._reset_daily_stats()

        channels = []
        ch_dict = getattr(self._channel_manager, "channels", None) or getattr(
            self._channel_manager, "_channels", None
        )
        if self._channel_manager and ch_dict is not None:
            for name, channel in ch_dict.items():
                channels.append(
                    {
                        "name": name,
                        "enabled": True,
                        "status": "online"
                        if hasattr(channel, "_connected") and channel._connected
                        else "offline",
                        "stats": {},
                    }
                )

        mcp_servers = []
        if self._agent_loop and hasattr(self._agent_loop, "_mcp_servers"):
            for name, config in self._agent_loop._mcp_servers.items():
                mcp_servers.append(
                    {
                        "name": name,
                        "status": "connected"
                        if getattr(self._agent_loop, "_mcp_connected", False)
                        else "disconnected",
                        "server_type": "stdio" if "command" in config else "http",
                        "last_connected": None,
                        "error": None,
                    }
                )

        active_sessions = 0
        if self._session_manager and hasattr(self._session_manager, "_cache"):
            active_sessions = len(self._session_manager._cache)

        model = None
        if self._agent_loop and hasattr(self._agent_loop, "model"):
            model = self._agent_loop.model

        return {
            "running": self.is_running,
            "uptime_seconds": self.uptime_seconds,
            "model": model,
            "active_sessions": active_sessions,
            "messages_today": self._messages_today,
            "channels": channels,
            "mcp_servers": mcp_servers,
        }

    async def get_sessions(self) -> list[dict[str, Any]]:
        """Get all sessions: merge in-memory cache with sessions from storage."""
        if not self._session_manager:
            return []

        by_key: dict[str, dict[str, Any]] = {}
        if hasattr(self._session_manager, "list_sessions"):
            try:
                for s in self._session_manager.list_sessions():
                    key = s.get("key", "")
                    if not key:
                        continue
                    msg_count = s.get("message_count")
                    if msg_count is None and s.get("path"):
                        msg_count = _count_session_messages_from_path(Path(s["path"]))
                    by_key[key] = {
                        "key": key,
                        "title": key.split(":")[0] if ":" in key else key,
                        "message_count": msg_count if msg_count is not None else 0,
                        "last_message": None,
                        "created_at": s.get("created_at"),
                        "updated_at": s.get("updated_at"),
                    }
            except Exception:
                pass

        if hasattr(self._session_manager, "_cache"):
            for key, session in self._session_manager._cache.items():
                messages = getattr(session, "messages", [])
                by_key[key] = {
                    "key": key,
                    "title": key.split(":")[0] if ":" in key else key,
                    "message_count": len(messages),
                    "last_message": messages[-1].get("content", "")[:100] if messages else None,
                    "created_at": session.created_at.isoformat()
                    if hasattr(session, "created_at") and session.created_at
                    else None,
                    "updated_at": session.updated_at.isoformat()
                    if hasattr(session, "updated_at") and session.updated_at
                    else None,
                }

        sessions = list(by_key.values())
        sessions.sort(key=lambda s: s.get("updated_at") or "", reverse=True)
        return sessions

    async def get_session(self, key: str) -> dict[str, Any] | None:
        """Get a specific session by key."""
        if not self._session_manager:
            return None

        if hasattr(self._session_manager, "_cache"):
            session = self._session_manager._cache.get(key)
            if session:
                history = session.get_history()
                return {
                    "key": key,
                    "title": key.split(":")[0] if ":" in key else key,
                    "messages": history,
                    "message_count": len(history),
                }

        if hasattr(self._session_manager, "get_or_create"):
            try:
                session = self._session_manager.get_or_create(key)
                history = session.get_history()
                return {
                    "key": key,
                    "title": key.split(":")[0] if ":" in key else key,
                    "messages": history,
                    "message_count": len(history),
                }
            except Exception:
                pass

        return None

    async def create_session(self, key: str | None = None) -> dict[str, Any]:
        """Create a new session."""
        if not self._session_manager:
            raise RuntimeError("Session manager not initialized")

        if key is None:
            import uuid

            key = f"console:{uuid.uuid4().hex[:8]}"

        self._session_manager.get_or_create(key)
        return {
            "key": key,
            "title": key,
            "message_count": 0,
        }

    async def delete_session(self, key: str) -> bool:
        """Delete a session."""
        if not self._session_manager:
            return False

        if hasattr(self._session_manager, "_cache") and key in self._session_manager._cache:
            del self._session_manager._cache[key]
            return True

        if hasattr(self._session_manager, "invalidate"):
            try:
                self._session_manager.invalidate(key)
                return True
            except Exception:
                pass

        return False

    # Known channel types from ChannelsConfig (excluding send_progress, send_tool_hints)
    CHANNEL_NAMES = (
        "whatsapp",
        "telegram",
        "discord",
        "feishu",
        "mochat",
        "dingtalk",
        "email",
        "slack",
        "qq",
        "matrix",
    )

    async def get_channels(self) -> list[dict[str, Any]]:
        """Get channel list from config, merged with runtime status when available."""
        config_channels = self._config.get("channels") or {}
        runtime_by_name: dict[str, dict] = {}

        ch_dict = None
        if self._channel_manager:
            ch_dict = getattr(self._channel_manager, "channels", None) or getattr(
                self._channel_manager, "_channels", None
            )
        if ch_dict is not None:
            for name, ch in ch_dict.items():
                runtime_by_name[name] = {
                    "name": name,
                    "enabled": True,
                    "status": (
                        "online"
                        if hasattr(ch, "_connected") and ch._connected
                        else "offline"
                    ),
                    "stats": {},
                }

        result = []
        for name in self.CHANNEL_NAMES:
            cfg = config_channels.get(name)
            if isinstance(cfg, dict):
                enabled = cfg.get("enabled", False)
            else:
                enabled = False

            if name in runtime_by_name:
                row = dict(runtime_by_name[name])
                row["enabled"] = enabled
            else:
                row = {
                    "name": name,
                    "enabled": enabled,
                    "status": "offline",
                    "stats": {},
                }
            result.append(row)

        return result

    def _deep_merge(self, base: dict, update: dict) -> dict:
        """Deep merge update into base. Mutates base."""
        for k, v in update.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                self._deep_merge(base[k], v)
            else:
                base[k] = v
        return base

    async def update_channel(self, name: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update a single channel config. Deep merges with existing."""
        if name not in self.CHANNEL_NAMES:
            raise ValueError(f"Unknown channel: {name}")

        async with self._lock:
            if "channels" not in self._config:
                self._config["channels"] = {}
            if name not in self._config["channels"]:
                self._config["channels"][name] = {}
            self._deep_merge(self._config["channels"][name], data)

            if self._config_path and self._config_path.exists():
                import json

                try:
                    self._config_path.write_text(
                        json.dumps(self._config, indent=2, ensure_ascii=False)
                    )
                except Exception as e:
                    logger.warning("Failed to write config: {}", e)

            return self._config["channels"][name]

    async def delete_channel(self, name: str) -> bool:
        """Disable a channel (set enabled=False). Returns True if updated."""
        if name not in self.CHANNEL_NAMES:
            return False

        async with self._lock:
            if "channels" not in self._config:
                self._config["channels"] = {}
            if name not in self._config["channels"]:
                self._config["channels"][name] = {}
            self._config["channels"][name]["enabled"] = False

            if self._config_path and self._config_path.exists():
                import json

                try:
                    self._config_path.write_text(
                        json.dumps(self._config, indent=2, ensure_ascii=False)
                    )
                except Exception as e:
                    logger.warning("Failed to write config: {}", e)

            return True

    async def get_config(self) -> dict[str, Any]:
        """Get the current configuration."""
        return self._config

    async def update_config(self, section: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update configuration section."""
        async with self._lock:
            if section not in self._config:
                self._config[section] = {}
            self._config[section].update(data)

            if self._config_path and self._config_path.exists():
                import json

                try:
                    self._config_path.write_text(json.dumps(self._config, indent=2))
                except Exception as e:
                    logger.warning("Failed to write config: {}", e)

            return self._config

    async def get_config_schema(self) -> dict[str, Any]:
        """Get the configuration schema."""
        from nanobot.config.schema import Config

        return Config.model_json_schema()

    async def validate_config(self, data: dict[str, Any]) -> dict[str, Any]:
        """Validate configuration data."""
        from nanobot.config.schema import Config

        try:
            Config(**data)
            return {"valid": True, "errors": []}
        except Exception as e:
            return {"valid": False, "errors": [str(e)]}

    async def stop_current_task(self) -> bool:
        """Stop the currently running task."""
        if not self._agent_loop:
            return False

        if hasattr(self._agent_loop, "_running"):
            self._agent_loop._running = False
            return True

        return False

    async def restart_bot(self) -> bool:
        """Restart the bot (reinitialize components)."""
        logger.warning("Restart requested for bot '{}'", self.bot_id)
        return False


class BotStateManager:
    """Manages multiple BotState instances, one per bot."""

    def __init__(self):
        self._states: dict[str, BotState] = {}
        self._default_bot_id: str | None = None

    @property
    def default_bot_id(self) -> str | None:
        return self._default_bot_id

    @default_bot_id.setter
    def default_bot_id(self, bot_id: str | None) -> None:
        self._default_bot_id = bot_id

    def get_state(self, bot_id: str | None = None) -> BotState:
        """Get BotState for a specific bot. Falls back to default bot."""
        bid = bot_id or self._default_bot_id
        if bid and bid in self._states:
            return self._states[bid]
        if self._states:
            return next(iter(self._states.values()))
        state = BotState("_empty")
        return state

    def set_state(self, bot_id: str, state: BotState) -> None:
        self._states[bot_id] = state

    def remove_state(self, bot_id: str) -> BotState | None:
        return self._states.pop(bot_id, None)

    def has_state(self, bot_id: str) -> bool:
        return bot_id in self._states

    def all_bot_ids(self) -> list[str]:
        return list(self._states.keys())

    def all_states(self) -> dict[str, BotState]:
        return dict(self._states)


# Global state manager
_manager: BotStateManager | None = None


def get_state_manager() -> BotStateManager:
    """Get the global BotStateManager."""
    global _manager
    if _manager is None:
        _manager = BotStateManager()
    return _manager


def get_state(bot_id: str | None = None) -> BotState:
    """Convenience: get BotState for a bot (backward-compatible)."""
    return get_state_manager().get_state(bot_id)

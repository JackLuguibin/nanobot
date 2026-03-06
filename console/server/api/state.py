"""State management for the console server.

This module provides a central state manager that bridges the FastAPI backend
with the nanobot core components (AgentLoop, SessionManager, ChannelManager, etc.).
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop
    from nanobot.session.manager import SessionManager
    from nanobot.channels.manager import ChannelManager


class BotState:
    """
    Central state manager for the console.
    
    Provides a unified interface to access nanobot's core components
    and their current state.
    """
    
    def __init__(self):
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
        logger.info("BotState initialized successfully")
    
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
    def is_running(self) -> bool:
        return self._agent_loop is not None and hasattr(self._agent_loop, 'is_running') and self._agent_loop.is_running
    
    @property
    def uptime_seconds(self) -> float:
        if self._start_time is None:
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
        # Trim if exceeds max
        if len(self._tool_call_logs) > self._max_tool_logs:
            self._tool_call_logs = self._tool_call_logs[-self._max_tool_logs:]
    
    @property
    def tool_call_logs(self) -> list[dict]:
        return self._tool_call_logs.copy()
    
    async def get_status(self) -> dict[str, Any]:
        """Get comprehensive status information."""
        self._reset_daily_stats()
        
        # Get channel statuses
        channels = []
        if self._channel_manager and hasattr(self._channel_manager, '_channels'):
            for name, channel in self._channel_manager._channels.items():
                channels.append({
                    "name": name,
                    "enabled": True,
                    "status": "online" if hasattr(channel, '_connected') and channel._connected else "offline",
                    "stats": {},
                })
        
        # Get MCP server statuses
        mcp_servers = []
        if self._agent_loop and hasattr(self._agent_loop, '_mcp_servers'):
            for name, config in self._agent_loop._mcp_servers.items():
                mcp_servers.append({
                    "name": name,
                    "status": "connected" if getattr(self._agent_loop, '_mcp_connected', False) else "disconnected",
                    "server_type": "stdio" if "command" in config else "http",
                    "last_connected": None,
                    "error": None,
                })
        
        # Get active sessions
        active_sessions = 0
        if self._session_manager and hasattr(self._session_manager, '_cache'):
            active_sessions = len(self._session_manager._cache)
        
        model = None
        if self._agent_loop and hasattr(self._agent_loop, 'model'):
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
        """Get all sessions."""
        if not self._session_manager:
            return []
        
        sessions = []
        
        # Get sessions from the cache
        if hasattr(self._session_manager, '_cache'):
            for key, session in self._session_manager._cache.items():
                history = session.get_history()
                sessions.append({
                    "key": key,
                    "title": key.split(":")[0] if ":" in key else key,
                    "message_count": len(history),
                    "last_message": history[-1].get("content", "")[:100] if history else None,
                    "created_at": session.created_at.isoformat() if hasattr(session, 'created_at') and session.created_at else None,
                    "updated_at": session.updated_at.isoformat() if hasattr(session, 'updated_at') and session.updated_at else None,
                })
        
        # If no sessions in cache, try to list from storage
        if not sessions and hasattr(self._session_manager, 'list_sessions'):
            try:
                stored_sessions = self._session_manager.list_sessions()
                for s in stored_sessions:
                    sessions.append({
                        "key": s.get("key", ""),
                        "title": s.get("key", "").split(":")[0] if ":" in s.get("key", "") else s.get("key", ""),
                        "message_count": s.get("message_count", 0),
                        "last_message": None,
                        "created_at": s.get("created_at"),
                        "updated_at": s.get("updated_at"),
                    })
            except Exception:
                pass
        
        # Sort by updated_at descending
        sessions.sort(key=lambda s: s.get("updated_at") or "", reverse=True)
        return sessions
    
    async def get_session(self, key: str) -> dict[str, Any] | None:
        """Get a specific session by key."""
        if not self._session_manager:
            return None
        
        # Try to get from in-memory cache first
        if hasattr(self._session_manager, '_cache'):
            session = self._session_manager._cache.get(key)
            if session:
                history = session.get_history()
                return {
                    "key": key,
                    "title": key.split(":")[0] if ":" in key else key,
                    "messages": history,
                    "message_count": len(history),
                }
        
        # Try to load from storage using get_or_create
        if hasattr(self._session_manager, 'get_or_create'):
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
        
        # Generate key if not provided
        if key is None:
            import uuid
            key = f"console:{uuid.uuid4().hex[:8]}"
        
        session = self._session_manager.get_or_create(key)
        return {
            "key": key,
            "title": key,
            "message_count": 0,
        }
    
    async def delete_session(self, key: str) -> bool:
        """Delete a session."""
        if not self._session_manager:
            return False
        
        # Try to delete from in-memory cache
        if hasattr(self._session_manager, '_cache') and key in self._session_manager._cache:
            del self._session_manager._cache[key]
            return True
        
        # Try to invalidate from storage
        if hasattr(self._session_manager, 'invalidate'):
            try:
                self._session_manager.invalidate(key)
                return True
            except Exception:
                pass
        
        return False
    
    async def get_config(self) -> dict[str, Any]:
        """Get the current configuration."""
        return self._config
    
    async def update_config(self, section: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update configuration section."""
        async with self._lock:
            # Update in-memory config
            if section not in self._config:
                self._config[section] = {}
            self._config[section].update(data)
            
            # Write to disk
            if self._config_path and self._config_path.exists():
                import json
                try:
                    self._config_path.write_text(json.dumps(self._config, indent=2))
                except Exception as e:
                    logger.warning("Failed to write config: {}", e)
            
            return self._config
    
    async def get_config_schema(self) -> dict[str, Any]:
        """Get the configuration schema."""
        from nanobot.config.schema import ConfigSchema
        return ConfigSchema.model_json_schema()
    
    async def validate_config(self, data: dict[str, Any]) -> dict[str, Any]:
        """Validate configuration data."""
        from nanobot.config.schema import ConfigSchema
        try:
            ConfigSchema(**data)
            return {"valid": True, "errors": []}
        except Exception as e:
            return {"valid": False, "errors": [str(e)]}
    
    async def stop_current_task(self) -> bool:
        """Stop the currently running task."""
        if not self._agent_loop:
            return False
        
        # Try to stop the agent loop
        if hasattr(self._agent_loop, '_running'):
            self._agent_loop._running = False
            return True
        
        return False
    
    async def restart_bot(self) -> bool:
        """Restart the bot (reinitialize components)."""
        logger.warning("Restart requested")
        # Full restart would require:
        # 1. Stop current agent loop
        # 2. Close MCP connections
        # 3. Reinitialize all components
        # For now, return False as full restart is complex
        return False


# Global state instance
_state: BotState | None = None


def get_state() -> BotState:
    """Get the global state instance."""
    global _state
    if _state is None:
        _state = BotState()
    return _state

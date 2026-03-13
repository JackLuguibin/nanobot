"""Bot registry for managing multiple nanobot instances with independent workspaces."""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


@dataclass
class BotInfo:
    id: str
    name: str
    config_path: str
    workspace_path: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "config_path": self.config_path,
            "workspace_path": self.workspace_path,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BotInfo:
        return cls(
            id=data["id"],
            name=data["name"],
            config_path=data["config_path"],
            workspace_path=data["workspace_path"],
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )


class BotRegistry:
    """Manages the bot registry stored in ~/.nanobot/bots/bots.json."""

    def __init__(self, base_dir: Path | None = None):
        self._base_dir = base_dir or (Path.home() / ".nanobot")
        self._bots_dir = self._base_dir / "bots"
        self._registry_path = self._bots_dir / "bots.json"
        self._data: dict[str, Any] = {"default_bot_id": None, "bots": []}
        self._load()

    def _load(self) -> None:
        if self._registry_path.exists():
            try:
                with open(self._registry_path, encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load bot registry: {}", e)
                self._data = {"default_bot_id": None, "bots": []}

    def _save(self) -> None:
        self._bots_dir.mkdir(parents=True, exist_ok=True)
        with open(self._registry_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    @property
    def default_bot_id(self) -> str | None:
        return self._data.get("default_bot_id")

    @default_bot_id.setter
    def default_bot_id(self, bot_id: str | None) -> None:
        self._data["default_bot_id"] = bot_id
        self._save()

    def list_bots(self) -> list[BotInfo]:
        return [BotInfo.from_dict(b) for b in self._data.get("bots", [])]

    def get_bot(self, bot_id: str) -> BotInfo | None:
        for b in self._data.get("bots", []):
            if b["id"] == bot_id:
                return BotInfo.from_dict(b)
        return None

    def get_bot_dir(self, bot_id: str) -> Path:
        return self._bots_dir / bot_id

    def create_bot(self, name: str, source_config: dict[str, Any] | None = None) -> BotInfo:
        """Create a new bot with its own config and workspace directory.

        Args:
            name: Human-readable bot name.
            source_config: Optional config dict to use as template.
                           If None, a default config is generated.
        """
        from nanobot.config.loader import save_config
        from nanobot.config.schema import Config
        from nanobot.utils.helpers import sync_workspace_templates

        bot_id = uuid.uuid4().hex[:12]
        bot_dir = self.get_bot_dir(bot_id)
        workspace_dir = bot_dir / "workspace"
        config_file = bot_dir / "config.json"

        bot_dir.mkdir(parents=True, exist_ok=True)
        workspace_dir.mkdir(parents=True, exist_ok=True)

        if source_config:
            config = Config.model_validate(source_config)
        else:
            config = Config()

        config.agents.defaults.workspace = str(workspace_dir)

        save_config(config, config_file)
        sync_workspace_templates(workspace_dir, silent=True)

        now = datetime.now().isoformat()
        info = BotInfo(
            id=bot_id,
            name=name,
            config_path=str(config_file),
            workspace_path=str(workspace_dir),
            created_at=now,
            updated_at=now,
        )

        self._data.setdefault("bots", []).append(info.to_dict())
        if self._data.get("default_bot_id") is None:
            self._data["default_bot_id"] = bot_id
        self._save()

        logger.info("Created bot '{}' (id={})", name, bot_id)
        return info

    def delete_bot(self, bot_id: str) -> bool:
        """Delete a bot and its directory."""
        bots = self._data.get("bots", [])
        original_len = len(bots)
        self._data["bots"] = [b for b in bots if b["id"] != bot_id]

        if len(self._data["bots"]) == original_len:
            return False

        if self._data.get("default_bot_id") == bot_id:
            self._data["default_bot_id"] = (
                self._data["bots"][0]["id"] if self._data["bots"] else None
            )

        bot_dir = self.get_bot_dir(bot_id)
        if bot_dir.exists():
            try:
                shutil.rmtree(bot_dir)
            except OSError as e:
                logger.warning("Failed to remove bot directory {}: {}", bot_dir, e)

        self._save()
        logger.info("Deleted bot {}", bot_id)
        return True

    def update_bot(self, bot_id: str, **kwargs: Any) -> BotInfo | None:
        """Update bot metadata (name, etc.)."""
        for b in self._data.get("bots", []):
            if b["id"] == bot_id:
                for k, v in kwargs.items():
                    if k in ("name",):
                        b[k] = v
                b["updated_at"] = datetime.now().isoformat()
                self._save()
                return BotInfo.from_dict(b)
        return None

    def set_default(self, bot_id: str) -> bool:
        if self.get_bot(bot_id) is None:
            return False
        self.default_bot_id = bot_id
        return True

    def needs_migration(self) -> bool:
        """Check if we need to migrate from the legacy single-bot config."""
        legacy_config = self._base_dir / "config.json"
        return legacy_config.exists() and not self._registry_path.exists()

    def migrate_legacy(self) -> BotInfo | None:
        """Migrate the legacy ~/.nanobot/config.json into a default bot."""
        legacy_config = self._base_dir / "config.json"
        if not legacy_config.exists():
            return None

        try:
            with open(legacy_config, encoding="utf-8") as f:
                config_data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read legacy config for migration: {}", e)
            return None

        legacy_workspace = Path(
            config_data.get("agents", {}).get("defaults", {}).get("workspace", "~/.nanobot/workspace")
        ).expanduser()

        bot_id = "default"
        bot_dir = self.get_bot_dir(bot_id)
        config_file = bot_dir / "config.json"
        workspace_dir = bot_dir / "workspace"

        bot_dir.mkdir(parents=True, exist_ok=True)

        if legacy_workspace.exists() and not workspace_dir.exists():
            try:
                shutil.copytree(str(legacy_workspace), str(workspace_dir))
            except OSError:
                workspace_dir.mkdir(parents=True, exist_ok=True)
        else:
            workspace_dir.mkdir(parents=True, exist_ok=True)

        config_data.setdefault("agents", {}).setdefault("defaults", {})["workspace"] = str(workspace_dir)

        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)

        now = datetime.now().isoformat()
        info = BotInfo(
            id=bot_id,
            name="Default Bot",
            config_path=str(config_file),
            workspace_path=str(workspace_dir),
            created_at=now,
            updated_at=now,
        )

        self._data = {
            "default_bot_id": bot_id,
            "bots": [info.to_dict()],
        }
        self._save()

        logger.info("Migrated legacy config to default bot")
        return info


_registry: BotRegistry | None = None


def get_registry() -> BotRegistry:
    global _registry
    if _registry is None:
        _registry = BotRegistry()
    return _registry

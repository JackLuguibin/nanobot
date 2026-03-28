"""
facade/config/loader.py - 统一配置加载接口

职责：
- 从配置文件路径加载配置
- 执行配置迁移（兼容旧格式）
- 验证配置 Schema
- 提供配置备份与恢复
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.config.loader import _migrate_config as _nanobot_migrate
from nanobot.config.schema import Config


# ---------------------------------------------------------------------------
# 兼容迁移
# ---------------------------------------------------------------------------


def _migrate_provider_keys(data: dict) -> dict:
    """将 providers 下的键统一为小写（如 OpenAI -> openai），避免 schema 不匹配。"""
    providers = data.get("providers") or data.get("Providers")
    if not isinstance(providers, dict):
        return data
    normalized = {}
    for k, v in providers.items():
        if isinstance(v, dict):
            normalized[k.lower()] = v
        else:
            normalized[k.lower()] = v
    data["providers"] = normalized
    if "Providers" in data:
        del data["Providers"]
    return data


def _ensure_agents_defaults(data: dict) -> dict:
    """确保 agents.defaults 存在，避免因缺少顶层结构导致验证失败。"""
    if "agents" not in data and "Agents" not in data:
        data["agents"] = {"defaults": {}}
        return data
    agents = data.get("agents") or data.get("Agents") or {}
    if "defaults" not in agents and "Defaults" not in agents:
        agents["defaults"] = agents.get("defaults") or agents.get("Defaults") or {}
    data["agents"] = agents
    if "Agents" in data:
        del data["Agents"]
    return data


def _apply_migrations(data: dict) -> dict:
    """依次执行所有迁移规则。"""
    data = _nanobot_migrate(data)
    data = _migrate_provider_keys(data)
    data = _ensure_agents_defaults(data)
    return data


# ---------------------------------------------------------------------------
# 配置加载器
# ---------------------------------------------------------------------------


class ConfigLoader:
    """
    统一配置加载接口。

    设计原则：
    - 配置文件不存在时抛出 FileNotFoundError（上层区分「缺失」与「错误」）
    - 执行配置迁移后验证 Schema，失败时抛出并带清晰错误
    - 不修改 nanobot 源码，仅读取配置
    """

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self._raw_cache: dict[str, Any] | None = None
        self._cache_time: float = 0.0

    def exists(self) -> bool:
        """检查配置文件是否存在。"""
        return self.config_path.exists()

    def load_raw(self) -> dict[str, Any]:
        """
        加载原始 JSON 配置（不验证）。
        异常：FileNotFoundError, json.JSONDecodeError, OSError
        """
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read config as JSON from {}: {}", self.config_path, e)
            raise

    def load(self) -> Config:
        """
        加载并验证配置。
        执行迁移 → 验证 Schema → 返回 Config 对象。
        异常：FileNotFoundError, json.JSONDecodeError, ValidationError
        """
        raw = self.load_raw()
        if not isinstance(raw, dict):
            raise ValueError(f"Config root must be a JSON object, got {type(raw).__name__}")

        raw = _apply_migrations(raw)
        validate_payload = {k: v for k, v in raw.items() if k != "skills"}
        try:
            return Config.model_validate(validate_payload)
        except Exception as e:
            logger.warning(
                "Config validation failed at {} (schema/format may have changed): {}",
                self.config_path,
                e,
            )
            raise

    def load_dict(self) -> dict[str, Any]:
        """加载配置为字典（不含 skills，适配 nanobot Schema）。"""
        raw = self.load_raw()
        return {k: v for k, v in raw.items() if k != "skills"}

    def save(self, data: dict[str, Any]) -> None:
        """
        保存配置到文件。
        写入前先备份，支持 skills 字段透传。
        """
        self._backup()
        # 加载当前 raw（保留 skills 等 nanobot Schema 不包含的字段）
        current_raw = self.load_raw() if self.exists() else {}
        merged = {**current_raw, **data}
        self.config_path.write_text(
            json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self._raw_cache = None  # invalidate cache

    def _backup(self) -> None:
        """创建带时间戳的备份文件。"""
        if not self.config_path.exists():
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.config_path.parent / f"{self.config_path.stem}.backup.{ts}.json"
        shutil.copy2(self.config_path, backup_path)
        # 只保留最近 5 个备份
        backups = sorted(
            self.config_path.parent.glob(f"{self.config_path.stem}.backup.*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        for old in backups[:-5]:
            old.unlink(missing_ok=True)

    def restore_backup(self, backup_path: Path) -> None:
        """从备份文件恢复配置。"""
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")
        shutil.copy2(backup_path, self.config_path)
        self._raw_cache = None

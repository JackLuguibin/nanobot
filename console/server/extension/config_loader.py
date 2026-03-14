"""Console 层配置加载：兼容旧格式、统一键名，便于排查 config 读取问题。"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from nanobot.config.loader import _migrate_config
from nanobot.config.schema import Config


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


def load_bot_config(config_path: Path) -> Config:
    """
    加载 bot 配置文件，并做 console 侧兼容迁移。

    - 配置文件不存在时抛出 FileNotFoundError（便于上层区分「文件缺失」与「格式错误」）。
    - 先做 nanobot 的 _migrate_config，再做 providers 键名归一化、agents.defaults 补全。
    - 验证失败时抛出并带清晰错误信息，便于排查 config 格式/ schema 变化。
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read config as JSON from {}: {}", config_path, e)
        raise

    if not isinstance(raw, dict):
        raise ValueError(f"Config root must be a JSON object, got {type(raw).__name__}")

    raw = _migrate_config(raw)
    raw = _migrate_provider_keys(raw)
    raw = _ensure_agents_defaults(raw)

    try:
        return Config.model_validate(raw)
    except Exception as e:
        logger.warning(
            "Config validation failed at {} (schema/format may have changed): {}",
            config_path,
            e,
        )
        raise

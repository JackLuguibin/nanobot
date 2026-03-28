"""
facade/config/validator.py - 配置验证规则

职责：
- Schema 验证（Pydantic 模型）
- 业务规则验证（冲突检测、依赖检查）
- 返回结构化错误信息
"""

from __future__ import annotations

from typing import Any

from nanobot.config.schema import Config


class ConfigValidationError(Exception):
    """配置验证失败异常。"""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


class ConfigValidator:
    """
    配置验证器。

    验证流程：
    1. Schema 验证（Pydantic）
    2. 业务规则验证（冲突检测、依赖检查）
    """

    KNOWN_CHANNEL_NAMES = (
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

    def validate(self, data: dict[str, Any]) -> list[str]:
        """
        完整验证配置数据。
        返回错误列表（空 = 验证通过）。
        """
        errors: list[str] = []

        schema_errors = self._validate_schema(data)
        errors.extend(schema_errors)

        if not errors:
            business_errors = self._validate_business_rules(data)
            errors.extend(business_errors)

        return errors

    def _validate_schema(self, data: dict[str, Any]) -> list[str]:
        """Pydantic Schema 验证。"""
        errors: list[str] = []
        try:
            Config(**data)
        except Exception as e:
            errors.append(f"Schema error: {e}")
        return errors

    def _validate_business_rules(self, data: dict[str, Any]) -> list[str]:
        """业务规则验证。"""
        errors: list[str] = []

        # 通道名称白名单
        channels = data.get("channels") or {}
        for name in channels:
            if name not in self.KNOWN_CHANNEL_NAMES and name not in ("send_progress", "send_tool_hints"):
                errors.append(f"Unknown channel type: '{name}'")

        # provider 依赖检查
        agents = data.get("agents", {})
        defaults = agents.get("defaults", {})
        provider = defaults.get("provider", "").lower().strip()
        providers = data.get("providers") or {}
        if provider and provider not in providers:
            errors.append(f"Provider '{provider}' is set as default but not defined in providers")

        # channel 与 provider 冲突
        channel_names = [k for k in channels if k not in ("send_progress", "send_tool_hints")]
        for name in channel_names:
            cfg = channels[name] or {}
            if isinstance(cfg, dict) and cfg.get("enabled"):
                # 某些通道需要特定 provider
                pass  # 扩展规则可在此添加

        # skills 检查（确保 skills 为 list 或 dict）
        skills = data.get("skills")
        if skills is not None and not isinstance(skills, (list, dict)):
            errors.append("'skills' must be a list or dict")

        return errors

    def is_valid(self, data: dict[str, Any]) -> bool:
        """返回验证是否通过。"""
        return len(self.validate(data)) == 0

"""
extension/config_bridge.py - 配置桥接器

Facade 层通过此模块访问 nanobot 配置。
仅读取和写入配置文件，不直接修改 nanobot 运行时状态。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from console.server.facade.config.loader import ConfigLoader
from console.server.facade.config.validator import ConfigValidator
from console.server.facade.config.diff import ConfigDiffCalculator, ConfigDiff

if TYPE_CHECKING:
    from nanobot.config.schema import Config


class ConfigBridge:
    """
    配置桥接器。

    职责：
    - 持有配置路径和加载器
    - 提供只读配置访问（不触发 nanobot 重载）
    - 支持配置变更写入（通过 ConfigLoader.save）
    - 验证和差量计算

    设计原则：
    - 不直接修改 nanobot 运行时状态
    - 配置变更仅写入文件，由 nanobot 自己重载
    """

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self._loader = ConfigLoader(config_path)
        self._validator = ConfigValidator()
        self._diff_calc = ConfigDiffCalculator()

    def exists(self) -> bool:
        """配置文件是否存在。"""
        return self._loader.exists()

    def load_raw(self) -> dict[str, Any]:
        """加载原始字典配置。"""
        return self._loader.load_dict()

    def load(self) -> Config:
        """加载并验证的 Config 对象。"""
        return self._loader.load()

    def validate(self, data: dict[str, Any]) -> list[str]:
        """验证配置数据，返回错误列表。"""
        return self._validator.validate(data)

    def is_valid(self, data: dict[str, Any]) -> bool:
        """配置是否有效。"""
        return self._validator.is_valid(data)

    def calculate_diff(
        self,
        old: dict[str, Any],
        new: dict[str, Any],
    ) -> ConfigDiff:
        """计算两个配置之间的差量。"""
        return self._diff_calc.calculate(old, new)

    def save(self, data: dict[str, Any]) -> None:
        """
        保存配置到文件。
        不修改 nanobot 运行时状态，nanobot 自行重载。
        """
        self._loader.save(data)
        logger.debug("Config saved to {}", self.config_path)

    def save_with_diff(
        self,
        section: str,
        partial: dict[str, Any],
    ) -> ConfigDiff:
        """
        部分更新配置（如只更新 channels.telegram）。
        返回差量信息。
        """
        current = self.load_raw()
        if section not in current:
            current[section] = {}
        current[section].update(partial)

        errors = self.validate(current)
        if errors:
            raise ValueError(f"Config validation failed: {'; '.join(errors)}")

        diff = self.calculate_diff(self.load_raw(), current)
        self._loader.save(current)
        return diff

    def get_schema(self) -> dict[str, Any]:
        """获取配置 Schema。"""
        from nanobot.config.schema import Config
        return Config.model_json_schema()

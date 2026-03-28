"""
facade/skill/manager.py - SkillFacade

Skill 的统一管理接口。
设计原则：
- 仅读取 SkillsLoader 状态，配置变更通过 ConfigBridge
- 提供技能列表、启用/禁用等操作
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from console.server.facade.base import BaseManager, FacadeEvent, FacadeEventType, HealthCheckResult, HealthStatus, OperationResult


class SkillFacade(BaseManager[dict[str, Any]]):
    """
    Skill 统一管理门面。

    职责：
    - 持有 workspace、ConfigBridge 引用
    - 提供技能列表、详情、启用/禁用

    设计原则：
    - 仅读取技能状态
    - 启用/禁用通过配置文件
    """

    def __init__(
        self,
        bot_id: str,
        workspace: Path | None = None,
        config_bridge: Any = None,
    ) -> None:
        super().__init__(bot_id)
        self._workspace = workspace
        self._config_bridge = config_bridge
        self._skills_loader: Any | None = None

    def _ensure_loader(self) -> Any | None:
        """懒加载 SkillsLoader。"""
        if self._skills_loader is not None:
            return self._skills_loader
        if self._workspace is None:
            return None
        try:
            from nanobot.agent.skills import SkillsLoader
            self._skills_loader = SkillsLoader(self._workspace)
            return self._skills_loader
        except Exception as e:
            logger.debug("Failed to initialize SkillsLoader: {}", e)
            return None

    # -------------------------------------------------------------------------
    # 只读操作
    # -------------------------------------------------------------------------

    def list(self) -> list[dict[str, Any]]:
        """列出所有技能。"""
        loader = self._ensure_loader()
        if not loader:
            return []

        try:
            skills = loader.list_skills(filter_unavailable=False)
            enabled_map = self._get_enabled_map()
            result = []
            for s in skills:
                name = s.get("name", "")
                result.append({
                    "name": name,
                    "description": s.get("description", ""),
                    "enabled": enabled_map.get(name, True),
                    "type": s.get("type", "unknown"),
                    "path": s.get("path", ""),
                })
            return result
        except Exception as e:
            logger.debug("Failed to list skills: {}", e)
            return []

    def get(self, identifier: str) -> dict[str, Any] | None:
        """获取指定技能详情。"""
        loader = self._ensure_loader()
        if not loader:
            return None

        try:
            skills = loader.list_skills(filter_unavailable=False)
            skill = next((s for s in skills if s.get("name") == identifier), None)
            if not skill:
                return None

            enabled_map = self._get_enabled_map()
            return {
                "name": identifier,
                "description": skill.get("description", ""),
                "enabled": enabled_map.get(identifier, True),
                "type": skill.get("type", "unknown"),
                "path": skill.get("path", ""),
            }
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # 写操作（配置驱动）
    # -------------------------------------------------------------------------

    async def update(self, identifier: str, data: dict[str, Any]) -> OperationResult:
        """更新技能配置（仅支持 enabled 字段，写入配置文件）。"""
        enabled = data.get("enabled")
        if enabled is None:
            return OperationResult.ok("No changes")

        return await self._set_enabled(identifier, bool(enabled))

    async def delete(self, identifier: str) -> OperationResult:
        """删除技能（从 workspace 中移除文件，不推荐）。"""
        return OperationResult.error("Deleting skills directly is not supported. Disable it instead.")

    async def start(self, identifier: str) -> OperationResult:
        """启用技能。"""
        return await self._set_enabled(identifier, True)

    async def stop(self, identifier: str) -> OperationResult:
        """禁用技能。"""
        return await self._set_enabled(identifier, False)

    # -------------------------------------------------------------------------
    # 健康检查
    # -------------------------------------------------------------------------

    def health_check(self) -> HealthCheckResult:
        """检查技能加载器状态。"""
        loader = self._ensure_loader()
        if not loader:
            return HealthCheckResult.unknown("SkillsLoader not available")

        try:
            skills = loader.list_skills(filter_unavailable=False)
            return HealthCheckResult.healthy(
                f"{len(skills)} skills loaded",
                details={"skill_count": len(skills)}
            )
        except Exception as e:
            return HealthCheckResult.unhealthy(f"Failed to list skills: {e}")

    # -------------------------------------------------------------------------
    # 工具方法
    # -------------------------------------------------------------------------

    def _get_enabled_map(self) -> dict[str, bool]:
        """从配置文件获取技能启用状态。"""
        if not self._config_bridge:
            return {}
        try:
            raw = self._config_bridge.load_raw()
            return raw.get("skills") or {}
        except Exception:
            return {}

    async def _set_enabled(self, identifier: str, enabled: bool) -> OperationResult:
        """设置技能启用状态（写入配置文件）。"""
        if not self._config_bridge:
            return OperationResult.error("ConfigBridge not available")

        try:
            current = self._config_bridge.load_raw()
            skills = current.get("skills") or {}
            if identifier not in skills:
                skills[identifier] = {}
            if isinstance(skills[identifier], dict):
                skills[identifier]["enabled"] = enabled
            else:
                skills[identifier] = {"enabled": enabled}
            current["skills"] = skills

            errors = self._config_bridge.validate(current)
            if errors:
                return OperationResult.error(f"Config validation failed: {'; '.join(errors)}")

            self._config_bridge.save(current)
            self.notify(FacadeEvent(
                type=FacadeEventType.UPDATED,
                resource_type="skill",
                resource_id=identifier,
                bot_id=self.bot_id,
                data={"enabled": enabled},
            ))
            return OperationResult.ok(f"Skill '{identifier}' {'enabled' if enabled else 'disabled'}")
        except Exception as e:
            return OperationResult.error(f"Failed to update skill: {e}")

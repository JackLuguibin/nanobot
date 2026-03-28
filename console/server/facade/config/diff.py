"""
facade/config/diff.py - 配置变更差量计算

职责：
- 计算新旧配置的差量（ConfigDiff）
- 识别变更类型（新增/修改/删除）
- 辅助配置备份与回滚
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DiffAction(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    NONE = "none"


@dataclass
class ConfigDiffEntry:
    """单个配置项的差量。"""
    key: str
    path: str  # JSONPath 形式，如 "channels.telegram"
    action: DiffAction
    old_value: Any = None
    new_value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "path": self.path,
            "action": self.action.value,
            "old_value": self.old_value,
            "new_value": self.new_value,
        }


@dataclass
class ConfigDiff:
    """新旧配置的完整差量。"""
    entries: list[ConfigDiffEntry] = field(default_factory=list)
    old_config: dict[str, Any] | None = None
    new_config: dict[str, Any] | None = None

    def is_empty(self) -> bool:
        return all(e.action == DiffAction.NONE for e in self.entries)

    def has_changes(self) -> bool:
        return not self.is_empty()

    def to_dict(self) -> dict[str, Any]:
        return {
            "entries": [e.to_dict() for e in self.entries],
            "has_changes": self.has_changes(),
        }


class ConfigDiffCalculator:
    """计算两个配置字典之间的差量。"""

    def calculate(self, old: dict[str, Any], new: dict[str, Any]) -> ConfigDiff:
        """
        计算 old -> new 的差量。
        """
        entries: list[ConfigDiffEntry] = []
        self._diff_recursive(old, new, "", entries)
        return ConfigDiff(entries=entries, old_config=old, new_config=new)

    def _diff_recursive(
        self,
        old: Any,
        new: Any,
        path: str,
        entries: list[ConfigDiffEntry],
    ) -> None:
        """递归比较，生成差量条目。"""
        if old == new:
            return

        if isinstance(old, dict) and isinstance(new, dict):
            all_keys = set(old.keys()) | set(new.keys())
            for key in all_keys:
                child_path = f"{path}.{key}" if path else key
                if key not in old:
                    self._add_entry(entries, key, child_path, DiffAction.CREATE, None, new[key])
                elif key not in new:
                    self._add_entry(entries, key, child_path, DiffAction.DELETE, old[key], None)
                else:
                    self._diff_recursive(old[key], new[key], child_path, entries)
        elif isinstance(old, list) and isinstance(new, list):
            if old != new:
                self._add_entry(entries, path, path, DiffAction.UPDATE, old, new)
        else:
            self._add_entry(entries, path, path, DiffAction.UPDATE, old, new)

    def _add_entry(
        self,
        entries: list[ConfigDiffEntry],
        key: str,
        path: str,
        action: DiffAction,
        old_value: Any,
        new_value: Any,
    ) -> None:
        if action == DiffAction.NONE:
            return
        entries.append(ConfigDiffEntry(
            key=key,
            path=path,
            action=action,
            old_value=old_value,
            new_value=new_value,
        ))

"""
gateway/commands.py - Gateway 命令定义

定义通过 Gateway 适配器发送的命令格式。
Gateway 配置下发（通过配置文件变更）不直接调用 Gateway 方法。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class GatewayCommandType(str, Enum):
    START_CHANNEL = "start_channel"
    STOP_CHANNEL = "stop_channel"
    RESTART_CHANNEL = "restart_channel"
    RESTART_ALL = "restart_all"
    STOP_ALL = "stop_all"


@dataclass
class GatewayCommand:
    """Gateway 命令。"""
    type: GatewayCommandType
    channel_name: str | None = None
    data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "channel_name": self.channel_name,
            "data": self.data or {},
        }

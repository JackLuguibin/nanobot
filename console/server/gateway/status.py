"""
gateway/status.py - Gateway 状态映射

Gateway 在实际代码中对应 ChannelManager + MessageBus。
此模块定义 Gateway 相关的状态类型，不直接操作 nanobot。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class GatewayRunState(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass
class GatewayStats:
    """Gateway 运行统计。"""
    inbound_size: int = 0
    outbound_size: int = 0
    total_inbound: int = 0
    total_outbound: int = 0
    channels_online: int = 0
    channels_total: int = 0


@dataclass
class GatewayStatus:
    """Gateway 当前状态。"""
    run_state: GatewayRunState = GatewayRunState.UNKNOWN
    stats: GatewayStats = field(default_factory=GatewayStats)
    message: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_state": self.run_state.value,
            "stats": {
                "inbound_size": self.stats.inbound_size,
                "outbound_size": self.stats.outbound_size,
                "total_inbound": self.stats.total_inbound,
                "total_outbound": self.stats.total_outbound,
                "channels_online": self.stats.channels_online,
                "channels_total": self.stats.channels_total,
            },
            "message": self.message,
            "timestamp": self.timestamp,
        }


def map_channel_manager_status(
    channel_manager: Any,
) -> GatewayStatus:
    """
    从 ChannelManager 映射 Gateway 状态。
    仅读取状态，不修改 nanobot。
    """
    if channel_manager is None:
        return GatewayStatus(run_state=GatewayRunState.UNKNOWN, message="No channel manager")

    channels: dict[str, Any] = getattr(channel_manager, "channels", None) or {}
    bus = getattr(channel_manager, "bus", None)

    inbound_size = 0
    outbound_size = 0
    channels_online = 0

    if bus is not None:
        inbound_size = getattr(bus, "inbound_size", 0)
        outbound_size = getattr(bus, "outbound_size", 0)

    for name, channel in channels.items():
        if getattr(channel, "_connected", False):
            channels_online += 1

    stats = GatewayStats(
        inbound_size=inbound_size,
        outbound_size=outbound_size,
        channels_online=channels_online,
        channels_total=len(channels),
    )

    all_online = channels_online == len(channels) and len(channels) > 0
    run_state = GatewayRunState.RUNNING if all_online else GatewayRunState.STOPPED

    return GatewayStatus(
        run_state=run_state,
        stats=stats,
        message=f"{channels_online}/{len(channels)} channels online",
    )

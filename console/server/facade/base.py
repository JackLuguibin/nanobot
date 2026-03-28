"""
facade/base.py - 基础接口与类型定义

Facade 层所有 Manager 的公共基类和通用数据结构。
遵循设计原则：
- nanobot 核心仅读取，不直接调用
- 仅通过配置驱动与 nanobot 交互
- 所有状态变更通过统一操作结果返回
"""

from __future__ import annotations

import asyncio
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")


# ---------------------------------------------------------------------------
# 操作结果
# ---------------------------------------------------------------------------


class OperationStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    PENDING = "pending"


@dataclass
class OperationResult:
    """统一操作结果，所有 Manager 方法返回此类型"""

    success: bool
    message: str = ""
    data: dict[str, Any] | None = None
    status: OperationStatus = OperationStatus.SUCCESS
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @classmethod
    def ok(cls, message: str = "OK", data: dict[str, Any] | None = None) -> "OperationResult":
        return cls(success=True, message=message, data=data, status=OperationStatus.SUCCESS)

    @classmethod
    def error(cls, message: str, data: dict[str, Any] | None = None) -> "OperationResult":
        return cls(success=False, message=message, data=data, status=OperationStatus.FAILURE)

    @classmethod
    def partial(cls, message: str, data: dict[str, Any] | None = None) -> "OperationResult":
        return cls(success=False, message=message, data=data, status=OperationStatus.PARTIAL)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "data": self.data or {},
            "status": self.status.value,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# 健康检查
# ---------------------------------------------------------------------------


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """健康检查结果"""

    status: HealthStatus
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @classmethod
    def healthy(cls, message: str = "OK", details: dict[str, Any] | None = None) -> "HealthCheckResult":
        return cls(status=HealthStatus.HEALTHY, message=message, details=details or {})

    @classmethod
    def degraded(cls, message: str, details: dict[str, Any] | None = None) -> "HealthCheckResult":
        return cls(status=HealthStatus.DEGRADED, message=message, details=details or {})

    @classmethod
    def unhealthy(cls, message: str, details: dict[str, Any] | None = None) -> "HealthCheckResult":
        return cls(status=HealthStatus.UNHEALTHY, message=message, details=details or {})

    @classmethod
    def unknown(cls, message: str = "Unknown") -> "HealthCheckResult":
        return cls(status=HealthStatus.UNKNOWN, message=message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Facade 事件
# ---------------------------------------------------------------------------


class FacadeEventType(str, Enum):
    STATE_CHANGED = "state_changed"
    HEALTH_CHANGED = "health_changed"
    CONFIG_CHANGED = "config_changed"
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    STARTED = "started"
    STOPPED = "stopped"


@dataclass
class FacadeEvent:
    """统一事件格式"""

    type: FacadeEventType
    resource_type: str
    resource_id: str
    bot_id: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "bot_id": self.bot_id,
            "data": self.data,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# 基础 Manager（所有 Facade Manager 的抽象基类）
# ---------------------------------------------------------------------------


class BaseManager(ABC, Generic[T]):
    """
    所有 Facade Manager 的抽象基类。

    设计原则：
    - bot_id 标识当前管理的 Bot
    - asyncio.Lock 保证并发安全
    - 订阅-通知机制支持状态变化观察
    - health_check 子类必须实现
    - list/get 仅为只读操作，不修改 nanobot 状态
    - create/update/delete/start/stop 为配置驱动操作
    """

    def __init__(self, bot_id: str) -> None:
        self.bot_id = bot_id
        self._lock = asyncio.Lock()
        self._subscribers: list[Callable[[FacadeEvent], None]] = []
        self._initialized = False

    # -------------------------------------------------------------------------
    # 生命周期
    # -------------------------------------------------------------------------

    async def initialize(self) -> None:
        """子类可覆盖以实现初始化逻辑"""
        self._initialized = True

    async def shutdown(self) -> None:
        """子类可覆盖以实现清理逻辑"""
        self._initialized = False

    # -------------------------------------------------------------------------
    # 订阅-通知
    # -------------------------------------------------------------------------

    def subscribe(self, callback: Callable[[FacadeEvent], None]) -> None:
        """注册状态变化监听器"""
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[FacadeEvent], None]) -> None:
        """取消状态变化监听器"""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def notify(self, event: FacadeEvent) -> None:
        """通知所有订阅者"""
        for callback in self._subscribers:
            try:
                callback(event)
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # 通用只读操作（子类可覆盖）
    # -------------------------------------------------------------------------

    @abstractmethod
    def list(self) -> list[dict[str, Any]]:
        """列出所有资源，返回基本信息列表"""
        raise NotImplementedError

    @abstractmethod
    def get(self, identifier: str) -> dict[str, Any] | None:
        """根据标识符获取资源详情"""
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # 通用写操作（子类必须覆盖）
    # -------------------------------------------------------------------------

    @abstractmethod
    async def create(self, data: dict[str, Any]) -> OperationResult:
        raise NotImplementedError

    @abstractmethod
    async def update(self, identifier: str, data: dict[str, Any]) -> OperationResult:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, identifier: str) -> OperationResult:
        raise NotImplementedError

    async def start(self, identifier: str) -> OperationResult:
        """启动资源（可选实现）"""
        return OperationResult.error(f"{self.__class__.__name__} does not support start operation")

    async def stop(self, identifier: str) -> OperationResult:
        """停止资源（可选实现）"""
        return OperationResult.error(f"{self.__class__.__name__} does not support stop operation")

    # -------------------------------------------------------------------------
    # 健康检查
    # -------------------------------------------------------------------------

    @abstractmethod
    def health_check(self) -> HealthCheckResult:
        """检查自身健康状态，子类必须实现"""
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # 工具方法
    # -------------------------------------------------------------------------

    @staticmethod
    def _safe_call(func: Callable[..., T], *args: Any, **kwargs: Any) -> T | None:
        """安全调用函数，捕获异常"""
        try:
            return func(*args, **kwargs)
        except Exception as e:
            traceback.print_exc()
            return None

    async def _safe_async_call(func: Callable[..., Any], *args: Any, **kwargs: Any) -> tuple[bool, Any]:
        """安全异步调用，返回 (success, result_or_error)"""
        try:
            result = await func(*args, **kwargs)
            return True, result
        except Exception as e:
            traceback.print_exc()
            return False, str(e)

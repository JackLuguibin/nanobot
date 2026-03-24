"""ZeroMQ-based Agent message bus for inter-agent and inter-bot communication."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import asdict, dataclass, replace as dataclass_replace
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable

import zmq
import zmq.asyncio
from loguru import logger

if TYPE_CHECKING:
    from console.server.extension.agents import AgentManager


@dataclass
class AgentMessage:
    """Agent间通信消息格式"""

    msg_type: str  # "request", "response", "broadcast", "delegate"
    sender_id: str
    topic: str  # 消息主题
    content: str
    context: dict[str, Any]
    correlation_id: str
    receiver_id: str | None = None  # None表示广播
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if not self.correlation_id:
            self.correlation_id = uuid.uuid4().hex[:8]


# ----------------------------------------------------------------------
# Global singleton
# ----------------------------------------------------------------------


_zero_mq_bus: "ZeroMQBus | None" = None


def get_zmq_bus() -> "ZeroMQBus":
    """Get the global shared ZeroMQBus instance."""
    global _zero_mq_bus
    if _zero_mq_bus is None:
        _zero_mq_bus = ZeroMQBus()
    return _zero_mq_bus


async def shutdown_zmq_bus() -> None:
    """Shutdown the global shared ZeroMQBus."""
    global _zero_mq_bus
    if _zero_mq_bus is not None:
        await _zero_mq_bus.shutdown()
        _zero_mq_bus = None


# ----------------------------------------------------------------------
# ZeroMQBus
# ----------------------------------------------------------------------


class ZeroMQBus:
    """基于ZeroMQ的Agent消息总线，支持Pub/Sub和Router/Dealer模式。

    作为全局单例，所有 bot 共用同一对 ZMQ socket（PUB + ROUTER）。
    通过 agent_id 前缀（"{bot_id}:{agent_id}"）区分不同 bot 下的 agent。
    """

    def __init__(self, bind_addr: str = "tcp://127.0.0.1:5555"):
        self._context: zmq.asyncio.Context | None = None
        self._pub_socket: zmq.asyncio.Socket | None = None
        self._router_socket: zmq.asyncio.Socket | None = None
        # agent_id -> (socket, task)
        self._sub_sockets: dict[str, tuple[zmq.asyncio.Socket, asyncio.Task]] = {}
        # agent_id -> handler
        self._handlers: dict[str, Callable] = {}
        # agent_id -> AgentManager instance
        self._managers: dict[str, "AgentManager"] = {}
        self._bind_addr = bind_addr
        self._agent_id: str | None = None
        self._is_initialized = False
        self._pending_delegations: dict[str, asyncio.Future[AgentMessage]] = {}
        self._router_loop_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        """初始化ZeroMQ上下文和 sockets。"""
        if self._is_initialized:
            return

        self._context = zmq.asyncio.Context()
        await self.start_publisher()
        await self.start_router()
        self._is_initialized = True
        logger.info("ZeroMQ Bus (shared) initialized at {}", self._bind_addr)

    def register_manager(self, bot_id: str, manager: "AgentManager") -> None:
        """Register an AgentManager so that messages can be routed to it."""
        self._managers[bot_id] = manager
        logger.debug("ZeroMQ Bus registered manager for bot '{}'", bot_id)

    def unregister_manager(self, bot_id: str) -> None:
        """Unregister an AgentManager on bot shutdown."""
        self._managers.pop(bot_id, None)
        logger.debug("ZeroMQ Bus unregistered manager for bot '{}'", bot_id)

    async def start_publisher(self) -> None:
        """启动Publisher (广播消息)。"""
        if self._context is None:
            self._context = zmq.asyncio.Context()

        self._pub_socket = self._context.socket(zmq.PUB)
        self._pub_socket.bind(self._bind_addr)
        logger.info("ZeroMQ Publisher bound to {}", self._bind_addr)

    async def start_router(self) -> None:
        """启动Router (用于Agent间直接通信/请求-响应模式)。"""
        if self._context is None:
            self._context = zmq.asyncio.Context()

        # 使用不同的端口（PUB端口+1）
        base_port = int(self._bind_addr.split(":")[-1])
        router_addr = f"tcp://127.0.0.1:{base_port + 1}"
        self._router_socket = self._context.socket(zmq.ROUTER)
        self._router_socket.bind(router_addr)
        logger.info("ZeroMQ Router bound to {}", router_addr)

        # 启动Router消息处理循环
        self._router_loop_task = asyncio.create_task(self._router_loop())

    async def subscribe(
        self, bot_id: str, agent_id: str, topics: list[str], handler: Callable[[AgentMessage], Any]
    ) -> None:
        """订阅一个或多个主题。bot_id+agent_id 组合构成唯一的 agent 标识。"""
        if self._context is None:
            self._context = zmq.asyncio.Context()

        # agent_id 在全局必须唯一：使用 "{bot_id}:{agent_id}" 前缀
        full_id = f"{bot_id}:{agent_id}"

        socket = self._context.socket(zmq.SUB)
        socket.connect(self._bind_addr)

        for topic in topics:
            socket.setsockopt(zmq.SUBSCRIBE, topic.encode())
            logger.debug("Agent {} (bot {}) subscribed to topic: {}", agent_id, bot_id, topic)

        task = asyncio.create_task(self._read_messages(socket, full_id, handler))
        self._sub_sockets[full_id] = (socket, task)
        self._handlers[full_id] = handler
        logger.info("Agent '{}' (bot '{}') subscribed to topics: {}", agent_id, bot_id, topics)

    async def unsubscribe(self, bot_id: str, agent_id: str) -> None:
        """取消订阅。"""
        full_id = f"{bot_id}:{agent_id}"
        if full_id in self._sub_sockets:
            socket, task = self._sub_sockets[full_id]
            task.cancel()
            socket.close()
            del self._sub_sockets[full_id]
            del self._handlers[full_id]
            logger.info("Agent '{}' (bot '{}') unsubscribed", agent_id, bot_id)

    async def publish(self, topic: str, message: AgentMessage) -> None:
        """发布消息到指定主题。"""
        if self._pub_socket is None:
            logger.warning("Publisher not initialized")
            return

        msg_data = json.dumps(asdict(message), ensure_ascii=False)
        await self._pub_socket.send_string(f"{topic}:{msg_data}")
        logger.debug("Published to topic {}: {}", topic, message.correlation_id)

    async def send_direct(
        self, receiver_bot_id: str, receiver_agent_id: str, message: AgentMessage, wait_response: bool = False
    ) -> AgentMessage | None:
        """直接发送消息给特定Agent (通过Router socket)。

        receiver_id 格式为 "{bot_id}:{agent_id}"，在全局唯一。
        """
        if self._router_socket is None:
            logger.warning("Router not initialized")
            return None

        # 全局唯一 receiver_id
        receiver_full_id = f"{receiver_bot_id}:{receiver_agent_id}"
        message = dataclass_replace(message, receiver_id=receiver_full_id)

        msg_data = json.dumps(asdict(message), ensure_ascii=False)

        if wait_response:
            future: asyncio.Future[AgentMessage] = asyncio.Future()
            self._pending_delegations[message.correlation_id] = future

        await self._router_socket.send_string(f"{receiver_full_id}:{msg_data}")
        logger.debug(
            "Sent direct to {}: {}",
            receiver_full_id,
            message.correlation_id,
        )

        if wait_response:
            try:
                response = await asyncio.wait_for(future, timeout=120.0)
                return response
            except asyncio.TimeoutError:
                logger.warning("Timeout waiting for response: {}", message.correlation_id)
                self._pending_delegations.pop(message.correlation_id, None)
                return None

        return None

    async def broadcast(self, message: AgentMessage) -> None:
        """广播消息给所有订阅者。"""
        await self.publish("broadcast", message)

    async def delegate_task(
        self,
        from_bot_id: str,
        from_agent_id: str,
        to_bot_id: str,
        to_agent_id: str,
        task: str,
        context: dict[str, Any],
        wait_response: bool = False,
    ) -> tuple[str, AgentMessage | None]:
        """将任务委托给另一个Agent（可跨bot）。"""
        sender_full_id = f"{from_bot_id}:{from_agent_id}"
        receiver_full_id = f"{to_bot_id}:{to_agent_id}"

        correlation_id = uuid.uuid4().hex[:8]
        message = AgentMessage(
            msg_type="delegate",
            sender_id=sender_full_id,
            receiver_id=receiver_full_id,
            topic="task_delegation",
            content=task,
            context=context,
            correlation_id=correlation_id,
        )

        response = await self.send_direct(to_bot_id, to_agent_id, message, wait_response)
        return correlation_id, response

    def set_agent_id(self, agent_id: str) -> None:
        """设置当前Agent ID。"""
        self._agent_id = agent_id
        logger.debug("ZeroMQ Bus agent_id set to: {}", agent_id)

    async def _read_messages(
        self, socket: zmq.asyncio.Socket, full_id: str, handler: Callable
    ) -> None:
        """持续读取订阅消息（SUB socket）。"""
        while True:
            try:
                message = await socket.recv_string()
                if ":" not in message:
                    continue
                topic, data = message.split(":", 1)
                msg_obj = AgentMessage(**json.loads(data))
                logger.debug(
                    "Agent {} received: topic={}, type={}, from={}",
                    full_id,
                    topic,
                    msg_obj.msg_type,
                    msg_obj.sender_id,
                )

                result = handler(msg_obj)
                if asyncio.iscoroutine(result):
                    await result

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error reading message for {}: {}", full_id, e)

    async def _router_loop(self) -> None:
        """Router socket消息处理循环，支持跨 bot 路由。

        ZMQ ROUTER 会自动附加发送方的 identity 帧。
        client_id 格式为 "{bot_id}:{agent_id}"，用于查找 handler。
        """
        while True:
            try:
                client_id = await self._router_socket.recv_string()
                message = await self._router_socket.recv_string()

                msg_obj = AgentMessage(**json.loads(message))
                logger.debug(
                    "Router received from {}: {}",
                    client_id,
                    msg_obj.correlation_id,
                )

                if (
                    msg_obj.msg_type == "response"
                    and msg_obj.correlation_id in self._pending_delegations
                ):
                    future = self._pending_delegations.pop(msg_obj.correlation_id)
                    if not future.done():
                        future.set_result(msg_obj)
                else:
                    if msg_obj.receiver_id in self._handlers:
                        handler = self._handlers[msg_obj.receiver_id]
                        result = handler(msg_obj)
                        if asyncio.iscoroutine(result):
                            await result
                    else:
                        logger.warning(
                            "No handler registered for receiver '{}' (from {})",
                            msg_obj.receiver_id,
                            client_id,
                        )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in router loop: {}", e)

    async def shutdown(self) -> None:
        """关闭所有socket和上下文。"""
        # 取消所有订阅任务（遍历时取 snapshot 以避免修改 dict）
        for full_id in list(self._sub_sockets.keys()):
            socket, task = self._sub_sockets[full_id]
            task.cancel()
            socket.close()
        self._sub_sockets.clear()
        self._handlers.clear()

        # 先取消 router_loop，再关闭 socket
        # 关闭 socket 会让 recv_string() 立即抛异常，从而让 loop 干净退出
        if self._router_loop_task:
            self._router_loop_task.cancel()
            try:
                await self._router_loop_task
            except asyncio.CancelledError:
                pass
            self._router_loop_task = None

        # 关闭sockets
        if self._pub_socket:
            self._pub_socket.close()
            self._pub_socket = None
        if self._router_socket:
            self._router_socket.close()
            self._router_socket = None
        if self._context:
            self._context.term()
            self._context = None

        self._is_initialized = False
        logger.info("ZeroMQ Bus shutdown")

    @property
    def is_initialized(self) -> bool:
        return self._is_initialized

    @property
    def agent_id(self) -> str | None:
        return self._agent_id

    @property
    def subscribed_agents(self) -> list[str]:
        return list(self._sub_sockets.keys())

    def get_queue_status(self) -> dict:
        """获取 ZMQ Bus 的连接状态和统计信息。"""
        return {
            "is_initialized": self._is_initialized,
            "bind_addr": self._bind_addr,
            "pub_socket": {
                "type": "PUB",
                "address": self._bind_addr,
                "connected": self._pub_socket is not None,
            },
            "router_socket": {
                "type": "ROUTER",
                "address": f"tcp://127.0.0.1:{int(self._bind_addr.split(':')[-1]) + 1}",
                "connected": self._router_socket is not None,
            },
            "sub_sockets": [
                {
                    "agent_id": full_id,
                    "bot_id": full_id.split(":")[0],
                    "topics": [],
                    "address": self._bind_addr,
                    "connected": socket is not None,
                }
                for full_id, (socket, _) in self._sub_sockets.items()
            ],
            "pending_delegations": len(self._pending_delegations),
        }


def get_queue_status() -> dict:
    """模块级便捷函数，获取全局 ZMQ Bus 状态。"""
    bus = get_zmq_bus()
    if bus is None or not bus.is_initialized:
        return {"is_initialized": False}
    return bus.get_queue_status()

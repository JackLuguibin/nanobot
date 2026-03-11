"""ZeroMQ-based Agent message bus for inter-agent communication."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Callable

import zmq
import zmq.asyncio
from loguru import logger


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


class ZeroMQBus:
    """基于ZeroMQ的Agent消息总线，支持Pub/Sub和Router/ Dealer模式。"""

    def __init__(self, bind_addr: str = "tcp://127.0.0.1:5555"):
        self._context: zmq.asyncio.Context | None = None
        self._pub_socket = None
        self._router_socket = None
        self._sub_sockets: dict[str, tuple[zmq.asyncio.Socket, asyncio.Task]] = {}
        self._handlers: dict[str, Callable] = {}
        self._bind_addr = bind_addr
        self._agent_id: str | None = None
        self._is_initialized = False
        self._pending_delegations: dict[str, asyncio.Future[AgentMessage]] = {}

    async def initialize(self) -> None:
        """初始化ZeroMQ上下文和 sockets。"""
        if self._is_initialized:
            return

        self._context = zmq.asyncio.Context()
        await self.start_publisher()
        await self.start_router()
        self._is_initialized = True
        logger.info("ZeroMQ Bus initialized at {}", self._bind_addr)

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
        asyncio.create_task(self._router_loop())

    async def subscribe(
        self, agent_id: str, topics: list[str], handler: Callable[[AgentMessage], Any]
    ) -> None:
        """订阅一个或多个主题。"""
        if self._context is None:
            self._context = zmq.asyncio.Context()

        socket = self._context.socket(zmq.SUB)
        socket.connect(self._bind_addr)

        for topic in topics:
            socket.setsockopt(zmq.SUBSCRIBE, topic.encode())
            logger.debug("Agent {} subscribed to topic: {}", agent_id, topic)

        task = asyncio.create_task(self._read_messages(socket, agent_id, handler))
        self._sub_sockets[agent_id] = (socket, task)
        self._handlers[agent_id] = handler
        logger.info("Agent {} subscribed to topics: {}", agent_id, topics)

    async def unsubscribe(self, agent_id: str) -> None:
        """取消订阅。"""
        if agent_id in self._sub_sockets:
            socket, task = self._sub_sockets[agent_id]
            task.cancel()
            socket.close()
            del self._sub_sockets[agent_id]
            del self._handlers[agent_id]
            logger.info("Agent {} unsubscribed", agent_id)

    async def publish(self, topic: str, message: AgentMessage) -> None:
        """发布消息到指定主题。"""
        if self._pub_socket is None:
            logger.warning("Publisher not initialized")
            return

        msg_data = json.dumps(asdict(message), ensure_ascii=False)
        await self._pub_socket.send_string(f"{topic}:{msg_data}")
        logger.debug("Published to topic {}: {}", topic, message.correlation_id)

    async def send_direct(
        self, receiver_id: str, message: AgentMessage, wait_response: bool = False
    ) -> AgentMessage | None:
        """直接发送消息给特定Agent (通过Router socket)。"""
        if self._router_socket is None:
            logger.warning("Router not initialized")
            return None

        msg_data = json.dumps(asdict(message), ensure_ascii=False)

        if wait_response:
            future: asyncio.Future[AgentMessage] = asyncio.Future()
            self._pending_delegations[message.correlation_id] = future

        await self._router_socket.send_string(f"{receiver_id}:{msg_data}")
        logger.debug(
            "Sent direct to {}: {}",
            receiver_id,
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
        to_agent_id: str,
        task: str,
        context: dict[str, Any],
        wait_response: bool = False,
    ) -> tuple[str, AgentMessage | None]:
        """将任务委托给另一个Agent。"""
        if self._agent_id is None:
            raise RuntimeError("Agent ID not set")

        correlation_id = uuid.uuid4().hex[:8]
        message = AgentMessage(
            msg_type="delegate",
            sender_id=self._agent_id,
            receiver_id=to_agent_id,
            topic="task_delegation",
            content=task,
            context=context,
            correlation_id=correlation_id,
        )

        response = await self.send_direct(to_agent_id, message, wait_response)
        return correlation_id, response

    def set_agent_id(self, agent_id: str) -> None:
        """设置当前Agent ID。"""
        self._agent_id = agent_id
        logger.info("ZeroMQ Bus agent_id set to: {}", agent_id)

    async def _read_messages(
        self, socket: zmq.asyncio.Socket, agent_id: str, handler: Callable
    ) -> None:
        """持续读取订阅消息。"""
        while True:
            try:
                message = await socket.recv_string()
                if ":" not in message:
                    continue
                topic, data = message.split(":", 1)
                msg_obj = AgentMessage(**json.loads(data))
                logger.debug(
                    "Agent {} received: topic={}, type={}, from={}",
                    agent_id,
                    topic,
                    msg_obj.msg_type,
                    msg_obj.sender_id,
                )

                # 处理消息
                result = handler(msg_obj)
                if asyncio.iscoroutine(result):
                    await result

                # 如果是请求消息，发送响应
                if (
                    msg_obj.msg_type == "delegate"
                    and msg_obj.receiver_id == agent_id
                ):
                    # 这里可以添加处理完成后发送响应的逻辑
                    pass

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error reading message for {}: {}", agent_id, e)

    async def _router_loop(self) -> None:
        """Router socket消息处理循环。"""
        while True:
            try:
                # Router接收: [client_id, message]
                client_id = await self._router_socket.recv_string()
                message = await self._router_socket.recv_string()

                msg_obj = AgentMessage(**json.loads(message))
                logger.debug(
                    "Router received from {}: {}",
                    client_id,
                    msg_obj.correlation_id,
                )

                # 检查是否是响应的委托任务
                if (
                    msg_obj.msg_type == "response"
                    and msg_obj.correlation_id in self._pending_delegations
                ):
                    future = self._pending_delegations.pop(msg_obj.correlation_id)
                    if not future.done():
                        future.set_result(msg_obj)
                else:
                    # 转发给对应的handler
                    if msg_obj.receiver_id in self._handlers:
                        handler = self._handlers[msg_obj.receiver_id]
                        result = handler(msg_obj)
                        if asyncio.iscoroutine(result):
                            await result

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in router loop: {}", e)

    async def shutdown(self) -> None:
        """关闭所有socket和上下文。"""
        # 取消所有订阅任务
        for agent_id in list(self._sub_sockets.keys()):
            await self.unsubscribe(agent_id)

        # 关闭sockets
        if self._pub_socket:
            self._pub_socket.close()
        if self._router_socket:
            self._router_socket.close()
        if self._context:
            self._context.term()

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

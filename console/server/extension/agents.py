"""Multi-Agent management for a single Bot."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from console.server.extension.zmq_bus import AgentMessage, ZeroMQBus, get_zmq_bus


# ----------------------------------------------------------------------
# Category
# ----------------------------------------------------------------------

CATEGORY_COLORS = [
    "#722ed1",
    "#13c2c2",
    "#eb2f96",
    "#2f54eb",
    "#fa8c16",
]


@dataclass
class CategoryConfig:
    key: str
    label: str
    color: str

    def to_dict(self) -> dict[str, str]:
        return {"key": self.key, "label": self.label, "color": self.color}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CategoryConfig":
        return cls(key=data["key"], label=data["label"], color=data["color"])


class CategoryManager:
    """Manages per-bot custom categories and per-agent category overrides.

    Persistence layout:
      <workspace>/agents/categories.json
        { "categories": [...], "overrides": { "<agent_id>": "<category_key>" } }
    """

    def __init__(self, bot_id: str, workspace: Path):
        self.bot_id = bot_id
        self.workspace = workspace
        self._categories: dict[str, CategoryConfig] = {}
        self._overrides: dict[str, str] = {}  # agent_id -> category key

    @property
    def _file(self) -> Path:
        return self.workspace / "agents" / "categories.json"

    async def initialize(self) -> None:
        (self.workspace / "agents").mkdir(exist_ok=True)
        await self._load()

    async def _load(self) -> None:
        if not self._file.exists():
            return
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            self._categories = {
                c["key"]: CategoryConfig.from_dict(c)
                for c in data.get("categories", [])
            }
            self._overrides = data.get("overrides", {})
            logger.debug(
                "CategoryManager loaded {} categories for bot '{}'",
                len(self._categories),
                self.bot_id,
            )
        except Exception as e:
            logger.error("Failed to load categories for bot '{}': {}", self.bot_id, e)
            self._categories = {}
            self._overrides = {}

    async def _save(self) -> None:
        data = {
            "categories": [c.to_dict() for c in self._categories.values()],
            "overrides": self._overrides,
        }
        self._file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def list_categories(self) -> list[CategoryConfig]:
        return list(self._categories.values())

    def get_category(self, key: str) -> CategoryConfig | None:
        return self._categories.get(key)

    async def add_category(self, label: str) -> CategoryConfig:
        if any(c.label == label for c in self._categories.values()):
            raise ValueError(f"Category '{label}' already exists")
        key = f"custom_{uuid.uuid4().hex[:8]}"
        idx = len(self._categories)
        color = CATEGORY_COLORS[idx % len(CATEGORY_COLORS)]
        cat = CategoryConfig(key=key, label=label, color=color)
        self._categories[key] = cat
        await self._save()
        return cat

    async def remove_category(self, key: str) -> bool:
        if key not in self._categories:
            return False
        del self._categories[key]
        # clear overrides that point to the removed category
        self._overrides = {k: v for k, v in self._overrides.items() if v != key}
        await self._save()
        return True

    def get_agent_category(self, agent_id: str) -> str | None:
        return self._overrides.get(agent_id)

    async def set_agent_category(self, agent_id: str, category_key: str | None) -> None:
        if category_key is None:
            self._overrides.pop(agent_id, None)
        else:
            self._overrides[agent_id] = category_key
        await self._save()

    def get_all_overrides(self) -> dict[str, str]:
        return dict(self._overrides)


# ----------------------------------------------------------------------
# Agent
# ----------------------------------------------------------------------


@dataclass
class AgentConfig:
    """单个Agent配置"""

    id: str
    name: str
    description: str | None = None
    model: str | None = None
    temperature: float | None = None
    system_prompt: str | None = None
    skills: list[str] = field(default_factory=list)
    enabled: bool = True
    topics: list[str] = field(default_factory=list)  # 订阅的ZeroMQ主题
    collaborators: list[str] = field(default_factory=list)  # 协作Agent列表
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典（序列化）"""
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentConfig":
        """从字典创建（反序列化）"""
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        return cls(**data)


class AgentManager:
    """Manages multiple Agents within a single Bot, with shared ZeroMQ bus.

    The ZeroMQBus is a global singleton shared across all bots. Each bot
    registers itself so that inter-bot agent delegation is supported via
    the "{bot_id}:{agent_id}" naming scheme.
    """

    def __init__(
        self,
        bot_id: str,
        workspace: Path,
        default_model: str = "anthropic/claude-sonnet-4-20250514",
    ):
        self.bot_id = bot_id
        self.workspace = workspace
        self.agents_dir = workspace / "agents"
        self.default_model = default_model
        # All bots share the same global ZeroMQBus singleton
        self._zmq_bus = get_zmq_bus()
        self._agents: dict[str, AgentConfig] = {}
        self._agent_handlers: dict[str, callable] = {}
        self._message_queue: asyncio.Queue[tuple[str, AgentMessage]] = asyncio.Queue()
        self._running = False
        self._process_task: asyncio.Task | None = None
        self._category_manager = CategoryManager(bot_id, workspace)

    @property
    def category_manager(self) -> CategoryManager:
        return self._category_manager

    async def initialize(self) -> None:
        """Initialize the Agent system."""
        self.agents_dir.mkdir(exist_ok=True)
        # Register with the shared global ZeroMQBus
        self._zmq_bus.register_manager(self.bot_id, self)
        await self._category_manager.initialize()
        await self._load_agents()
        self._running = True
        self._process_task = asyncio.create_task(self._process_messages())
        logger.info(
            "AgentManager initialized for bot '{}' with {} agents", self.bot_id, len(self._agents)
        )

    async def shutdown(self) -> None:
        """关闭Agent系统（供外部调用，如进程退出时）。"""
        await self._inner_shutdown()
        logger.info("AgentManager shutdown for bot '{}'", self.bot_id)

    async def _inner_shutdown(self) -> None:
        """内部关闭逻辑。"""
        self._running = False
        if self._process_task:
            self._process_task.cancel()
            try:
                await self._process_task
            except asyncio.CancelledError:
                pass
        # Unregister from the shared bus so messages stop being routed here
        self._zmq_bus.unregister_manager(self.bot_id)
        logger.debug("AgentManager inner shutdown for bot '{}'", self.bot_id)

    async def _load_agents(self) -> None:
        """从文件加载Agent配置"""
        config_file = self.agents_dir / "agents.json"
        if not config_file.exists():
            return

        try:
            data = json.loads(config_file.read_text(encoding="utf-8"))
            for agent_data in data.get("agents", []):
                agent = AgentConfig.from_dict(agent_data)
                self._agents[agent.id] = agent
                logger.debug("Loaded agent: {}", agent.id)
        except Exception as e:
            logger.error("Failed to load agents: {}", e)

    async def _save_agents(self) -> None:
        """保存Agent配置到文件"""
        config_file = self.agents_dir / "agents.json"
        data = {"agents": [agent.to_dict() for agent in self._agents.values()]}
        config_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.debug("Saved {} agents to {}", len(self._agents), config_file)

    def _create_handler(self, agent_id: str) -> callable:
        """创建Agent消息处理器"""

        async def handle_message(msg: AgentMessage) -> None:
            logger.info(
                "Agent '{}' (bot '{}') received message: type={}, from={}",
                agent_id,
                self.bot_id,
                msg.msg_type,
                msg.sender_id,
            )
            await self._message_queue.put((agent_id, msg))

        return handle_message

    async def _process_messages(self) -> None:
        """处理接收到的消息队列"""
        while self._running:
            try:
                agent_id, msg = await asyncio.wait_for(self._message_queue.get(), timeout=1.0)

                if msg.msg_type == "delegate":
                    await self._handle_delegation(agent_id, msg)
                elif msg.msg_type == "broadcast":
                    await self._handle_broadcast(agent_id, msg)
                elif msg.msg_type == "request":
                    await self._handle_request(agent_id, msg)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Error processing message: {}", e)

    async def _handle_delegation(self, agent_id: str, msg: AgentMessage) -> None:
        """处理任务委托"""
        logger.info(
            "Agent '{}' (bot '{}') handling delegation from '{}': {}",
            agent_id,
            self.bot_id,
            msg.sender_id,
            msg.content[:100],
        )
        # TODO: 将任务注入到对应Agent的AgentLoop处理

    async def _handle_broadcast(self, agent_id: str, msg: AgentMessage) -> None:
        """处理广播消息"""
        logger.debug(
            "Agent '{}' (bot '{}') received broadcast: {}", agent_id, self.bot_id, msg.topic
        )

    async def _handle_request(self, agent_id: str, msg: AgentMessage) -> None:
        """处理请求消息"""
        logger.debug("Agent '{}' received request: {}", agent_id, msg.correlation_id)

    # --- Public API ---

    def list_agents(self) -> list[AgentConfig]:
        """列出所有Agent"""
        return list(self._agents.values())

    def get_agent(self, agent_id: str) -> AgentConfig | None:
        """获取指定Agent"""
        return self._agents.get(agent_id)

    async def create_agent(self, config: AgentConfig) -> AgentConfig:
        """创建新Agent"""
        if config.id in self._agents:
            raise ValueError(f"Agent '{config.id}' already exists")

        if not config.id:
            config.id = uuid.uuid4().hex[:8]

        self._agents[config.id] = config
        await self._save_agents()

        # 订阅ZeroMQ主题
        if config.enabled and config.topics:
            await self._zmq_bus.subscribe(
                self.bot_id, config.id, config.topics, self._create_handler(config.id)
            )

        logger.info("Created agent '{}' ({})", config.name, config.id)
        return config

    async def update_agent(self, agent_id: str, updates: dict[str, Any]) -> AgentConfig:
        """更新Agent配置"""
        if agent_id not in self._agents:
            raise ValueError(f"Agent '{agent_id}' not found")

        agent = self._agents[agent_id]
        old_topics = agent.topics.copy() if agent.topics else []
        old_enabled = agent.enabled

        # 更新字段
        for key, value in updates.items():
            if hasattr(agent, key):
                setattr(agent, key, value)

        self._agents[agent_id] = agent
        await self._save_agents()

        # 处理订阅变更
        if old_enabled != agent.enabled or old_topics != agent.topics:
            await self._zmq_bus.unsubscribe(self.bot_id, agent_id)
            if agent.enabled and agent.topics:
                await self._zmq_bus.subscribe(
                    self.bot_id, agent_id, agent.topics, self._create_handler(agent_id)
                )

        logger.info("Updated agent '{}'", agent_id)
        return agent

    async def delete_agent(self, agent_id: str) -> bool:
        """删除Agent"""
        if agent_id not in self._agents:
            return False

        await self._zmq_bus.unsubscribe(self.bot_id, agent_id)
        del self._agents[agent_id]
        await self._save_agents()

        logger.info("Deleted agent '{}'", agent_id)
        return True

    async def enable_agent(self, agent_id: str) -> AgentConfig:
        """启用Agent"""
        return await self.update_agent(agent_id, {"enabled": True})

    async def disable_agent(self, agent_id: str) -> AgentConfig:
        """禁用Agent"""
        return await self.update_agent(agent_id, {"enabled": False})

    # --- Inter-Agent Communication ---

    async def delegate_task(
        self,
        from_agent_id: str,
        to_bot_id: str,
        to_agent_id: str,
        task: str,
        context: dict[str, Any] | None = None,
        wait_response: bool = False,
    ) -> tuple[str, AgentMessage | None]:
        """委托任务给另一个Agent（可跨bot）。"""
        if from_agent_id not in self._agents:
            raise ValueError(f"Source agent '{from_agent_id}' not found")

        correlation_id, response = await self._zmq_bus.delegate_task(
            from_bot_id=self.bot_id,
            from_agent_id=from_agent_id,
            to_bot_id=to_bot_id,
            to_agent_id=to_agent_id,
            task=task,
            context=context or {},
            wait_response=wait_response,
        )

        logger.info(
            "Task delegated from '{}' (bot '{}') to '{}' (bot '{}'): {}",
            from_agent_id,
            self.bot_id,
            to_agent_id,
            to_bot_id,
            correlation_id,
        )
        return correlation_id, response

    async def broadcast_event(
        self,
        agent_id: str,
        topic: str,
        content: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """广播事件给所有Agent（跨bot）。"""
        sender_full_id = f"{self.bot_id}:{agent_id}"

        msg = AgentMessage(
            msg_type="broadcast",
            sender_id=sender_full_id,
            receiver_id=None,
            topic=topic,
            content=content,
            context=context or {},
            correlation_id=uuid.uuid4().hex[:8],
        )

        await self._zmq_bus.broadcast(msg)
        logger.info("Agent '{}' (bot '{}') broadcast event: {}", agent_id, self.bot_id, topic)

    # --- Agent Routing ---

    async def select_agent(
        self, message: str, session_history: list[dict] | None = None
    ) -> AgentConfig | None:
        """根据消息内容智能选择最合适的Agent"""
        enabled_agents = [a for a in self._agents.values() if a.enabled]

        if not enabled_agents:
            return None

        if len(enabled_agents) == 1:
            return enabled_agents[0]

        # 简单的关键字匹配路由
        message_lower = message.lower()

        for agent in enabled_agents:
            if agent.skills:
                for skill in agent.skills:
                    if skill.lower() in message_lower:
                        logger.debug("Routed message to agent '{}' via keyword match", agent.id)
                        return agent

        # 默认返回第一个启用的Agent
        return enabled_agents[0]

    # --- Status ---

    def get_status(self) -> dict[str, Any]:
        """获取Agent系统状态"""
        return {
            "total_agents": len(self._agents),
            "enabled_agents": len([a for a in self._agents.values() if a.enabled]),
            "subscribed_agents": self._zmq_bus.subscribed_agents,
            "zmq_initialized": self._zmq_bus.is_initialized,
            "agent_id": self._zmq_bus.agent_id,
        }

    @property
    def zmq_bus(self) -> ZeroMQBus:
        """获取ZeroMQ总线实例"""
        return self._zmq_bus

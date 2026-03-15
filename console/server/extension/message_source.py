"""Extension: 为会话消息增加 source 字段，区分用户、主 Agent、子 Agent、工具调用。

不在 nanobot 核心中修改，通过 patch AgentLoop._save_turn 在写入 session 时注入 source。
"""

from __future__ import annotations

import contextvars
from typing import Any

from loguru import logger

# 当前对话轮次的来源：main_agent（主 Agent 轮）或 sub_agent（子 Agent 结果汇总轮）
_message_source_context: contextvars.ContextVar[str] = contextvars.ContextVar(
    "message_source_context", default="main_agent"
)

# 供 API/前端使用的 source 取值
SOURCE_USER = "user"
SOURCE_MAIN_AGENT = "main_agent"
SOURCE_SUB_AGENT = "sub_agent"
SOURCE_TOOL_CALL = "tool_call"


def get_message_source_context() -> str:
    """获取当前轮次的 message source 上下文。"""
    return _message_source_context.get()


def set_message_source_context(source: str) -> None:
    """设置当前轮次的 message source（main_agent / sub_agent）。"""
    _message_source_context.set(source)


def patch_agent_loop_message_source(agent_loop: Any) -> None:
    """Patch AgentLoop._save_turn，在写入 session 的每条消息上增加 source 字段。

    - role=user -> source=当前上下文（main_agent 时为 user，sub_agent 时为 sub_agent）
    - role=assistant -> source=当前上下文（main_agent / sub_agent）
    - role=tool -> source=tool_call
    """
    from nanobot.agent.loop import AgentLoop
    from nanobot.session.manager import Session

    if not isinstance(agent_loop, AgentLoop):
        return

    _original_save_turn = agent_loop._save_turn

    def _patched_save_turn(session: Session, messages: list[dict], skip: int) -> None:
        ctx = get_message_source_context()
        for m in messages[skip:]:
            role = m.get("role")
            if role == "user":
                m_source = SOURCE_USER if ctx == SOURCE_MAIN_AGENT else SOURCE_SUB_AGENT
            elif role == "assistant":
                m_source = ctx
            elif role == "tool":
                m_source = SOURCE_TOOL_CALL
            else:
                m_source = ctx
            m["source"] = m_source
        try:
            # _save_turn 内 entry=dict(m)，会带上 source 写入 session
            _original_save_turn(session, messages, skip)
        finally:
            for m in messages[skip:]:
                m.pop("source", None)

    agent_loop._save_turn = _patched_save_turn
    logger.info("Patched AgentLoop._save_turn with message source (user/main_agent/sub_agent/tool_call)")

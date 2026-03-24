"""WebSocket handling for real-time updates.

This module is kept for backward compatibility. New code should import from
console.server.websocket instead.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from loguru import logger

from console.server.models.chat import WSMessage
from console.server.models.base import WSMessageType

# Re-export from new module for backward compatibility
from console.server.websocket import (
    RoomManager,
    get_room_manager,
    handle_websocket,
    WSConnection,
)
from console.server.websocket.rooms import get_room_manager as _get_room_manager

if TYPE_CHECKING:
    from fastapi import WebSocket


class ConnectionManager:
    """Legacy wrapper around RoomManager for backward compatibility."""

    def __init__(self) -> None:
        self._rooms = _get_room_manager()

    async def connect(self, websocket: "WebSocket") -> None:
        await websocket.accept()

    async def disconnect(self, websocket: "WebSocket") -> None:
        await self._rooms.leave_all(websocket)

    async def send_message(self, message: WSMessage) -> None:
        data = message.model_dump()
        data["type"] = message.type.value if hasattr(message.type, "value") else message.type
        await self._rooms.broadcast(RoomManager.GLOBAL, data)

    async def send_to_session(self, session_key: str, message: WSMessage) -> None:
        # Broadcast to global for now (could route to page:chat in future)
        await self.send_message(message)

    async def send_to_connection(self, websocket: "WebSocket", message: WSMessage) -> None:
        data = message.model_dump()
        data["type"] = message.type.value if hasattr(message.type, "value") else message.type
        await self._rooms.send_to(websocket, data)

    async def broadcast_status_update(
        self, status: dict[str, Any], bot_id: str | None = None
    ) -> None:
        data = dict(status)
        if bot_id is not None:
            data["bot_id"] = bot_id
        msg = WSMessage(type=WSMessageType.STATUS_UPDATE, data=data)
        await self.send_message(msg)

    async def broadcast_sessions_update(
        self, sessions: list[dict[str, Any]], bot_id: str | None = None
    ) -> None:
        data: dict[str, Any] = {"sessions": sessions}
        if bot_id is not None:
            data["bot_id"] = bot_id
        msg = WSMessage(type=WSMessageType.SESSIONS_UPDATE, data=data)
        await self.send_message(msg)

    async def broadcast_tool_call(
        self, session_key: str, tool_name: str, tool_id: str, arguments: dict
    ) -> None:
        msg = WSMessage(
            type=WSMessageType.TOOL_CALL,
            data={"tool_name": tool_name, "tool_id": tool_id, "arguments": arguments},
            session_key=session_key,
        )
        await self.send_message(msg)

    async def broadcast_tool_result(
        self, session_key: str, tool_id: str, result: str, error: str | None = None
    ) -> None:
        msg = WSMessage(
            type=WSMessageType.TOOL_RESULT,
            data={"tool_id": tool_id, "result": result, "error": error},
            session_key=session_key,
        )
        await self.send_message(msg)

    async def broadcast_chat_token(
        self, session_key: str, token: str, is_final: bool = False
    ) -> None:
        msg = WSMessage(
            type=WSMessageType.CHAT_TOKEN,
            data={"token": token, "is_final": is_final},
            session_key=session_key,
        )
        await self.send_message(msg)

    async def broadcast_bots_update(self) -> None:
        msg = WSMessage(type=WSMessageType.BOTS_UPDATE, data={})
        await self.send_message(msg)

    async def broadcast_queue_update(self, data: dict[str, Any]) -> None:
        msg = WSMessage(type=WSMessageType.QUEUE_UPDATE, data=data)
        await self.send_message(msg)


_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager (legacy interface)."""
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager

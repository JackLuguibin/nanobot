"""WebSocket handling for real-time updates."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger

from console.server.api.models import WSMessage, WSMessageType
from console.server.api.state import get_state, get_state_manager


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and track a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    async def send_message(self, message: WSMessage) -> None:
        """Send a message to all connected clients."""
        if not self.active_connections:
            return

        message_json = json.dumps(message.model_dump(), default=str)

        # Create a copy of connections to avoid mutation during iteration
        async with self._lock:
            connections = self.active_connections.copy()

        # Send to all connections
        disconnected = []
        for connection in connections:
            try:
                await connection.send_text(message_json)
            except OSError:
                disconnected.append(connection)

        # Clean up disconnected clients
        async with self._lock:
            for conn in disconnected:
                if conn in self.active_connections:
                    self.active_connections.remove(conn)

    async def send_to_session(self, session_key: str, message: WSMessage) -> None:
        """Send a message to a specific session's clients."""
        # For now, broadcast to all - could be enhanced to track per-session
        await self.send_message(message)

    async def send_to_connection(self, websocket: WebSocket, message: WSMessage) -> None:
        """Send a message to a single WebSocket connection."""
        try:
            message_json = json.dumps(message.model_dump(), default=str)
            await websocket.send_text(message_json)
        except OSError:
            pass

    async def broadcast_status_update(
        self, status: dict[str, Any], bot_id: str | None = None
    ) -> None:
        """Broadcast a status update to all clients."""
        data = dict(status)
        if bot_id is not None:
            data["bot_id"] = bot_id
        message = WSMessage(
            type=WSMessageType.STATUS_UPDATE,
            data=data,
        )
        await self.send_message(message)

    async def broadcast_sessions_update(
        self, sessions: list[dict[str, Any]], bot_id: str | None = None
    ) -> None:
        """Broadcast a sessions update to all clients."""
        data: dict[str, Any] = {"sessions": sessions}
        if bot_id is not None:
            data["bot_id"] = bot_id
        message = WSMessage(
            type=WSMessageType.SESSIONS_UPDATE,
            data=data,
        )
        await self.send_message(message)

    async def broadcast_tool_call(
        self, session_key: str, tool_name: str, tool_id: str, arguments: dict
    ) -> None:
        """Broadcast a tool call notification."""
        message = WSMessage(
            type=WSMessageType.TOOL_CALL,
            data={
                "tool_name": tool_name,
                "tool_id": tool_id,
                "arguments": arguments,
            },
            session_key=session_key,
        )
        await self.send_message(message)

    async def broadcast_tool_result(
        self, session_key: str, tool_id: str, result: str, error: str | None = None
    ) -> None:
        """Broadcast a tool result."""
        message = WSMessage(
            type=WSMessageType.TOOL_RESULT,
            data={
                "tool_id": tool_id,
                "result": result,
                "error": error,
            },
            session_key=session_key,
        )
        await self.send_message(message)

    async def broadcast_chat_token(
        self, session_key: str, token: str, is_final: bool = False
    ) -> None:
        """Broadcast a chat token."""
        message = WSMessage(
            type=WSMessageType.CHAT_TOKEN,
            data={
                "token": token,
                "is_final": is_final,
            },
            session_key=session_key,
        )
        await self.send_message(message)

    async def broadcast_bots_update(self) -> None:
        """Broadcast that the bots list has changed (create/delete/set_default)."""
        message = WSMessage(type=WSMessageType.BOTS_UPDATE, data={})
        await self.send_message(message)


# Global connection manager
_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager."""
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager


async def handle_websocket(websocket: WebSocket) -> None:
    """Handle a WebSocket connection.

    This is a simple implementation that maintains the connection
    and allows sending messages from other parts of the application.
    On connect, sends initial status and sessions for the default bot.
    """
    manager = get_connection_manager()
    await manager.connect(websocket)

    # Send initial status and sessions for default bot on connect
    try:
        state_manager = get_state_manager()
        default_bot_id = state_manager.default_bot_id
        if default_bot_id:
            state = get_state(default_bot_id)
            status = await state.get_status()
            status_data = dict(status)
            status_data["bot_id"] = default_bot_id
            await manager.send_to_connection(
                websocket,
                WSMessage(type=WSMessageType.STATUS_UPDATE, data=status_data),
            )
            sessions = await state.get_sessions()
            await manager.send_to_connection(
                websocket,
                WSMessage(
                    type=WSMessageType.SESSIONS_UPDATE,
                    data={"bot_id": default_bot_id, "sessions": sessions},
                ),
            )
    except Exception as e:
        logger.debug("WebSocket initial send failed: {}", e)

    try:
        # Keep the connection alive and handle incoming messages
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60)

                # Handle incoming messages (e.g., chat messages)
                try:
                    message = json.loads(data)
                    # Process message based on type
                    msg_type = message.get("type")

                    if msg_type == "chat":
                        # Handle chat message - this would integrate with AgentLoop
                        response = {
                            "type": "chat_response",
                            "data": {"status": "received"},
                        }
                        await websocket.send_text(json.dumps(response))
                    elif msg_type == "subscribe" or msg_type == "request_initial":
                        # Client requests initial status/sessions for a specific bot
                        bot_id = message.get("bot_id") or get_state_manager().default_bot_id
                        if bot_id:
                            state = get_state(bot_id)
                            status = await state.get_status()
                            status_data = dict(status)
                            status_data["bot_id"] = bot_id
                            await manager.send_to_connection(
                                websocket,
                                WSMessage(type=WSMessageType.STATUS_UPDATE, data=status_data),
                            )
                            sessions = await state.get_sessions()
                            await manager.send_to_connection(
                                websocket,
                                WSMessage(
                                    type=WSMessageType.SESSIONS_UPDATE,
                                    data={"bot_id": bot_id, "sessions": sessions},
                                ),
                            )

                except json.JSONDecodeError:
                    pass

            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                continue

    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket)

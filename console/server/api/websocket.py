"""WebSocket handling for real-time updates."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

from fastapi import WebSocket, WebSocketDisconnect

from console.server.api.models import WSMessage, WSMessageType


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
            except Exception:
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
    
    async def broadcast_status_update(self, status: dict[str, Any]) -> None:
        """Broadcast a status update to all clients."""
        message = WSMessage(
            type=WSMessageType.STATUS_UPDATE,
            data=status,
        )
        await self.send_message(message)
    
    async def broadcast_tool_call(self, session_key: str, tool_name: str, tool_id: str, arguments: dict) -> None:
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
    
    async def broadcast_tool_result(self, session_key: str, tool_id: str, result: str, error: str | None = None) -> None:
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
    
    async def broadcast_chat_token(self, session_key: str, token: str, is_final: bool = False) -> None:
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
    """
    manager = get_connection_manager()
    await manager.connect(websocket)
    
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
                    
                except json.JSONDecodeError:
                    pass
                    
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                continue
                
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket)

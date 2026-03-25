"""WebSocket module.

Provides room-based WebSocket connection management. Each client connection
belongs to one or more rooms and receives only messages broadcast to those
rooms. This replaces the flat "all clients" broadcast model.

Typical usage:
    from console.server.websocket import get_room_manager, handle_websocket

    # In an API router:
    @router.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await handle_websocket(ws)

    # To broadcast to a room:
    await get_room_manager().broadcast("page:chat", {"type": "chat_token", ...})

Room naming convention:
    global           - all connected clients
    page:<page_name> - clients viewing a specific page
    bot:<bot_id>     - clients watching a specific bot
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket

from console.server.websocket.handler import WSConnection, handle_websocket
from console.server.websocket.rooms import RoomManager, get_room_manager

ws_router = APIRouter()

# Expose the singleton room manager so other modules (e.g. extension/activity.py)
# can broadcast to WebSocket rooms without importing rooms directly.
room_manager = get_room_manager()


@ws_router.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await handle_websocket(ws)


__all__ = [
    "WSConnection",
    "RoomManager",
    "get_room_manager",
    "handle_websocket",
    "room_manager",
    "ws_router",
]

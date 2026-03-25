"""WebSocket rooms module.

Each WebSocket connection belongs to one or more "rooms" based on the page it
is on. This allows targeted broadcasting: only clients viewing the same page
receive updates relevant to that page.

Room naming convention:
  page:<page_name>    - e.g. "page:chat", "page:queue", "page:status"
  bot:<bot_id>        - all clients watching a specific bot
  global              - broadcast to every connected client
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket
from loguru import logger


@dataclass
class Room:
    """A logical channel for broadcasting messages to a subset of clients."""

    name: str
    connections: set[WebSocket] = field(default_factory=set)

    async def add(self, ws: WebSocket) -> None:
        self.connections.add(ws)

    async def remove(self, ws: WebSocket) -> None:
        self.connections.discard(ws)

    @property
    def size(self) -> int:
        return len(self.connections)


class RoomManager:
    """
    Manages WebSocket rooms and their members.

    A connection can subscribe to multiple rooms simultaneously.
    When a connection closes, it is automatically removed from all rooms.
    """

    GLOBAL = "global"
    SYSTEM_ROOMS = {"global"}

    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}
        self._conn_rooms: dict[int, set[str]] = {}
        self._lock = asyncio.Lock()

    def _room(self, name: str) -> Room:
        if name not in self._rooms:
            self._rooms[name] = Room(name=name)
        return self._rooms[name]

    def _conn_id(self, ws: WebSocket) -> int:
        return id(ws)

    async def join(self, ws: WebSocket, room_name: str) -> None:
        """Add a connection to a room."""
        async with self._lock:
            rid = self._conn_id(ws)
            if rid not in self._conn_rooms:
                self._conn_rooms[rid] = set()
            self._conn_rooms[rid].add(room_name)
            await self._room(room_name).add(ws)

    async def leave(self, ws: WebSocket, room_name: str) -> None:
        """Remove a connection from a room."""
        async with self._lock:
            rid = self._conn_id(ws)
            if room := self._rooms.get(room_name):
                await room.remove(ws)
            if rid in self._conn_rooms:
                self._conn_rooms[rid].discard(room_name)

    async def leave_all(self, ws: WebSocket) -> None:
        """Remove a connection from all rooms it has joined."""
        async with self._lock:
            rid = self._conn_id(ws)
            room_names = self._conn_rooms.pop(rid, set())
            for name in room_names:
                if room := self._rooms.get(name):
                    await room.remove(ws)

    async def broadcast(
        self,
        room_name: str,
        message: dict[str, Any],
        exclude: WebSocket | None = None,
    ) -> None:
        """Send a message to all connections in a room."""
        if room_name not in self._rooms:
            return

        room = self._rooms[room_name]
        if not room.connections:
            return

        import json

        message_json = json.dumps(message, default=str)

        async with self._lock:
            targets = room.connections.copy()

        disconnected = []
        for ws in targets:
            if exclude and self._conn_id(ws) == self._conn_id(exclude):
                continue
            try:
                await ws.send_text(message_json)
            except OSError:
                disconnected.append(ws)

        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    await self.leave(ws, room_name)

    async def send_to(self, ws: WebSocket, message: dict[str, Any]) -> None:
        """Send a message to a single connection."""
        try:
            import json
            await ws.send_text(json.dumps(message, default=str))
        except OSError:
            pass

    def room_clients(self, room_name: str) -> int:
        """Return the number of connected clients in a room."""
        return self._rooms.get(room_name, Room(name=room_name)).size

    async def shutdown(self) -> None:
        """Clean up room manager resources."""
        self._rooms.clear()
        self._conn_rooms.clear()


# Global singleton
_room_manager: RoomManager | None = None


def get_room_manager() -> RoomManager:
    global _room_manager
    if _room_manager is None:
        _room_manager = RoomManager()
    return _room_manager

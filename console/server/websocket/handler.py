"""WebSocket connection handler.

Each incoming connection is assigned to rooms based on the page it
is viewing. The client sends subscribe/unsubscribe messages to move
between rooms; it starts in the "global" room only.

Supported client messages:
  { "type": "subscribe", "room": "page:chat" }
  { "type": "unsubscribe", "room": "page:chat" }
  { "type": "subscribe", "bot_id": "my-bot" }      # shortcut for "bot:<bot_id>"
  { "type": "chat", "message": "...", "session_key": "..." }
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger

from console.server.api.state import get_state, get_state_manager
from console.server.models.chat import WSMessage
from console.server.models.enums import WSMessageType
from console.server.websocket.rooms import RoomManager, get_room_manager


def _bot_room(bot_id: str) -> str:
    return f"bot:{bot_id}"


def _page_room(page: str) -> str:
    return f"page:{page}"


class WSConnection:
    """Encapsulates the state of a single WebSocket client."""

    def __init__(self, ws: WebSocket, rooms: RoomManager) -> None:
        self._ws = ws
        self._rooms = rooms
        self._rooms_joined: set[str] = set()

    async def accept(self) -> None:
        await self._ws.accept()

    async def join_room(self, name: str) -> None:
        if name in self._rooms_joined:
            return
        await self._rooms.join(self._ws, name)
        self._rooms_joined.add(name)

    async def _broadcast_queue_to_page(self) -> None:
        """Push queue status once to the page:queue room (called on subscribe)."""
        try:
            state_manager = get_state_manager()
            all_status = await state_manager.get_all_queue_status()
            await self._rooms.broadcast(
                "page:queue",
                {
                    "type": "queue_update",
                    "data": {"queues": all_status},
                    "session_key": None,
                },
            )
        except Exception as e:
            logger.debug("[WS] Failed to broadcast queue to page:queue: {}", e)

    async def leave_room(self, name: str) -> None:
        if name not in self._rooms_joined:
            return
        await self._rooms.leave(self._ws, name)
        self._rooms_joined.discard(name)

    async def leave_all_rooms(self) -> None:
        await self._rooms.leave_all(self._ws)
        self._rooms_joined.clear()

    async def send_json(self, data: dict[str, Any]) -> None:
        try:
            await self._ws.send_text(json.dumps(data, default=str))
        except OSError:
            pass

    async def send_ws_message(self, msg: WSMessage) -> None:
        data = msg.model_dump()
        data["type"] = msg.type.value if hasattr(msg.type, "value") else msg.type
        await self.send_json(data)

    async def send_initial_state(self) -> None:
        """Send initial status, sessions, and queue data for the default bot."""
        try:
            state_manager = get_state_manager()
            default_bot_id = state_manager.default_bot_id or ""

            if default_bot_id:
                state = get_state(default_bot_id)
                status = await state.get_status()
                status_data = dict(status)
                status_data["bot_id"] = default_bot_id
                await self.send_ws_message(
                    WSMessage(type=WSMessageType.STATUS_UPDATE, data=status_data)
                )
                sessions = await state.get_sessions()
                await self.send_ws_message(
                    WSMessage(
                        type=WSMessageType.SESSIONS_UPDATE,
                        data={"bot_id": default_bot_id, "sessions": sessions},
                    )
                )
                all_status = await state_manager.get_all_queue_status()
                await self.send_ws_message(
                    WSMessage(type=WSMessageType.QUEUE_UPDATE, data={"queues": all_status})
                )
        except Exception as e:
            logger.debug("Failed to send initial state: {}", e)

    async def handle_subscribe(self, msg: dict[str, Any]) -> None:
        """Handle subscribe message: join a room (page or bot)."""
        room_name: str | None = msg.get("room")
        if room_name:
            await self.join_room(room_name)
            if room_name == "page:queue":
                await self._broadcast_queue_to_page()
            return

        bot_id: str | None = msg.get("bot_id")
        if bot_id:
            await self.join_room(_bot_room(bot_id))
            return

        page: str | None = msg.get("page")
        if page:
            await self.join_room(_page_room(page))

    async def handle_unsubscribe(self, msg: dict[str, Any]) -> None:
        """Handle unsubscribe message: leave a room."""
        room_name: str | None = msg.get("room")
        if room_name:
            await self.leave_room(room_name)
            return

        bot_id: str | None = msg.get("bot_id")
        if bot_id:
            await self.leave_room(_bot_room(bot_id))

    async def handle_chat(self, msg: dict[str, Any]) -> None:
        """Handle chat message from client via WebSocket.

        Runs the agent loop, streams tokens/progress/tool calls back through
        the same WebSocket connection, then broadcasts status updates to all
        connected clients.
        """
        from console.server.api.chat import _resolve_state, _agent_unavailable_detail
        from console.server.api.websocket import get_connection_manager
        from console.server.extension.message_source import (
            SOURCE_MAIN_AGENT,
            SOURCE_SUB_AGENT,
            set_message_source_context,
        )
        from console.server.extension.subagent_events import set_subagent_callback
        from console.server.models.chat import ChatRequest

        try:
            request = ChatRequest.model_validate(msg)
        except Exception:
            await self.send_json({"type": "error", "error": "Invalid chat request"})
            return

        state = _resolve_state(request.bot_id)
        agent_loop = state.agent_loop

        if agent_loop is None:
            await self.send_json({
                "type": "error",
                "error": _agent_unavailable_detail(state),
            })
            return

        session_key = request.session_key
        if session_key is None:
            session = await state.create_session()
            session_key = session["key"]
            await self.send_json({"type": "session_key", "session_key": session_key})

        subagent_active: set[str] = set()

        async def stream_progress(content: str | None, *, tool_hint: bool = False) -> None:
            if tool_hint:
                if content:
                    await self.send_json({"type": "tool_progress", "content": content})
                return
            if content:
                await self.send_json({"type": "chat_token", "content": content})

        async def on_subagent_event(event: dict[str, Any]) -> None:
            await self.send_json(event)

            subagent_id = event.get("subagent_id")
            event_type = event.get("type")
            if event_type == "subagent_start" and isinstance(subagent_id, str):
                subagent_active.add(subagent_id)
            elif event_type == "subagent_done" and isinstance(subagent_id, str):
                subagent_active.discard(subagent_id)

            if event_type != "subagent_done":
                return

            label = event.get("label", "task")
            task = event.get("task", "")
            result = event.get("result", "")
            status = event.get("status", "error")
            status_text = "completed successfully" if status == "ok" else "failed"

            summarize_content = f"""[Subagent '{label}' {status_text}]

Task: {task}

Result:
{result}

Summarize this naturally for the user. Keep it brief (1-2 sentences). Do not mention technical details like "subagent" or task IDs."""

            try:
                set_message_source_context(SOURCE_SUB_AGENT)
                follow_up_response = await agent_loop.process_direct(
                    content=summarize_content,
                    session_key=session_key,
                    channel="console",
                    chat_id="web",
                    on_progress=stream_progress,
                )
                if follow_up_response:
                    content = follow_up_response.content if hasattr(follow_up_response, "content") else follow_up_response
                    await self.send_json({
                        "type": "assistant_message",
                        "content": content,
                        "source": "sub_agent",
                    })
            except Exception as e:
                logger.warning("Failed to process subagent result: {}", e)

        set_subagent_callback(agent_loop, on_subagent_event)

        response_holder: list[str] = []

        try:
            set_message_source_context(SOURCE_MAIN_AGENT)
            response_text = await agent_loop.process_direct(
                content=request.message,
                session_key=session_key,
                channel="console",
                chat_id="web",
                on_progress=stream_progress,
            )
            response_holder.append(response_text.content if response_text else "")
        except Exception as e:
            logger.error("Error in WS chat: {}", e)
            await self.send_json({"type": "error", "error": str(e)})
            return

        state.increment_messages()

        try:
            manager = get_connection_manager()
            status = await state.get_status()
            sessions = await state.get_sessions()
            await manager.broadcast_status_update(status, state.bot_id)
            await manager.broadcast_sessions_update(sessions, state.bot_id)
        except Exception as e:
            logger.warning("Failed to broadcast status update: {}", e)

        response_text = response_holder[0] if response_holder else ""
        await self.send_json({
            "type": "chat_done",
            "done": True,
            "content": response_text,
            "source": "main_agent",
        })

    async def handle_message(self, raw: str) -> bool:
        """Parse and handle a client message. Returns False to signal disconnect."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return True

        msg_type = msg.get("type")

        if msg_type == "subscribe" or msg_type == "request_initial":
            await self.handle_subscribe(msg)
            if msg_type == "request_initial":
                await self.send_initial_state()

        elif msg_type == "unsubscribe":
            await self.handle_unsubscribe(msg)

        elif msg_type == "chat":
            await self.handle_chat(msg)

        return True

    @property
    def ws(self) -> WebSocket:
        return self._ws


async def handle_websocket(websocket: WebSocket) -> None:
    """Main entry point: accept a connection, set up rooms, run the loop."""
    rooms = get_room_manager()
    conn = WSConnection(websocket, rooms)

    await conn.accept()
    await conn.join_room(RoomManager.GLOBAL)
    logger.debug("[WS] Client connected, joined global room")

    try:
        await conn.send_initial_state()

        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60)
                should_continue = await conn.handle_message(data)
                if not should_continue:
                    break
            except asyncio.TimeoutError:
                continue

    except WebSocketDisconnect:
        pass
    finally:
        await conn.leave_all_rooms()
        logger.debug("[WS] Client disconnected")

"""消息队列监控 API。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from console.server.api.state import get_state, get_state_manager
from console.server.models.queue import AllQueueStatusResponse, QueueStatusResponse

router = APIRouter(prefix="/queue")


@router.get("/status")
async def get_queue_status(
    bot_id: str | None = Query(None),
) -> QueueStatusResponse | AllQueueStatusResponse:
    """获取所有 Bot（或指定 Bot）的队列状态。"""
    manager = get_state_manager()
    if bot_id:
        state = get_state(bot_id)
        raw = await state.get_queue_status()
        return QueueStatusResponse(**raw)
    raws = await manager.get_all_queue_status()
    return AllQueueStatusResponse(statuses=[QueueStatusResponse(**raw) for raw in raws])

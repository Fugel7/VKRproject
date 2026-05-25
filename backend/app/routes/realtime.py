import asyncio

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from psycopg import connect
from psycopg.rows import dict_row

from app.db import get_database_url
from app.project_service import ensure_project_member, get_user_id_by_tg_id
from app.services.realtime_service import format_sse_message, project_event_bus

router = APIRouter()

SSE_HEARTBEAT_INTERVAL_SECONDS = 15


def _assert_project_access(project_id: int, tg_id: int) -> None:
    with connect(get_database_url()) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            user_id = get_user_id_by_tg_id(cur, tg_id)
            ensure_project_member(cur, project_id, user_id)


@router.get('/projects/{project_id}/events')
async def project_events(project_id: int, tg_id: int) -> StreamingResponse:
    _assert_project_access(project_id, tg_id)

    async def event_stream():
        queue = await project_event_bus.subscribe(project_id)
        try:
            yield format_sse_message('ready', {'project_id': project_id})
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=SSE_HEARTBEAT_INTERVAL_SECONDS)
                    yield format_sse_message('board_update', event)
                except asyncio.TimeoutError:
                    yield ': heartbeat\n\n'
        finally:
            await project_event_bus.unsubscribe(project_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )

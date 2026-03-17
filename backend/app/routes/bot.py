import os

from fastapi import APIRouter, Header, HTTPException

from app.schemas import BotChatProjectRequest, BotIngestMessageRequest
from app.services.board_service import create_bot_tasks_from_message
from app.services.chat_project_service import ensure_chat_project

router = APIRouter()


def _require_bot_token(x_bot_token: str | None) -> None:
    expected_token = os.getenv('BOT_INTERNAL_TOKEN')
    if not expected_token:
        raise HTTPException(status_code=503, detail='BOT_INTERNAL_TOKEN is not configured')
    if not x_bot_token or x_bot_token != expected_token:
        raise HTTPException(status_code=401, detail='Invalid bot token')


@router.post('/bot/chat-project')
def bot_chat_project(payload: BotChatProjectRequest, x_bot_token: str | None = Header(default=None)) -> dict:
    _require_bot_token(x_bot_token)
    project = ensure_chat_project(payload.chat_id, payload.chat_type, payload.title)
    return {'ok': True, 'project': project}


@router.post('/bot/ingest-message')
def bot_ingest_message(payload: BotIngestMessageRequest, x_bot_token: str | None = Header(default=None)) -> dict:
    _require_bot_token(x_bot_token)
    result = create_bot_tasks_from_message(payload)
    return {'ok': True, **result}

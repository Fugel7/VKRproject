import os

from fastapi import APIRouter, HTTPException

from app.auth_service import get_user_by_tg_id, save_or_update_user, verify_telegram_init_data
from app.schemas import TelegramAuthRequest
from app.services.chat_project_service import ensure_chat_project_for_user, ensure_project_member_by_start_param

router = APIRouter()


@router.get('/me')
def me(tg_id: int) -> dict:
    user = get_user_by_tg_id(tg_id)
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    return {'ok': True, 'user': user}


@router.post('/auth/telegram')
def auth_telegram(payload: TelegramAuthRequest) -> dict:
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        raise HTTPException(status_code=503, detail='TELEGRAM_BOT_TOKEN is not configured')

    verified = verify_telegram_init_data(payload.init_data, bot_token)
    user = verified['user']
    context = verified['context']

    existing_chat = context.get('chat') if isinstance(context.get('chat'), dict) else {}
    fallback_chat = {
        'id': existing_chat.get('id') if existing_chat.get('id') is not None else payload.unsafe_chat_id,
        'type': existing_chat.get('type') or payload.unsafe_chat_type or context.get('chat_type'),
        'title': existing_chat.get('title') or payload.unsafe_chat_title,
    }
    if any(value is not None for value in fallback_chat.values()):
        context['chat'] = fallback_chat
    if not context.get('chat_type') and payload.unsafe_chat_type:
        context['chat_type'] = payload.unsafe_chat_type
    if not context.get('start_param') and payload.start_param:
        context['start_param'] = payload.start_param

    db_user = save_or_update_user(user)
    active_project = ensure_project_member_by_start_param(context.get('start_param'), db_user['id'])
    if active_project is None:
        active_project = ensure_chat_project_for_user(context, db_user['id'])
    return {
        'ok': True,
        'user': user,
        'db_user': db_user,
        'active_project': active_project,
        'launched_from_chat': active_project is not None,
    }

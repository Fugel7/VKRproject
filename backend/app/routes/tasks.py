from fastapi import APIRouter

from app.schemas import CommentCreateRequest, TaskUpdateRequest
from app.services.board_service import create_task_comment, delete_task, list_task_comments, list_task_history, update_task

router = APIRouter()


@router.patch('/tasks/{task_id}')
def patch_task(task_id: int, payload: TaskUpdateRequest) -> dict:
    return {'ok': True, 'task': update_task(task_id, payload)}


@router.delete('/tasks/{task_id}')
def remove_task(task_id: int, tg_id: int) -> dict:
    deleted = delete_task(task_id, tg_id)
    return {'ok': True, 'deleted_task_id': deleted['id']}


@router.get('/tasks/{task_id}/comments')
def task_comments(task_id: int, tg_id: int) -> dict:
    return {'ok': True, 'comments': list_task_comments(task_id, tg_id)}


@router.get('/tasks/{task_id}/history')
def task_history(task_id: int, tg_id: int) -> dict:
    return {'ok': True, 'history': list_task_history(task_id, tg_id)}


@router.post('/tasks/{task_id}/comments')
def create_comment(task_id: int, payload: CommentCreateRequest) -> dict:
    return {'ok': True, 'comment': create_task_comment(task_id, payload)}

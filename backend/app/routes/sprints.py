from fastapi import APIRouter

from app.schemas import SprintUpdateRequest
from app.services.board_service import delete_sprint, update_sprint

router = APIRouter()


@router.patch('/sprints/{sprint_id}')
def patch_sprint(sprint_id: int, payload: SprintUpdateRequest) -> dict:
    return {'ok': True, 'sprint': update_sprint(sprint_id, payload)}


@router.delete('/sprints/{sprint_id}')
def remove_sprint(sprint_id: int, tg_id: int) -> dict:
    deleted = delete_sprint(sprint_id, tg_id)
    return {'ok': True, 'deleted_sprint_id': deleted['id']}

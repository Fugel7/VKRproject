from fastapi import APIRouter

from app.project_service import delete_project_by_tg_id, get_projects_by_tg_id
from app.schemas import SprintCreateRequest, TaskCreateRequest
from app.services.board_service import create_project_sprint, create_project_task, list_project_sprints, list_project_tasks

router = APIRouter()


@router.get('/projects')
def projects(tg_id: int) -> dict:
    return {'ok': True, 'projects': get_projects_by_tg_id(tg_id)}


@router.delete('/projects/{project_id}')
def delete_project(project_id: int, tg_id: int) -> dict:
    deleted = delete_project_by_tg_id(project_id, tg_id)
    return {'ok': True, 'deleted_project_id': deleted['id']}


@router.get('/projects/{project_id}/tasks')
def project_tasks(project_id: int, tg_id: int) -> dict:
    return {'ok': True, 'tasks': list_project_tasks(project_id, tg_id)}


@router.post('/projects/{project_id}/tasks')
def project_create_task(project_id: int, payload: TaskCreateRequest) -> dict:
    return {'ok': True, 'task': create_project_task(project_id, payload)}


@router.get('/projects/{project_id}/sprints')
def project_sprints(project_id: int, tg_id: int) -> dict:
    return {'ok': True, 'sprints': list_project_sprints(project_id, tg_id)}


@router.post('/projects/{project_id}/sprints')
def project_create_sprint(project_id: int, payload: SprintCreateRequest) -> dict:
    return {'ok': True, 'sprint': create_project_sprint(project_id, payload)}

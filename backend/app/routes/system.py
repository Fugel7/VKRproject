import os

from fastapi import APIRouter

router = APIRouter()


@router.get('/health')
def health() -> dict:
    return {'status': 'ok'}


@router.get('/')
def root() -> dict:
    return {
        'service': 'vkr-backend',
        'env': os.getenv('APP_ENV', 'development'),
    }

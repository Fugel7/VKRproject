from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.auth import router as auth_router
from app.routes.bot import router as bot_router
from app.routes.projects import router as projects_router
from app.routes.sprints import router as sprints_router
from app.routes.system import router as system_router
from app.routes.tasks import router as tasks_router


app = FastAPI(title='VKR Backend', version='0.1.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        'http://localhost:5173',
        'http://127.0.0.1:5173',
    ],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(system_router)
app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(tasks_router)
app.include_router(sprints_router)
app.include_router(bot_router)

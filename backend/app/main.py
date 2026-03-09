import hashlib
import hmac
import json
import os
import time
import uuid
from urllib.parse import parse_qsl

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from psycopg import connect
from psycopg.errors import Error as PsycopgError
from psycopg.rows import dict_row

from app.db import get_database_url


app = FastAPI(title="VKR Backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TelegramAuthRequest(BaseModel):
    init_data: str
    start_param: str | None = None
    unsafe_chat_id: int | None = None
    unsafe_chat_type: str | None = None
    unsafe_chat_title: str | None = None


class BotChatProjectRequest(BaseModel):
    chat_id: int
    chat_type: str | None = None
    title: str | None = None


class SprintCreateRequest(BaseModel):
    tg_id: int
    title: str


class SprintUpdateRequest(BaseModel):
    tg_id: int
    title: str | None = None
    is_open: bool | None = None


class TaskCreateRequest(BaseModel):
    tg_id: int
    title: str
    description: str = ""
    deadline_at: str | None = None
    status: str | None = None
    sprint_id: int | None = None


class TaskUpdateRequest(BaseModel):
    tg_id: int
    title: str | None = None
    description: str | None = None
    deadline_at: str | None = None
    status: str | None = None
    sprint_id: int | None = None


class CommentCreateRequest(BaseModel):
    tg_id: int
    text: str


def verify_telegram_init_data(init_data: str, bot_token: str) -> dict:
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    incoming_hash = pairs.pop("hash", None)

    if not incoming_hash:
        raise HTTPException(status_code=400, detail="Missing Telegram hash")

    data_check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, incoming_hash):
        raise HTTPException(status_code=401, detail="Invalid Telegram auth signature")

    auth_date = int(pairs.get("auth_date", "0"))
    if auth_date and time.time() - auth_date > 86400:
        raise HTTPException(status_code=401, detail="Telegram auth payload expired")

    user_raw = pairs.get("user")
    if not user_raw:
        raise HTTPException(status_code=400, detail="Missing Telegram user data")

    user = json.loads(user_raw)
    context = {
        "chat_instance": pairs.get("chat_instance"),
        "chat_type": pairs.get("chat_type"),
        "start_param": pairs.get("start_param"),
    }

    chat_raw = pairs.get("chat")
    if chat_raw:
        try:
            context["chat"] = json.loads(chat_raw)
        except json.JSONDecodeError:
            context["chat"] = None

    return {"user": user, "context": context}


def save_or_update_user(telegram_user: dict) -> dict:
    tg_id = telegram_user.get("id")
    if tg_id is None:
        raise HTTPException(status_code=400, detail="Telegram user id is missing")

    try:
        with connect(get_database_url()) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO users (tg_id, username, first_name, last_name, photo_url, last_login_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (tg_id)
                    DO UPDATE SET
                        username = EXCLUDED.username,
                        first_name = EXCLUDED.first_name,
                        last_name = EXCLUDED.last_name,
                        photo_url = EXCLUDED.photo_url,
                        last_login_at = NOW()
                    RETURNING id, tg_id, username, first_name, last_name, photo_url, created_at, last_login_at;
                    """,
                    (
                        tg_id,
                        telegram_user.get("username"),
                        telegram_user.get("first_name") or "",
                        telegram_user.get("last_name"),
                        telegram_user.get("photo_url"),
                    ),
                )
                user_row = cur.fetchone()
            conn.commit()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except PsycopgError as exc:
        raise HTTPException(status_code=500, detail=f"Database error while saving user: {exc}")

    return user_row


def get_user_by_tg_id(tg_id: int) -> dict | None:
    try:
        with connect(get_database_url()) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, tg_id, username, first_name, last_name, photo_url, created_at, last_login_at
                    FROM users
                    WHERE tg_id = %s
                    LIMIT 1;
                    """,
                    (tg_id,),
                )
                return cur.fetchone()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except PsycopgError as exc:
        raise HTTPException(status_code=500, detail=f"Database error while loading user: {exc}")


def get_user_id_by_tg_id(cur, tg_id: int) -> int:
    cur.execute("SELECT id FROM users WHERE tg_id = %s LIMIT 1;", (tg_id,))
    user_row = cur.fetchone()
    if not user_row:
        raise HTTPException(status_code=404, detail="User not found")
    return user_row["id"]


def ensure_project_member(cur, project_id: int, user_id: int) -> None:
    cur.execute(
        """
        SELECT 1
        FROM project_members
        WHERE project_id = %s AND user_id = %s AND is_active = TRUE
        LIMIT 1;
        """,
        (project_id, user_id),
    )
    if not cur.fetchone():
        raise HTTPException(status_code=403, detail="Access denied for this project")


def normalize_task_status(status: str | None) -> str:
    if not status:
        return "NEW"
    status_upper = status.strip().upper()
    allowed = {"NEW", "IN_PROGRESS", "DONE"}
    if status_upper not in allowed:
        raise HTTPException(status_code=400, detail="Invalid task status")
    return status_upper


def get_projects_by_tg_id(tg_id: int) -> list[dict]:
    try:
        with connect(get_database_url()) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        p.id,
                        p.project_key,
                        p.title,
                        p.tg_chat_id,
                        p.tg_chat_instance,
                        p.tg_chat_type
                    FROM users u
                    JOIN project_members pm ON pm.user_id = u.id AND pm.is_active = TRUE
                    JOIN projects p ON p.id = pm.project_id
                    WHERE u.tg_id = %s
                    ORDER BY p.created_at DESC, p.id DESC;
                    """,
                    (tg_id,),
                )
                return cur.fetchall()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except PsycopgError as exc:
        raise HTTPException(status_code=500, detail=f"Database error while loading projects: {exc}")


def delete_project_by_tg_id(project_id: int, tg_id: int) -> dict:
    try:
        with connect(get_database_url()) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT u.id AS user_id
                    FROM users u
                    WHERE u.tg_id = %s
                    LIMIT 1;
                    """,
                    (tg_id,),
                )
                user_row = cur.fetchone()
                if not user_row:
                    raise HTTPException(status_code=404, detail="User not found")

                cur.execute(
                    """
                    SELECT 1
                    FROM project_members pm
                    WHERE pm.project_id = %s
                      AND pm.user_id = %s
                      AND pm.is_active = TRUE
                    LIMIT 1;
                    """,
                    (project_id, user_row["user_id"]),
                )
                membership = cur.fetchone()
                if not membership:
                    raise HTTPException(status_code=404, detail="Project not found in user scope")

                cur.execute(
                    """
                    DELETE FROM projects
                    WHERE id = %s
                    RETURNING id;
                    """,
                    (project_id,),
                )
                deleted = cur.fetchone()
                if not deleted:
                    raise HTTPException(status_code=404, detail="Project not found")

            conn.commit()
            return {"id": deleted["id"]}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except HTTPException:
        raise
    except PsycopgError as exc:
        raise HTTPException(status_code=500, detail=f"Database error while deleting project: {exc}")


def ensure_projects_chat_columns(cur) -> None:
    cur.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS tg_chat_instance TEXT;")
    cur.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS tg_chat_type TEXT;")
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_projects_tg_chat_id_not_null
          ON projects(tg_chat_id)
          WHERE tg_chat_id IS NOT NULL;
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_projects_tg_chat_instance_not_null
          ON projects(tg_chat_instance)
          WHERE tg_chat_instance IS NOT NULL;
        """
    )


def ensure_sprint_tables(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sprints (
          id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          title TEXT NOT NULL,
          is_open BOOLEAN NOT NULL DEFAULT TRUE,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS sprint_id BIGINT;")
    cur.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'fk_tasks_sprint'
          ) THEN
            ALTER TABLE tasks
            ADD CONSTRAINT fk_tasks_sprint
            FOREIGN KEY (sprint_id)
            REFERENCES sprints(id)
            ON DELETE SET NULL;
          END IF;
        END
        $$;
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sprints_project ON sprints(project_id, created_at DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_project_sprint ON tasks(project_id, sprint_id, updated_at DESC);")


def ensure_chat_project(chat_id: int, chat_type: str | None, title: str | None) -> dict:
    normalized_title = (title or "Новый проект").strip() or "Новый проект"
    chat_instance = str(chat_id)
    try:
        with connect(get_database_url()) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                ensure_projects_chat_columns(cur)
                cur.execute(
                    """
                    SELECT id, project_key, title, tg_chat_id, tg_chat_instance, tg_chat_type
                    FROM projects
                    WHERE tg_chat_id = %s
                    LIMIT 1;
                    """,
                    (chat_id,),
                )
                project = cur.fetchone()
                if not project:
                    cur.execute(
                        """
                        SELECT id, project_key, title, tg_chat_id, tg_chat_instance, tg_chat_type
                        FROM projects
                        WHERE tg_chat_instance = %s
                        LIMIT 1;
                        """,
                        (chat_instance,),
                    )
                    project = cur.fetchone()
                if not project:
                    cur.execute(
                        """
                        INSERT INTO projects (tg_chat_id, tg_chat_instance, tg_chat_type, title)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id, project_key, title, tg_chat_id, tg_chat_instance, tg_chat_type;
                        """,
                        (chat_id, chat_instance, chat_type, normalized_title),
                    )
                    project = cur.fetchone()
                else:
                    cur.execute(
                        """
                        UPDATE projects
                        SET
                            title = %s,
                            tg_chat_id = COALESCE(tg_chat_id, %s),
                            tg_chat_instance = COALESCE(tg_chat_instance, %s),
                            tg_chat_type = COALESCE(%s, tg_chat_type)
                        WHERE id = %s
                        RETURNING id, project_key, title, tg_chat_id, tg_chat_instance, tg_chat_type;
                        """,
                        (normalized_title, chat_id, chat_instance, chat_type, project["id"]),
                    )
                    project = cur.fetchone()
            conn.commit()
        return project
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except PsycopgError as exc:
        raise HTTPException(status_code=500, detail=f"Database error while ensuring chat project: {exc}")


def ensure_project_member_by_start_param(start_param: str | None, user_id: int) -> dict | None:
    if not start_param:
        return None
    try:
        project_key = uuid.UUID(start_param)
    except ValueError:
        return None

    try:
        with connect(get_database_url()) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, project_key, title, tg_chat_id, tg_chat_instance, tg_chat_type
                    FROM projects
                    WHERE project_key = %s
                    LIMIT 1;
                    """,
                    (str(project_key),),
                )
                project = cur.fetchone()
                if not project:
                    return None

                cur.execute(
                    """
                    INSERT INTO project_members (project_id, user_id, role, is_active)
                    VALUES (%s, %s, %s, TRUE)
                    ON CONFLICT (project_id, user_id)
                    DO UPDATE SET is_active = TRUE
                    RETURNING project_id;
                    """,
                    (project["id"], user_id, "MEMBER"),
                )
                cur.fetchone()
            conn.commit()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except PsycopgError as exc:
        raise HTTPException(status_code=500, detail=f"Database error while ensuring start_param project: {exc}")

    return {
        "id": project["id"],
        "project_key": project["project_key"],
        "title": project["title"],
        "tg_chat_id": project["tg_chat_id"],
        "tg_chat_instance": project["tg_chat_instance"],
        "tg_chat_type": project["tg_chat_type"],
    }


def ensure_chat_project_for_user(auth_context: dict, user_id: int) -> dict | None:
    chat = auth_context.get("chat") if isinstance(auth_context.get("chat"), dict) else None
    raw_tg_chat_id = chat.get("id") if chat else None
    chat_instance = auth_context.get("chat_instance")
    chat_type = auth_context.get("chat_type") or (chat.get("type") if chat else None)
    chat_title = chat.get("title") if chat else None

    tg_chat_id = None
    if raw_tg_chat_id is not None:
        try:
            tg_chat_id = int(raw_tg_chat_id)
        except (TypeError, ValueError):
            tg_chat_id = None

    if tg_chat_id is None and not chat_instance:
        return None

    title = (chat_title or "Новый проект").strip() or "Новый проект"

    try:
        with connect(get_database_url()) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                ensure_projects_chat_columns(cur)

                project = None
                if tg_chat_id is not None:
                    cur.execute(
                        """
                        SELECT id, project_key, title, tg_chat_id, tg_chat_instance, tg_chat_type
                        FROM projects
                        WHERE tg_chat_id = %s
                        LIMIT 1;
                        """,
                        (tg_chat_id,),
                    )
                    project = cur.fetchone()

                if not project and chat_instance:
                    cur.execute(
                        """
                        SELECT id, project_key, title, tg_chat_id, tg_chat_instance, tg_chat_type
                        FROM projects
                        WHERE tg_chat_instance = %s
                        LIMIT 1;
                        """,
                        (chat_instance,),
                    )
                    project = cur.fetchone()

                if project is None:
                    cur.execute(
                        """
                        INSERT INTO projects (tg_chat_id, tg_chat_instance, tg_chat_type, title)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id, project_key, title, tg_chat_id, tg_chat_instance, tg_chat_type;
                        """,
                        (tg_chat_id, chat_instance, chat_type, title),
                    )
                    project = cur.fetchone()
                else:
                    cur.execute(
                        """
                        UPDATE projects
                        SET
                            title = %s,
                            tg_chat_id = COALESCE(tg_chat_id, %s),
                            tg_chat_instance = COALESCE(tg_chat_instance, %s),
                            tg_chat_type = COALESCE(%s, tg_chat_type)
                        WHERE id = %s
                        RETURNING id, project_key, title, tg_chat_id, tg_chat_instance, tg_chat_type;
                        """,
                        (title, tg_chat_id, chat_instance, chat_type, project["id"]),
                    )
                    project = cur.fetchone()

                cur.execute(
                    """
                    INSERT INTO project_members (project_id, user_id, role, is_active)
                    VALUES (%s, %s, %s, TRUE)
                    ON CONFLICT (project_id, user_id)
                    DO UPDATE SET is_active = TRUE
                    RETURNING project_id;
                    """,
                    (project["id"], user_id, "MEMBER"),
                )
                cur.fetchone()

            conn.commit()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except PsycopgError as exc:
        raise HTTPException(status_code=500, detail=f"Database error while ensuring chat project: {exc}")

    return {
        "id": project["id"],
        "project_key": project["project_key"],
        "title": project["title"],
        "tg_chat_id": project["tg_chat_id"],
        "tg_chat_instance": project["tg_chat_instance"],
        "tg_chat_type": project["tg_chat_type"],
    }


def list_project_tasks(project_id: int, tg_id: int) -> list[dict]:
    try:
        with connect(get_database_url()) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                ensure_sprint_tables(cur)
                user_id = get_user_id_by_tg_id(cur, tg_id)
                ensure_project_member(cur, project_id, user_id)
                cur.execute(
                    """
                    SELECT
                      t.id,
                      t.project_id,
                      t.sprint_id,
                      t.title,
                      t.description,
                      t.status,
                      t.deadline_at,
                      t.created_at,
                      t.updated_at
                    FROM tasks t
                    WHERE t.project_id = %s
                    ORDER BY t.updated_at DESC, t.id DESC;
                    """,
                    (project_id,),
                )
                return cur.fetchall()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except HTTPException:
        raise
    except PsycopgError as exc:
        raise HTTPException(status_code=500, detail=f"Database error while loading tasks: {exc}")


def list_project_sprints(project_id: int, tg_id: int) -> list[dict]:
    try:
        with connect(get_database_url()) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                ensure_sprint_tables(cur)
                user_id = get_user_id_by_tg_id(cur, tg_id)
                ensure_project_member(cur, project_id, user_id)
                cur.execute(
                    """
                    SELECT id, project_id, title, is_open, created_at
                    FROM sprints
                    WHERE project_id = %s
                    ORDER BY created_at DESC, id DESC;
                    """,
                    (project_id,),
                )
                return cur.fetchall()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except HTTPException:
        raise
    except PsycopgError as exc:
        raise HTTPException(status_code=500, detail=f"Database error while loading sprints: {exc}")


def create_project_sprint(project_id: int, payload: SprintCreateRequest) -> dict:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Sprint title is required")
    try:
        with connect(get_database_url()) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                ensure_sprint_tables(cur)
                user_id = get_user_id_by_tg_id(cur, payload.tg_id)
                ensure_project_member(cur, project_id, user_id)
                cur.execute(
                    """
                    INSERT INTO sprints (project_id, title, is_open)
                    VALUES (%s, %s, TRUE)
                    RETURNING id, project_id, title, is_open, created_at;
                    """,
                    (project_id, title),
                )
                sprint = cur.fetchone()
            conn.commit()
            return sprint
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except HTTPException:
        raise
    except PsycopgError as exc:
        raise HTTPException(status_code=500, detail=f"Database error while creating sprint: {exc}")


def update_sprint(sprint_id: int, payload: SprintUpdateRequest) -> dict:
    if payload.title is None and payload.is_open is None:
        raise HTTPException(status_code=400, detail="No sprint fields to update")
    try:
        with connect(get_database_url()) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                ensure_sprint_tables(cur)
                user_id = get_user_id_by_tg_id(cur, payload.tg_id)
                cur.execute("SELECT project_id FROM sprints WHERE id = %s LIMIT 1;", (sprint_id,))
                sprint_row = cur.fetchone()
                if not sprint_row:
                    raise HTTPException(status_code=404, detail="Sprint not found")
                ensure_project_member(cur, sprint_row["project_id"], user_id)
                cur.execute(
                    """
                    UPDATE sprints
                    SET
                      title = COALESCE(%s, title),
                      is_open = COALESCE(%s, is_open)
                    WHERE id = %s
                    RETURNING id, project_id, title, is_open, created_at;
                    """,
                    (payload.title.strip() if payload.title is not None else None, payload.is_open, sprint_id),
                )
                updated = cur.fetchone()
            conn.commit()
            return updated
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except HTTPException:
        raise
    except PsycopgError as exc:
        raise HTTPException(status_code=500, detail=f"Database error while updating sprint: {exc}")


def create_project_task(project_id: int, payload: TaskCreateRequest) -> dict:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Task title is required")
    status = normalize_task_status(payload.status)
    try:
        with connect(get_database_url()) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                ensure_sprint_tables(cur)
                user_id = get_user_id_by_tg_id(cur, payload.tg_id)
                ensure_project_member(cur, project_id, user_id)
                if payload.sprint_id is not None:
                    cur.execute(
                        "SELECT 1 FROM sprints WHERE id = %s AND project_id = %s LIMIT 1;",
                        (payload.sprint_id, project_id),
                    )
                    if not cur.fetchone():
                        raise HTTPException(status_code=404, detail="Sprint not found in this project")
                cur.execute(
                    """
                    INSERT INTO tasks (
                      project_id, sprint_id, title, description, status, author_id, assignee_id, deadline_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, project_id, sprint_id, title, description, status, deadline_at, created_at, updated_at;
                    """,
                    (
                        project_id,
                        payload.sprint_id,
                        title,
                        payload.description or "",
                        status,
                        user_id,
                        user_id,
                        payload.deadline_at,
                    ),
                )
                task = cur.fetchone()
            conn.commit()
            return task
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except HTTPException:
        raise
    except PsycopgError as exc:
        raise HTTPException(status_code=500, detail=f"Database error while creating task: {exc}")


def update_task(task_id: int, payload: TaskUpdateRequest) -> dict:
    if (
        payload.title is None
        and payload.description is None
        and payload.deadline_at is None
        and payload.status is None
        and payload.sprint_id is None
    ):
        raise HTTPException(status_code=400, detail="No task fields to update")
    status = normalize_task_status(payload.status) if payload.status is not None else None
    fields_set = payload.model_fields_set
    sprint_value = payload.sprint_id if "sprint_id" in fields_set else "__KEEP__"
    deadline_value = payload.deadline_at if "deadline_at" in fields_set else "__KEEP__"
    try:
        with connect(get_database_url()) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                ensure_sprint_tables(cur)
                user_id = get_user_id_by_tg_id(cur, payload.tg_id)
                cur.execute("SELECT id, project_id FROM tasks WHERE id = %s LIMIT 1;", (task_id,))
                task_row = cur.fetchone()
                if not task_row:
                    raise HTTPException(status_code=404, detail="Task not found")
                project_id = task_row["project_id"]
                ensure_project_member(cur, project_id, user_id)
                if payload.sprint_id is not None:
                    cur.execute(
                        "SELECT 1 FROM sprints WHERE id = %s AND project_id = %s LIMIT 1;",
                        (payload.sprint_id, project_id),
                    )
                    if not cur.fetchone():
                        raise HTTPException(status_code=404, detail="Sprint not found in this project")
                cur.execute(
                    """
                    UPDATE tasks
                    SET
                      title = COALESCE(%s, title),
                      description = COALESCE(%s, description),
                      deadline_at = CASE WHEN %s THEN %s ELSE deadline_at END,
                      status = COALESCE(%s, status),
                      sprint_id = CASE WHEN %s THEN %s ELSE sprint_id END
                    WHERE id = %s
                    RETURNING id, project_id, sprint_id, title, description, status, deadline_at, created_at, updated_at;
                    """,
                    (
                        payload.title.strip() if payload.title is not None else None,
                        payload.description,
                        deadline_value != "__KEEP__",
                        None if deadline_value == "__KEEP__" else deadline_value,
                        status,
                        sprint_value != "__KEEP__",
                        None if sprint_value == "__KEEP__" else sprint_value,
                        task_id,
                    ),
                )
                updated = cur.fetchone()
            conn.commit()
            return updated
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except HTTPException:
        raise
    except PsycopgError as exc:
        raise HTTPException(status_code=500, detail=f"Database error while updating task: {exc}")


def list_task_comments(task_id: int, tg_id: int) -> list[dict]:
    try:
        with connect(get_database_url()) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                ensure_sprint_tables(cur)
                user_id = get_user_id_by_tg_id(cur, tg_id)
                cur.execute("SELECT project_id FROM tasks WHERE id = %s LIMIT 1;", (task_id,))
                task_row = cur.fetchone()
                if not task_row:
                    raise HTTPException(status_code=404, detail="Task not found")
                ensure_project_member(cur, task_row["project_id"], user_id)
                cur.execute(
                    """
                    SELECT
                      c.id,
                      c.task_id,
                      c.text,
                      c.created_at,
                      u.id AS author_id,
                      u.first_name,
                      u.last_name,
                      u.username
                    FROM comments c
                    JOIN users u ON u.id = c.author_id
                    WHERE c.task_id = %s
                    ORDER BY c.created_at ASC, c.id ASC;
                    """,
                    (task_id,),
                )
                return cur.fetchall()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except HTTPException:
        raise
    except PsycopgError as exc:
        raise HTTPException(status_code=500, detail=f"Database error while loading comments: {exc}")


def create_task_comment(task_id: int, payload: CommentCreateRequest) -> dict:
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Comment text is required")
    try:
        with connect(get_database_url()) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                ensure_sprint_tables(cur)
                user_id = get_user_id_by_tg_id(cur, payload.tg_id)
                cur.execute("SELECT project_id FROM tasks WHERE id = %s LIMIT 1;", (task_id,))
                task_row = cur.fetchone()
                if not task_row:
                    raise HTTPException(status_code=404, detail="Task not found")
                ensure_project_member(cur, task_row["project_id"], user_id)
                cur.execute(
                    """
                    INSERT INTO comments (task_id, author_id, text)
                    VALUES (%s, %s, %s)
                    RETURNING id, task_id, text, created_at;
                    """,
                    (task_id, user_id, text),
                )
                comment = cur.fetchone()
            conn.commit()
            return comment
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except HTTPException:
        raise
    except PsycopgError as exc:
        raise HTTPException(status_code=500, detail=f"Database error while creating comment: {exc}")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/")
def root() -> dict:
    return {
        "service": "vkr-backend",
        "env": os.getenv("APP_ENV", "development"),
    }


@app.get("/me")
def me(tg_id: int) -> dict:
    user = get_user_by_tg_id(tg_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True, "user": user}


@app.get("/projects")
def projects(tg_id: int) -> dict:
    return {"ok": True, "projects": get_projects_by_tg_id(tg_id)}


@app.get("/projects/{project_id}/tasks")
def project_tasks(project_id: int, tg_id: int) -> dict:
    return {"ok": True, "tasks": list_project_tasks(project_id, tg_id)}


@app.post("/projects/{project_id}/tasks")
def project_create_task(project_id: int, payload: TaskCreateRequest) -> dict:
    return {"ok": True, "task": create_project_task(project_id, payload)}


@app.patch("/tasks/{task_id}")
def patch_task(task_id: int, payload: TaskUpdateRequest) -> dict:
    return {"ok": True, "task": update_task(task_id, payload)}


@app.get("/tasks/{task_id}/comments")
def task_comments(task_id: int, tg_id: int) -> dict:
    return {"ok": True, "comments": list_task_comments(task_id, tg_id)}


@app.post("/tasks/{task_id}/comments")
def create_comment(task_id: int, payload: CommentCreateRequest) -> dict:
    return {"ok": True, "comment": create_task_comment(task_id, payload)}


@app.get("/projects/{project_id}/sprints")
def project_sprints(project_id: int, tg_id: int) -> dict:
    return {"ok": True, "sprints": list_project_sprints(project_id, tg_id)}


@app.post("/projects/{project_id}/sprints")
def project_create_sprint(project_id: int, payload: SprintCreateRequest) -> dict:
    return {"ok": True, "sprint": create_project_sprint(project_id, payload)}


@app.patch("/sprints/{sprint_id}")
def patch_sprint(sprint_id: int, payload: SprintUpdateRequest) -> dict:
    return {"ok": True, "sprint": update_sprint(sprint_id, payload)}


@app.post("/auth/telegram")
def auth_telegram(payload: TelegramAuthRequest) -> dict:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise HTTPException(status_code=503, detail="TELEGRAM_BOT_TOKEN is not configured")

    verified = verify_telegram_init_data(payload.init_data, bot_token)
    user = verified["user"]
    context = verified["context"]
    # Fallback: Telegram may omit chat fields in signed init_data for some launch paths.
    # Backfill missing metadata from WebApp unsafe fields.
    existing_chat = context.get("chat") if isinstance(context.get("chat"), dict) else {}
    fallback_chat = {
        "id": existing_chat.get("id") if existing_chat.get("id") is not None else payload.unsafe_chat_id,
        "type": existing_chat.get("type") or payload.unsafe_chat_type or context.get("chat_type"),
        "title": existing_chat.get("title") or payload.unsafe_chat_title,
    }
    if any(value is not None for value in fallback_chat.values()):
        context["chat"] = fallback_chat
    if not context.get("chat_type") and payload.unsafe_chat_type:
        context["chat_type"] = payload.unsafe_chat_type
    if not context.get("start_param") and payload.start_param:
        context["start_param"] = payload.start_param
    db_user = save_or_update_user(user)
    active_project = ensure_project_member_by_start_param(context.get("start_param"), db_user["id"])
    if active_project is None:
        active_project = ensure_chat_project_for_user(context, db_user["id"])
    return {
        "ok": True,
        "user": user,
        "db_user": db_user,
        "active_project": active_project,
        "launched_from_chat": active_project is not None,
    }


@app.post("/bot/chat-project")
def bot_chat_project(payload: BotChatProjectRequest, x_bot_token: str | None = Header(default=None)) -> dict:
    expected_token = os.getenv("BOT_INTERNAL_TOKEN")
    if not expected_token:
        raise HTTPException(status_code=503, detail="BOT_INTERNAL_TOKEN is not configured")
    if not x_bot_token or x_bot_token != expected_token:
        raise HTTPException(status_code=401, detail="Invalid bot token")

    project = ensure_chat_project(payload.chat_id, payload.chat_type, payload.title)
    return {"ok": True, "project": project}


@app.delete("/projects/{project_id}")
def delete_project(project_id: int, tg_id: int) -> dict:
    deleted = delete_project_by_tg_id(project_id, tg_id)
    return {"ok": True, "deleted_project_id": deleted["id"]}

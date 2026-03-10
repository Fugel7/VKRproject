import hashlib
import hmac
import json
import os
import re
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl
from urllib.request import Request, urlopen

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


class BotIngestMessageRequest(BaseModel):
    chat_id: int
    chat_type: str | None = None
    title: str | None = None
    user_tg_id: int
    user_username: str | None = None
    user_first_name: str | None = None
    user_last_name: str | None = None
    content_text: str
    source_type: str | None = None
    attachment_kind: str | None = None
    attachment_mime: str | None = None
    attachment_base64: str | None = None


class SprintCreateRequest(BaseModel):
    tg_id: int
    title: str
    start_date: str | None = None
    end_date: str | None = None


class SprintUpdateRequest(BaseModel):
    tg_id: int
    title: str | None = None
    is_open: bool | None = None
    start_date: str | None = None
    end_date: str | None = None


class TaskCreateRequest(BaseModel):
    tg_id: int
    title: str
    description: str = ""
    execution_hours: int | None = None
    status: str | None = None
    sprint_id: int | None = None


class TaskUpdateRequest(BaseModel):
    tg_id: int
    title: str | None = None
    description: str | None = None
    execution_hours: int | None = None
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
          start_date DATE,
          end_date DATE,
          is_open BOOLEAN NOT NULL DEFAULT TRUE,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    cur.execute("ALTER TABLE sprints ADD COLUMN IF NOT EXISTS start_date DATE;")
    cur.execute("ALTER TABLE sprints ADD COLUMN IF NOT EXISTS end_date DATE;")
    cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS sprint_id BIGINT;")
    cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS execution_hours INTEGER;")
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
        EXCEPTION
          WHEN duplicate_object THEN
            NULL;
        END
        $$;
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sprints_project ON sprints(project_id, created_at DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_project_sprint ON tasks(project_id, sprint_id, updated_at DESC);")


def ensure_task_comment_reads_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS task_comment_reads (
          task_id BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
          user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          last_read_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (task_id, user_id)
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_task_comment_reads_user ON task_comment_reads(user_id, task_id);")


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
                ensure_task_comment_reads_table(cur)
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
                      t.execution_hours,
                      COALESCE(cs.comment_count, 0) AS comment_count,
                      cs.last_comment_at,
                      COALESCE(cs.unread_comment_count, 0) AS unread_comment_count,
                      t.created_at,
                      t.updated_at
                    FROM tasks t
                    LEFT JOIN LATERAL (
                      SELECT
                        COUNT(*)::INT AS comment_count,
                        MAX(c.created_at) AS last_comment_at,
                        COUNT(*) FILTER (
                          WHERE c.created_at > COALESCE(tcr.last_read_at, TO_TIMESTAMP(0))
                        )::INT AS unread_comment_count
                      FROM comments c
                      LEFT JOIN task_comment_reads tcr
                        ON tcr.task_id = t.id
                       AND tcr.user_id = %s
                      WHERE c.task_id = t.id
                    ) cs ON TRUE
                    WHERE t.project_id = %s
                    ORDER BY t.updated_at DESC, t.id DESC;
                    """,
                    (user_id, project_id),
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
                    SELECT id, project_id, title, start_date, end_date, is_open, created_at
                    FROM sprints
                    WHERE project_id = %s
                    ORDER BY created_at ASC, id ASC;
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
                    INSERT INTO sprints (project_id, title, start_date, end_date, is_open)
                    VALUES (%s, %s, %s, %s, TRUE)
                    RETURNING id, project_id, title, start_date, end_date, is_open, created_at;
                    """,
                    (project_id, title, payload.start_date, payload.end_date),
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
    if payload.title is None and payload.is_open is None and payload.start_date is None and payload.end_date is None:
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
                      start_date = COALESCE(%s, start_date),
                      end_date = COALESCE(%s, end_date),
                      is_open = COALESCE(%s, is_open)
                    WHERE id = %s
                    RETURNING id, project_id, title, start_date, end_date, is_open, created_at;
                    """,
                    (
                        payload.title.strip() if payload.title is not None else None,
                        payload.start_date,
                        payload.end_date,
                        payload.is_open,
                        sprint_id,
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
        raise HTTPException(status_code=500, detail=f"Database error while updating sprint: {exc}")


def delete_sprint(sprint_id: int, tg_id: int) -> dict:
    try:
        with connect(get_database_url()) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                ensure_sprint_tables(cur)
                user_id = get_user_id_by_tg_id(cur, tg_id)
                cur.execute("SELECT project_id FROM sprints WHERE id = %s LIMIT 1;", (sprint_id,))
                sprint_row = cur.fetchone()
                if not sprint_row:
                    raise HTTPException(status_code=404, detail="Sprint not found")
                ensure_project_member(cur, sprint_row["project_id"], user_id)
                cur.execute("DELETE FROM sprints WHERE id = %s RETURNING id;", (sprint_id,))
                deleted = cur.fetchone()
            conn.commit()
            return deleted or {"id": sprint_id}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except HTTPException:
        raise
    except PsycopgError as exc:
        raise HTTPException(status_code=500, detail=f"Database error while deleting sprint: {exc}")


def create_project_task(project_id: int, payload: TaskCreateRequest) -> dict:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Task title is required")
    status = normalize_task_status(payload.status)
    if payload.execution_hours is not None and payload.execution_hours <= 0:
        raise HTTPException(status_code=400, detail="Execution hours must be greater than zero")
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
                      project_id, sprint_id, title, description, status, author_id, assignee_id, execution_hours
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, project_id, sprint_id, title, description, status, execution_hours, created_at, updated_at;
                    """,
                    (
                        project_id,
                        payload.sprint_id,
                        title,
                        payload.description or "",
                        status,
                        user_id,
                        user_id,
                        payload.execution_hours,
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


def _extract_json_object(raw_text: str) -> dict:
    text = (raw_text or "").strip()
    if not text:
        raise HTTPException(status_code=502, detail="OpenRouter returned empty content")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            raise HTTPException(status_code=502, detail="OpenRouter returned non-JSON response")
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=502, detail="Failed to parse OpenRouter JSON output") from exc


def _extract_openrouter_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts).strip()
    return ""


def _coerce_hours(raw_value) -> int | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, (int, float)):
        value = int(round(float(raw_value)))
    else:
        digits = "".join(ch for ch in str(raw_value) if ch.isdigit())
        if not digits:
            return None
        value = int(digits)
    if value <= 0:
        return None
    return min(value, 999)


def _normalize_ai_tasks(items: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        description = str(item.get("description") or "").strip()
        raw_status = item.get("status")
        try:
            status = normalize_task_status(raw_status if isinstance(raw_status, str) else None)
        except HTTPException:
            status = "NEW"
        normalized.append(
            {
                "title": title[:180],
                "description": description,
                "execution_hours": _coerce_hours(item.get("execution_hours")),
                "status": status,
            }
        )
    return normalized[:15]


def _split_text_to_clauses(text: str) -> list[str]:
    rough_parts = re.split(r"[\n\r;,.!?]+", text or "")
    clauses: list[str] = []
    for part in rough_parts:
        if not part.strip():
            continue
        subparts = re.split(r"\b(?:и|а|но|затем|потом)\b", part, flags=re.IGNORECASE)
        for subpart in subparts:
            cleaned = subpart.strip(" -:\t")
            if cleaned:
                clauses.append(cleaned)
    return clauses


def _extract_tasks_by_rules(text: str) -> list[dict]:
    action_markers = (
        "сделай", "сделать", "добавь", "добавить", "исправь", "исправить", "поправь", "поправить",
        "измени", "изменить", "обнови", "обновить", "удали", "удалить", "создай", "создать",
        "реализуй", "реализовать", "настрой", "настроить", "почини", "починить", "нужно", "надо",
        "необходимо", "требуется",
    )
    project_markers = (
        "страниц", "карточк", "сайт", "лендинг", "интерфейс", "ui", "ux", "верстк", "макет",
        "фронтенд", "frontend", "бэкенд", "backend", "api", "endpoint", "роут", "кнопк", "форма",
        "модал", "таблиц", "база", "проект", "задач", "баг", "ошибк", "фильтр", "поиск", "авторизац",
        "товар",
    )
    tasks: list[dict] = []
    for clause in _split_text_to_clauses(text):
        lowered = clause.lower()
        has_action = any(marker in lowered for marker in action_markers)
        has_project = any(marker in lowered for marker in project_markers)
        if not has_action:
            continue
        if not has_project:
            continue

        title = re.sub(
            r"^\s*(?:надо(?: бы)?|нужно|необходимо|требуется|не забыть бы|пожалуйста)\s+",
            "",
            clause,
            flags=re.IGNORECASE,
        )
        title = re.sub(
            r"^\s*(?:сделай|сделать|добавь|добавить|исправь|исправить|измени|изменить|обнови|обновить|создай|создать|удали|удалить|реализуй|реализовать|настрой|настроить|почини|починить)\s+",
            "",
            title,
            flags=re.IGNORECASE,
        ).strip(" .,:;-")
        if not title:
            continue
        if len(title) > 180:
            title = title[:180].rstrip()

        tasks.append(
            {
                "title": title[:1].upper() + title[1:] if title else title,
                "description": clause.strip(),
                "execution_hours": None,
                "status": "NEW",
            }
        )
    return tasks[:15]
def extract_tasks_via_openrouter(
    content_text: str,
    project_title: str,
    attachment_kind: str | None = None,
    attachment_mime: str | None = None,
    attachment_base64: str | None = None,
) -> list[dict]:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENROUTER_API_KEY is not configured")
    text_model = os.getenv("OPENROUTER_MODEL", "openrouter/free").strip() or "openrouter/free"
    vision_model = os.getenv("OPENROUTER_VISION_MODEL", "").strip() or text_model
    fallback_models = [
        item.strip()
        for item in os.getenv("OPENROUTER_FALLBACK_MODELS", "").split(",")
        if item.strip()
    ]
    prompt = (
        "You extract project tasks from user messages for a task tracker. "
        "Return ONLY one JSON object with exact schema: "
        '{"tasks":[{"title":"string","description":"string","execution_hours":number|null,"status":"NEW|IN_PROGRESS|DONE"}]}. '
        "Rules: "
        "1) Include ONLY tasks clearly related to the current project context. "
        "2) Ignore personal, household, off-topic, joke, or unrelated requests. "
        "3) If a message mixes related and unrelated items, keep only related items. "
        "4) If project context is weak or generic, treat software/product tasks as related "
        "(site/app/bot/frontend/backend/api/design/content/analytics/integration/testing). "
        "5) If no related tasks exist, return {\"tasks\":[]}. "
        "6) In mixed messages like 'make tea and add checkout page', keep only the software task. "
        "7) title and description must be in Russian. If source text is another language, translate to Russian. "
        "8) Keep titles short and specific. "
        "9) execution_hours should be realistic integer estimate or null if uncertain. "
        "10) Do not output markdown or any extra text."
    )
    user_text = f"Project title: {project_title}\n\nUser message:\n{content_text}"
    user_content: str | list[dict] = user_text
    if (
        attachment_kind == "image"
        and attachment_base64
        and attachment_mime
        and attachment_mime.startswith("image/")
    ):
        user_content = [
            {"type": "text", "text": user_text + "\n\nAlso analyze the attached image content."},
            {
                "type": "image_url",
                "image_url": {"url": f"data:{attachment_mime};base64,{attachment_base64}"},
            },
        ]

    def build_request_body(use_system_prompt: bool, model_name: str, use_image: bool) -> dict:
        current_user_content: str | list[dict]
        if use_image:
            current_user_content = user_content
        else:
            current_user_content = user_text
        if use_system_prompt:
            return {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": current_user_content},
                ],
                "temperature": 0.1,
            }
        if isinstance(current_user_content, list):
            merged_content = [{"type": "text", "text": prompt}] + current_user_content
        else:
            merged_content = f"{prompt}\n\n{current_user_content}"
        return {
            "model": model_name,
            "messages": [{"role": "user", "content": merged_content}],
            "temperature": 0.1,
        }

    def send_request(request_body: dict) -> dict:
        req = Request(
            url="https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(request_body).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        with urlopen(req, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))

    def try_models(use_image: bool, models: list[str]) -> tuple[dict | None, str | None]:
        last_error: str | None = None
        for model_name in models:
            try:
                return send_request(build_request_body(use_system_prompt=True, model_name=model_name, use_image=use_image)), None
            except HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code == 400 and "Developer instruction is not enabled" in body:
                    try:
                        return (
                            send_request(
                                build_request_body(use_system_prompt=False, model_name=model_name, use_image=use_image)
                            ),
                            None,
                        )
                    except HTTPError as inner_exc:
                        inner_body = inner_exc.read().decode("utf-8", errors="replace")
                        last_error = f"OpenRouter error {inner_exc.code}: {inner_body}"
                        continue
                    except URLError as inner_exc:
                        last_error = f"OpenRouter is unreachable: {inner_exc}"
                        continue
                    except json.JSONDecodeError:
                        last_error = "OpenRouter response is not valid JSON"
                        continue
                last_error = f"OpenRouter error {exc.code}: {body}"
                continue
            except URLError as exc:
                last_error = f"OpenRouter is unreachable: {exc}"
                continue
            except json.JSONDecodeError:
                last_error = "OpenRouter response is not valid JSON"
                continue
        return None, last_error

    has_image = isinstance(user_content, list)
    model_candidates = [vision_model] + [m for m in fallback_models if m != vision_model]
    parsed, request_error = try_models(use_image=has_image, models=model_candidates)
    if parsed is None and has_image and content_text.strip():
        text_candidates = [text_model] + [m for m in fallback_models if m != text_model]
        parsed, request_error = try_models(use_image=False, models=text_candidates)
    if parsed is None:
        raise HTTPException(status_code=502, detail=request_error or "OpenRouter request failed")

    error_payload = parsed.get("error")
    if isinstance(error_payload, dict):
        error_message = str(error_payload.get("message") or "").strip()
        if error_message:
            raise HTTPException(status_code=502, detail=f"OpenRouter error: {error_message}")
        raise HTTPException(status_code=502, detail="OpenRouter returned an error payload")

    choices = parsed.get("choices")
    if not isinstance(choices, list) or not choices:
        return []
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    content_text_raw = _extract_openrouter_text(content)
    if not content_text_raw.strip():
        return []
    try:
        payload = _extract_json_object(content_text_raw)
    except HTTPException:
        return []
    tasks = payload.get("tasks") if isinstance(payload, dict) else None
    if not isinstance(tasks, list):
        return []
    return _normalize_ai_tasks(tasks)


def create_bot_tasks_from_message(payload: BotIngestMessageRequest) -> dict:
    text = payload.content_text.strip()
    has_image = (
        payload.attachment_kind == "image"
        and bool(payload.attachment_base64)
        and bool(payload.attachment_mime)
    )
    if not text and not has_image:
        raise HTTPException(status_code=400, detail="Message content is empty")
    if len(text) > 12000:
        text = text[:12000]

    project_title = payload.title or "Новый проект"
    project = ensure_chat_project(payload.chat_id, payload.chat_type, project_title)
    save_or_update_user(
        {
            "id": payload.user_tg_id,
            "username": payload.user_username,
            "first_name": payload.user_first_name or "",
            "last_name": payload.user_last_name,
            "photo_url": None,
        }
    )

    try:
        with connect(get_database_url()) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                user_id = get_user_id_by_tg_id(cur, payload.user_tg_id)
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
        raise HTTPException(status_code=500, detail=f"Database error while linking user to project: {exc}")

    extracted_tasks = extract_tasks_via_openrouter(
        text,
        project.get("title") or project_title,
        payload.attachment_kind,
        payload.attachment_mime,
        payload.attachment_base64,
    )
    if not extracted_tasks:
        extracted_tasks = _extract_tasks_by_rules(text)
    created_tasks = []
    for task in extracted_tasks:
        created = create_project_task(
            project["id"],
            TaskCreateRequest(
                tg_id=payload.user_tg_id,
                title=task["title"],
                description=task["description"],
                execution_hours=task["execution_hours"],
                status=task["status"],
                sprint_id=None,
            ),
        )
        created_tasks.append(created)

    return {
        "project": project,
        "created_tasks": created_tasks,
        "created_count": len(created_tasks),
        "source_type": payload.source_type or "text",
    }


def update_task(task_id: int, payload: TaskUpdateRequest) -> dict:
    if (
        payload.title is None
        and payload.description is None
        and payload.execution_hours is None
        and payload.status is None
        and payload.sprint_id is None
    ):
        raise HTTPException(status_code=400, detail="No task fields to update")
    status = normalize_task_status(payload.status) if payload.status is not None else None
    fields_set = payload.model_fields_set
    sprint_value = payload.sprint_id if "sprint_id" in fields_set else "__KEEP__"
    execution_hours_value = payload.execution_hours if "execution_hours" in fields_set else "__KEEP__"
    if execution_hours_value != "__KEEP__" and execution_hours_value is not None and execution_hours_value <= 0:
        raise HTTPException(status_code=400, detail="Execution hours must be greater than zero")
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
                      execution_hours = CASE WHEN %s THEN %s ELSE execution_hours END,
                      status = COALESCE(%s, status),
                      sprint_id = CASE WHEN %s THEN %s ELSE sprint_id END
                    WHERE id = %s
                    RETURNING id, project_id, sprint_id, title, description, status, execution_hours, created_at, updated_at;
                    """,
                    (
                        payload.title.strip() if payload.title is not None else None,
                        payload.description,
                        execution_hours_value != "__KEEP__",
                        None if execution_hours_value == "__KEEP__" else execution_hours_value,
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


def delete_task(task_id: int, tg_id: int) -> dict:
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
                cur.execute("DELETE FROM tasks WHERE id = %s RETURNING id;", (task_id,))
                deleted = cur.fetchone()
            conn.commit()
            return deleted or {"id": task_id}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except HTTPException:
        raise
    except PsycopgError as exc:
        raise HTTPException(status_code=500, detail=f"Database error while deleting task: {exc}")


def list_task_comments(task_id: int, tg_id: int) -> list[dict]:
    try:
        with connect(get_database_url()) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                ensure_sprint_tables(cur)
                ensure_task_comment_reads_table(cur)
                user_id = get_user_id_by_tg_id(cur, tg_id)
                cur.execute("SELECT project_id FROM tasks WHERE id = %s LIMIT 1;", (task_id,))
                task_row = cur.fetchone()
                if not task_row:
                    raise HTTPException(status_code=404, detail="Task not found")
                ensure_project_member(cur, task_row["project_id"], user_id)
                cur.execute(
                    """
                    INSERT INTO task_comment_reads (task_id, user_id, last_read_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (task_id, user_id)
                    DO UPDATE SET last_read_at = EXCLUDED.last_read_at;
                    """,
                    (task_id, user_id),
                )
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


@app.delete("/tasks/{task_id}")
def remove_task(task_id: int, tg_id: int) -> dict:
    deleted = delete_task(task_id, tg_id)
    return {"ok": True, "deleted_task_id": deleted["id"]}


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


@app.delete("/sprints/{sprint_id}")
def remove_sprint(sprint_id: int, tg_id: int) -> dict:
    deleted = delete_sprint(sprint_id, tg_id)
    return {"ok": True, "deleted_sprint_id": deleted["id"]}


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


@app.post("/bot/ingest-message")
def bot_ingest_message(payload: BotIngestMessageRequest, x_bot_token: str | None = Header(default=None)) -> dict:
    expected_token = os.getenv("BOT_INTERNAL_TOKEN")
    if not expected_token:
        raise HTTPException(status_code=503, detail="BOT_INTERNAL_TOKEN is not configured")
    if not x_bot_token or x_bot_token != expected_token:
        raise HTTPException(status_code=401, detail="Invalid bot token")
    result = create_bot_tasks_from_message(payload)
    return {"ok": True, **result}


@app.delete("/projects/{project_id}")
def delete_project(project_id: int, tg_id: int) -> dict:
    deleted = delete_project_by_tg_id(project_id, tg_id)
    return {"ok": True, "deleted_project_id": deleted["id"]}







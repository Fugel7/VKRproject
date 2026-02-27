import hashlib
import hmac
import json
import os
import time
from urllib.parse import parse_qsl

from fastapi import FastAPI, HTTPException
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
    unsafe_chat_id: int | None = None
    unsafe_chat_type: str | None = None
    unsafe_chat_title: str | None = None


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
                        p.tg_chat_type,
                        pm.role
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
                    SELECT pm.role
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
                if membership["role"] != "OWNER":
                    raise HTTPException(status_code=403, detail="Only project owner can delete project")

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

                is_new_project = project is None
                if is_new_project:
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

                default_role = "OWNER" if is_new_project else "MEMBER"
                cur.execute(
                    """
                    INSERT INTO project_members (project_id, user_id, role, is_active)
                    VALUES (%s, %s, %s, TRUE)
                    ON CONFLICT (project_id, user_id)
                    DO UPDATE SET is_active = TRUE
                    RETURNING role;
                    """,
                    (project["id"], user_id, default_role),
                )
                member_row = cur.fetchone()

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
        "role": member_row["role"] if member_row else None,
    }


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
    db_user = save_or_update_user(user)
    active_project = ensure_chat_project_for_user(context, db_user["id"])
    return {
        "ok": True,
        "user": user,
        "db_user": db_user,
        "active_project": active_project,
        "launched_from_chat": active_project is not None,
    }


@app.delete("/projects/{project_id}")
def delete_project(project_id: int, tg_id: int) -> dict:
    deleted = delete_project_by_tg_id(project_id, tg_id)
    return {"ok": True, "deleted_project_id": deleted["id"]}

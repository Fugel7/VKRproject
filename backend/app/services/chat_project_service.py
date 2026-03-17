import uuid

from fastapi import HTTPException
from psycopg import connect
from psycopg.errors import Error as PsycopgError
from psycopg.rows import dict_row

from app.db import get_database_url
from app.db_helpers import ensure_projects_chat_columns


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

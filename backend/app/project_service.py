from fastapi import HTTPException
from psycopg import connect
from psycopg.errors import Error as PsycopgError
from psycopg.rows import dict_row

from app.db import get_database_url


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

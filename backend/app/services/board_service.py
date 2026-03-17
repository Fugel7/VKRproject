import json

from fastapi import HTTPException
from psycopg import connect
from psycopg.errors import Error as PsycopgError
from psycopg.rows import dict_row

from app.ai_extraction import extract_tasks_by_rules, extract_tasks_via_openrouter
from app.auth_service import save_or_update_user
from app.db import get_database_url
from app.db_helpers import (
    add_task_audit_entry,
    ensure_sprint_tables,
    ensure_task_audit_table,
    ensure_task_comment_reads_table,
    normalize_task_status,
)
from app.project_service import ensure_project_member, get_user_id_by_tg_id
from app.schemas import BotIngestMessageRequest, CommentCreateRequest, SprintCreateRequest, SprintUpdateRequest, TaskCreateRequest, TaskUpdateRequest
from app.services.chat_project_service import ensure_chat_project


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
                      t.version,
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
                ensure_task_audit_table(cur)
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
                      project_id, sprint_id, title, description, status, author_id, assignee_id, execution_hours, version
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1)
                    RETURNING id, project_id, sprint_id, version, title, description, status, execution_hours, created_at, updated_at;
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
                add_task_audit_entry(
                    cur,
                    task_id=task["id"],
                    actor_id=user_id,
                    event_type="CREATE",
                    field=None,
                    old_value=None,
                    new_value={
                        "title": task["title"],
                        "description": task["description"],
                        "status": task["status"],
                        "execution_hours": task["execution_hours"],
                        "sprint_id": task["sprint_id"],
                        "version": task["version"],
                    },
                )
            conn.commit()
            return task
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except HTTPException:
        raise
    except PsycopgError as exc:
        raise HTTPException(status_code=500, detail=f"Database error while creating task: {exc}")


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
        extracted_tasks = extract_tasks_by_rules(text)
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
                ensure_task_audit_table(cur)
                user_id = get_user_id_by_tg_id(cur, payload.tg_id)
                cur.execute(
                    """
                    SELECT id, project_id, title, description, status, execution_hours, sprint_id
                    FROM tasks
                    WHERE id = %s
                    LIMIT 1;
                    """,
                    (task_id,),
                )
                before = cur.fetchone()
                if not before:
                    raise HTTPException(status_code=404, detail="Task not found")
                project_id = before["project_id"]
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
                    RETURNING id, project_id, sprint_id, version, title, description, status, execution_hours, created_at, updated_at;
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
                if not updated:
                    raise HTTPException(status_code=404, detail="Task not found")
                changed_fields = [
                    ("title", before["title"], updated["title"], "UPDATE"),
                    ("description", before["description"], updated["description"], "UPDATE"),
                    ("execution_hours", before["execution_hours"], updated["execution_hours"], "UPDATE"),
                    ("sprint_id", before["sprint_id"], updated["sprint_id"], "UPDATE"),
                    ("status", before["status"], updated["status"], "STATUS_CHANGE"),
                ]
                changed_any = False
                for field, old_val, new_val, event_type in changed_fields:
                    if old_val != new_val:
                        changed_any = True
                        add_task_audit_entry(
                            cur,
                            task_id=task_id,
                            actor_id=user_id,
                            event_type=event_type,
                            field=field,
                            old_value=old_val,
                            new_value=new_val,
                        )
                if changed_any:
                    cur.execute("UPDATE tasks SET version = version + 1 WHERE id = %s RETURNING version;", (task_id,))
                    version_row = cur.fetchone()
                    if version_row:
                        updated["version"] = version_row["version"]
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


def list_task_history(task_id: int, tg_id: int) -> list[dict]:
    try:
        with connect(get_database_url()) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                ensure_sprint_tables(cur)
                ensure_task_audit_table(cur)
                user_id = get_user_id_by_tg_id(cur, tg_id)
                cur.execute("SELECT project_id FROM tasks WHERE id = %s LIMIT 1;", (task_id,))
                task_row = cur.fetchone()
                if not task_row:
                    raise HTTPException(status_code=404, detail="Task not found")
                ensure_project_member(cur, task_row["project_id"], user_id)
                cur.execute(
                    """
                    SELECT
                      l.id,
                      l.task_id,
                      l.event_type,
                      l.field,
                      l.old_value,
                      l.new_value,
                      l.created_at,
                      u.id AS actor_id,
                      u.first_name,
                      u.last_name,
                      u.username
                    FROM task_audit_log l
                    JOIN users u ON u.id = l.actor_id
                    WHERE l.task_id = %s
                    ORDER BY l.created_at DESC, l.id DESC;
                    """,
                    (task_id,),
                )
                return cur.fetchall()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except HTTPException:
        raise
    except PsycopgError as exc:
        raise HTTPException(status_code=500, detail=f"Database error while loading task history: {exc}")


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

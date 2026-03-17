import json

from fastapi import HTTPException


def normalize_task_status(status: str | None) -> str:
    if not status:
        return "NEW"
    status_upper = status.upper()
    if status_upper not in {"NEW", "IN_PROGRESS", "DONE"}:
        raise HTTPException(status_code=400, detail="Invalid task status")
    return status_upper


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
    cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;")
    cur.execute("UPDATE tasks SET version = 1 WHERE version IS NULL OR version < 1;")
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


def ensure_task_audit_table(cur) -> None:
    cur.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'audit_event_type') THEN
            CREATE TYPE audit_event_type AS ENUM (
              'CREATE',
              'UPDATE',
              'STATUS_CHANGE',
              'ASSIGNEE_CHANGE',
              'DEADLINE_CHANGE',
              'COMMENT_ADD',
              'ATTACH_ADD'
            );
          END IF;
        END
        $$;
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS task_audit_log (
          id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          task_id BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
          actor_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
          event_type audit_event_type NOT NULL,
          field TEXT,
          old_value JSONB,
          new_value JSONB,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_task_audit_task_created ON task_audit_log(task_id, created_at DESC);")


def add_task_audit_entry(
    cur,
    task_id: int,
    actor_id: int,
    event_type: str,
    field: str | None,
    old_value,
    new_value,
) -> None:
    cur.execute(
        """
        INSERT INTO task_audit_log (task_id, actor_id, event_type, field, old_value, new_value)
        VALUES (%s, %s, %s::audit_event_type, %s, %s::jsonb, %s::jsonb);
        """,
        (
            task_id,
            actor_id,
            event_type,
            field,
            json.dumps(old_value, ensure_ascii=False) if old_value is not None else None,
            json.dumps(new_value, ensure_ascii=False) if new_value is not None else None,
        ),
    )

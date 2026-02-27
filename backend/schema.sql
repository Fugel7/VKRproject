-- PostgreSQL schema for Telegram Mini App task tracker (MVP)

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE project_role AS ENUM ('OWNER', 'EXECUTOR', 'MEMBER', 'VIEWER');
CREATE TYPE task_status AS ENUM ('NEW', 'IN_PROGRESS', 'DONE');
CREATE TYPE attachment_type AS ENUM ('TELEGRAM_FILE', 'URL');
CREATE TYPE audit_event_type AS ENUM (
  'CREATE',
  'UPDATE',
  'STATUS_CHANGE',
  'ASSIGNEE_CHANGE',
  'DEADLINE_CHANGE',
  'COMMENT_ADD',
  'ATTACH_ADD'
);

CREATE TABLE users (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tg_id BIGINT NOT NULL UNIQUE,
  username TEXT,
  first_name TEXT NOT NULL,
  last_name TEXT,
  photo_url TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_login_at TIMESTAMPTZ
);

CREATE TABLE projects (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tg_chat_id BIGINT,
  tg_chat_instance TEXT,
  tg_chat_type TEXT,
  project_key UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
  title TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX ux_projects_tg_chat_id_not_null
  ON projects(tg_chat_id)
  WHERE tg_chat_id IS NOT NULL;

CREATE UNIQUE INDEX ux_projects_tg_chat_instance_not_null
  ON projects(tg_chat_instance)
  WHERE tg_chat_instance IS NOT NULL;

CREATE TABLE project_members (
  project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role project_role NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (project_id, user_id)
);

CREATE TABLE tasks (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title VARCHAR(120) NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  status task_status NOT NULL DEFAULT 'NEW',
  author_id BIGINT NOT NULL,
  assignee_id BIGINT NOT NULL,
  deadline_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT fk_tasks_author_member
    FOREIGN KEY (project_id, author_id)
    REFERENCES project_members(project_id, user_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_tasks_assignee_member
    FOREIGN KEY (project_id, assignee_id)
    REFERENCES project_members(project_id, user_id)
    ON DELETE RESTRICT
);

CREATE TABLE comments (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  task_id BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  author_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  text TEXT NOT NULL CHECK (char_length(text) BETWEEN 1 AND 4000),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE attachments (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  task_id BIGINT REFERENCES tasks(id) ON DELETE CASCADE,
  comment_id BIGINT REFERENCES comments(id) ON DELETE CASCADE,
  type attachment_type NOT NULL,
  tg_file_id TEXT,
  url TEXT,
  file_name TEXT,
  mime_type TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT chk_attachments_owner_xor
    CHECK (num_nonnulls(task_id, comment_id) = 1),
  CONSTRAINT chk_attachments_payload
    CHECK (
      (type = 'TELEGRAM_FILE' AND tg_file_id IS NOT NULL AND url IS NULL)
      OR
      (type = 'URL' AND url IS NOT NULL AND tg_file_id IS NULL)
    )
);

CREATE TABLE task_audit_log (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  task_id BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  actor_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  event_type audit_event_type NOT NULL,
  field TEXT,
  old_value JSONB,
  new_value JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_project_members_user_id
  ON project_members(user_id)
  WHERE is_active = TRUE;

CREATE INDEX idx_tasks_project_status
  ON tasks(project_id, status);

CREATE INDEX idx_tasks_project_assignee
  ON tasks(project_id, assignee_id);

CREATE INDEX idx_tasks_project_deadline
  ON tasks(project_id, deadline_at);

CREATE INDEX idx_tasks_project_updated_desc
  ON tasks(project_id, updated_at DESC);

CREATE INDEX idx_tasks_project_author
  ON tasks(project_id, author_id);

CREATE INDEX idx_comments_task_created
  ON comments(task_id, created_at);

CREATE INDEX idx_attachments_task_created
  ON attachments(task_id, created_at)
  WHERE task_id IS NOT NULL;

CREATE INDEX idx_attachments_comment_created
  ON attachments(comment_id, created_at)
  WHERE comment_id IS NOT NULL;

CREATE INDEX idx_task_audit_task_created
  ON task_audit_log(task_id, created_at DESC);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_tasks_set_updated_at
BEFORE UPDATE ON tasks
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

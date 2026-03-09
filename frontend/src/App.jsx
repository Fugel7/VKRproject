import React, { useEffect, useMemo, useState } from 'react';

const STATUS_OPTIONS = [
  { value: 'NEW', label: 'Запланирован', progress: 33 },
  { value: 'IN_PROGRESS', label: 'В работе', progress: 66 },
  { value: 'DONE', label: 'Готово', progress: 100 }
];

function applyTelegramTheme() {
  // Intentionally keep app branding independent from Telegram theme colors.
}

function toDisplayName(user) {
  if (!user) return 'Не авторизован';
  const full = [user.first_name, user.last_name].filter(Boolean).join(' ').trim();
  return full || user.username || `ID ${user.tg_id ?? user.id}`;
}

function toInitials(user) {
  const name = toDisplayName(user);
  return name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');
}

function getApiBase() {
  const { hostname, port } = window.location;
  if (port === '5173' && (hostname === '127.0.0.1' || hostname === 'localhost')) {
    return 'http://127.0.0.1:8000';
  }
  return '/api';
}

function statusMeta(status) {
  return STATUS_OPTIONS.find((item) => item.value === status) || STATUS_OPTIONS[0];
}

function toDeadlineLabel(dateLike) {
  if (!dateLike) return 'Без дедлайна';
  const dt = new Date(dateLike);
  if (Number.isNaN(dt.getTime())) return 'Без дедлайна';
  return dt.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
}

function toSprintDateLabel(value) {
  if (!value) return '—';
  const dt = new Date(`${value}T00:00:00`);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleDateString('ru-RU');
}

function TaskProgress({ status }) {
  const meta = statusMeta(status);
  return (
    <div className="progress-wrap">
      <div className="progress-line">
        <div className="progress-fill" style={{ width: `${meta.progress}%` }} />
      </div>
      <span className="progress-label">{meta.label}</span>
    </div>
  );
}

export default function App() {
  const [query, setQuery] = useState('');
  const [selectedProject, setSelectedProject] = useState(null);
  const [projects, setProjects] = useState([]);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [projectsError, setProjectsError] = useState(null);
  const [deletingProjectId, setDeletingProjectId] = useState(null);
  const [authState, setAuthState] = useState({
    status: 'loading',
    user: null,
    source: null,
    error: null
  });

  const [tasks, setTasks] = useState([]);
  const [sprints, setSprints] = useState([]);
  const [boardLoading, setBoardLoading] = useState(false);
  const [boardError, setBoardError] = useState(null);
  const [showTaskModal, setShowTaskModal] = useState(false);
  const [showSprintModal, setShowSprintModal] = useState(false);
  const [taskForm, setTaskForm] = useState({
    title: '',
    description: '',
    execution_hours: '',
    status: 'NEW',
    sprint_id: ''
  });
  const [sprintForm, setSprintForm] = useState({
    title: '',
    start_date: '',
    end_date: ''
  });
  const [expandedSprints, setExpandedSprints] = useState({});
  const [taskDetails, setTaskDetails] = useState(null);
  const [comments, setComments] = useState([]);
  const [commentsLoading, setCommentsLoading] = useState(false);
  const [commentText, setCommentText] = useState('');

  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    tg?.ready?.();
    applyTelegramTheme();

    async function loadProjects(apiBase, tgId, activeProject) {
      setProjectsLoading(true);
      setProjectsError(null);
      try {
        const response = await fetch(`${apiBase}/projects?tg_id=${encodeURIComponent(tgId)}`);
        if (!response.ok) {
          let details = `Projects failed ${response.status}`;
          try {
            const payload = await response.json();
            if (payload?.detail) details = `${response.status}: ${payload.detail}`;
          } catch {
            // keep details with status
          }
          throw new Error(details);
        }

        const data = await response.json();
        const list = Array.isArray(data?.projects) ? data.projects : [];
        setProjects(list);

        if (activeProject) {
          const foundById = list.find((item) => item.id === activeProject.id);
          const foundByKey = list.find((item) => item.project_key === activeProject.project_key);
          setSelectedProject(foundById || foundByKey || activeProject);
        } else {
          const params = new URLSearchParams(window.location.search);
          const incomingProjectKey = params.get('project_key');
          if (incomingProjectKey) {
            const found = list.find((item) => item.project_key === incomingProjectKey);
            if (found) setSelectedProject(found);
          }
        }
      } catch (error) {
        setProjects([]);
        setProjectsError(`Не удалось загрузить проекты. ${error?.message ?? ''}`.trim());
      } finally {
        setProjectsLoading(false);
      }
    }

    async function resolveTelegramUser() {
      const apiBase = getApiBase();

      if (!tg) {
        setAuthState({
          status: 'anonymous',
          user: null,
          source: null,
          error: 'Откройте приложение внутри Telegram для авторизации.'
        });
        return;
      }

      const unsafeUser = tg.initDataUnsafe?.user ?? null;
      if (!tg.initData) {
        setAuthState({
          status: unsafeUser ? 'ready' : 'anonymous',
          user: unsafeUser,
          source: unsafeUser ? 'telegram_unsafe' : null,
          error: unsafeUser ? null : 'Telegram initData не получен.'
        });
        return;
      }

      try {
        const unsafeChat = tg.initDataUnsafe?.chat ?? null;
        const urlParams = new URLSearchParams(window.location.search);
        const webStartParam = urlParams.get('tgWebAppStartParam');
        const response = await fetch(`${apiBase}/auth/telegram`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            init_data: tg.initData,
            start_param: webStartParam,
            unsafe_chat_id: unsafeChat?.id ?? null,
            unsafe_chat_type: unsafeChat?.type ?? null,
            unsafe_chat_title: unsafeChat?.title ?? null
          })
        });

        if (!response.ok) {
          let details = `Auth failed ${response.status}`;
          try {
            const errorPayload = await response.json();
            if (errorPayload?.detail) details = `${response.status}: ${errorPayload.detail}`;
          } catch {
            // ignore JSON parse errors and keep status text
          }
          throw new Error(details);
        }

        const data = await response.json();
        const dbUser = data?.db_user;
        if (!dbUser) throw new Error('Missing db_user after auth');
        const activeProject = data?.active_project ?? null;

        setAuthState({
          status: 'ready',
          user: dbUser,
          source: 'telegram_verified_db',
          error: null
        });

        await loadProjects(apiBase, dbUser.tg_id, activeProject);
      } catch (error) {
        setAuthState({
          status: unsafeUser ? 'ready' : 'error',
          user: unsafeUser,
          source: unsafeUser ? 'telegram_unsafe' : null,
          error: `Не удалось подтвердить Telegram подпись на бэке. ${error?.message ?? ''}`.trim()
        });
        setProjects([]);
      }
    }

    resolveTelegramUser();
  }, []);

  const visibleProjects = useMemo(() => {
    if (!query.trim()) return projects;
    const lowered = query.toLowerCase();
    return projects.filter((project) => project.title.toLowerCase().includes(lowered));
  }, [projects, query]);

  const backlogTasks = useMemo(() => tasks.filter((task) => task.sprint_id == null), [tasks]);

  async function loadBoard(projectId, tgId) {
    const apiBase = getApiBase();
    setBoardLoading(true);
    setBoardError(null);
    try {
      const [tasksRes, sprintsRes] = await Promise.all([
        fetch(`${apiBase}/projects/${projectId}/tasks?tg_id=${encodeURIComponent(tgId)}`),
        fetch(`${apiBase}/projects/${projectId}/sprints?tg_id=${encodeURIComponent(tgId)}`)
      ]);
      if (!tasksRes.ok || !sprintsRes.ok) {
        throw new Error(`Не удалось загрузить данные проекта (${tasksRes.status}/${sprintsRes.status})`);
      }
      const tasksData = await tasksRes.json();
      const sprintsData = await sprintsRes.json();
      setTasks(Array.isArray(tasksData?.tasks) ? tasksData.tasks : []);
      const sprintList = Array.isArray(sprintsData?.sprints) ? sprintsData.sprints : [];
      setSprints(sprintList);
      setExpandedSprints((prev) => {
        const next = { ...prev };
        sprintList.forEach((sprint) => {
          if (next[sprint.id] == null) next[sprint.id] = !!sprint.is_open;
        });
        return next;
      });
    } catch (error) {
      setBoardError(`Не удалось загрузить задачи и спринты. ${error?.message ?? ''}`.trim());
      setTasks([]);
      setSprints([]);
    } finally {
      setBoardLoading(false);
    }
  }

  useEffect(() => {
    if (!selectedProject?.id || !authState.user?.tg_id) return;
    loadBoard(selectedProject.id, authState.user.tg_id);
  }, [selectedProject?.id, authState.user?.tg_id]);

  async function deleteProject(project) {
    if (!project?.id || !authState.user?.tg_id) return;

    const confirmed = window.confirm(`Удалить проект "${project.title}"?`);
    if (!confirmed) return;

    try {
      setDeletingProjectId(project.id);
      setProjectsError(null);

      const apiBase = getApiBase();
      const response = await fetch(
        `${apiBase}/projects/${encodeURIComponent(project.id)}?tg_id=${encodeURIComponent(authState.user.tg_id)}`,
        { method: 'DELETE' }
      );

      if (!response.ok) {
        let details = `Delete failed ${response.status}`;
        try {
          const payload = await response.json();
          if (payload?.detail) details = `${response.status}: ${payload.detail}`;
        } catch {
          // keep default details
        }
        throw new Error(details);
      }

      setProjects((prev) => prev.filter((item) => item.id !== project.id));
      setSelectedProject((prev) => (prev?.id === project.id ? null : prev));
    } catch (error) {
      setProjectsError(`Не удалось удалить проект. ${error?.message ?? ''}`.trim());
    } finally {
      setDeletingProjectId(null);
    }
  }

  async function createTask(event) {
    event.preventDefault();
    if (!selectedProject?.id || !authState.user?.tg_id) return;
    const apiBase = getApiBase();
    try {
      const response = await fetch(`${apiBase}/projects/${selectedProject.id}/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tg_id: authState.user.tg_id,
          title: taskForm.title,
          description: taskForm.description,
          execution_hours: taskForm.execution_hours ? Number(taskForm.execution_hours) : null,
          status: taskForm.status,
          sprint_id: taskForm.sprint_id ? Number(taskForm.sprint_id) : null
        })
      });
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({}));
        throw new Error(errorPayload?.detail || `Task create failed ${response.status}`);
      }
      setTaskForm({ title: '', description: '', execution_hours: '', status: 'NEW', sprint_id: '' });
      setShowTaskModal(false);
      await loadBoard(selectedProject.id, authState.user.tg_id);
    } catch (error) {
      setBoardError(`Не удалось создать задачу. ${error?.message ?? ''}`.trim());
    }
  }

  async function createSprint(event) {
    event.preventDefault();
    if (!selectedProject?.id || !authState.user?.tg_id) return;
    const apiBase = getApiBase();
    try {
      const response = await fetch(`${apiBase}/projects/${selectedProject.id}/sprints`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tg_id: authState.user.tg_id,
          title: sprintForm.title,
          start_date: sprintForm.start_date || null,
          end_date: sprintForm.end_date || null
        })
      });
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({}));
        throw new Error(errorPayload?.detail || `Sprint create failed ${response.status}`);
      }
      setSprintForm({ title: '', start_date: '', end_date: '' });
      setShowSprintModal(false);
      await loadBoard(selectedProject.id, authState.user.tg_id);
    } catch (error) {
      setBoardError(`Не удалось создать спринт. ${error?.message ?? ''}`.trim());
    }
  }

  async function updateTask(taskId, fields) {
    if (!authState.user?.tg_id) return;
    const apiBase = getApiBase();
    const response = await fetch(`${apiBase}/tasks/${taskId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tg_id: authState.user.tg_id, ...fields })
    });
    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}));
      throw new Error(errorPayload?.detail || `Task update failed ${response.status}`);
    }
  }

  async function moveTaskToSprint(taskId, sprintId) {
    try {
      await updateTask(taskId, { sprint_id: sprintId });
      if (selectedProject?.id && authState.user?.tg_id) {
        await loadBoard(selectedProject.id, authState.user.tg_id);
      }
    } catch (error) {
      setBoardError(`Не удалось переместить задачу в спринт. ${error?.message ?? ''}`.trim());
    }
  }

  async function deleteSprint(sprintId, sprintTitle) {
    if (!authState.user?.tg_id || !selectedProject?.id) return;
    const confirmed = window.confirm(`Удалить спринт "${sprintTitle}"? Задачи останутся и перейдут в общий список.`);
    if (!confirmed) return;
    try {
      const apiBase = getApiBase();
      const response = await fetch(
        `${apiBase}/sprints/${encodeURIComponent(sprintId)}?tg_id=${encodeURIComponent(authState.user.tg_id)}`,
        { method: 'DELETE' }
      );
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({}));
        throw new Error(errorPayload?.detail || `Sprint delete failed ${response.status}`);
      }
      await loadBoard(selectedProject.id, authState.user.tg_id);
    } catch (error) {
      setBoardError(`Не удалось удалить спринт. ${error?.message ?? ''}`.trim());
    }
  }

  function openTaskDetails(task) {
    setTaskDetails({ ...task, execution_hours: task.execution_hours ?? '' });
    setCommentText('');
    void loadTaskComments(task.id);
  }

  async function loadTaskComments(taskId) {
    if (!authState.user?.tg_id) return;
    setCommentsLoading(true);
    try {
      const apiBase = getApiBase();
      const response = await fetch(`${apiBase}/tasks/${taskId}/comments?tg_id=${encodeURIComponent(authState.user.tg_id)}`);
      if (!response.ok) {
        throw new Error(`Comments failed ${response.status}`);
      }
      const data = await response.json();
      setComments(Array.isArray(data?.comments) ? data.comments : []);
    } catch (error) {
      setBoardError(`Не удалось загрузить комментарии. ${error?.message ?? ''}`.trim());
      setComments([]);
    } finally {
      setCommentsLoading(false);
    }
  }

  async function saveTaskDetails(event) {
    event.preventDefault();
    if (!taskDetails?.id) return;
    try {
      await updateTask(taskDetails.id, {
        title: taskDetails.title,
        description: taskDetails.description,
        status: taskDetails.status,
        execution_hours: taskDetails.execution_hours === '' ? null : Number(taskDetails.execution_hours)
      });
      if (selectedProject?.id && authState.user?.tg_id) {
        await loadBoard(selectedProject.id, authState.user.tg_id);
      }
      setTaskDetails(null);
    } catch (error) {
      setBoardError(`Не удалось сохранить задачу. ${error?.message ?? ''}`.trim());
    }
  }

  async function createComment(event) {
    event.preventDefault();
    if (!taskDetails?.id || !commentText.trim() || !authState.user?.tg_id) return;
    try {
      const apiBase = getApiBase();
      const response = await fetch(`${apiBase}/tasks/${taskDetails.id}/comments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tg_id: authState.user.tg_id, text: commentText.trim() })
      });
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({}));
        throw new Error(errorPayload?.detail || `Comment create failed ${response.status}`);
      }
      setCommentText('');
      await loadTaskComments(taskDetails.id);
    } catch (error) {
      setBoardError(`Не удалось добавить комментарий. ${error?.message ?? ''}`.trim());
    }
  }

  function sprintTasksSorted(sprintId) {
    const order = { DONE: 0, IN_PROGRESS: 1, NEW: 2 };
    return tasks
      .filter((task) => task.sprint_id === sprintId)
      .sort((a, b) => {
        const statusDiff = (order[a.status] ?? 9) - (order[b.status] ?? 9);
        if (statusDiff !== 0) return statusDiff;
        return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
      });
  }

  function toggleSprint(sprintId, current) {
    setExpandedSprints((prev) => ({ ...prev, [sprintId]: !current }));
  }

  function openProfile() {
    if (!authState.user) return;
    const tg = window.Telegram?.WebApp;

    if (authState.user.username) {
      const link = `https://t.me/${authState.user.username}`;
      if (tg?.openTelegramLink) tg.openTelegramLink(link);
      else window.open(link, '_blank', 'noopener,noreferrer');
      return;
    }

    const telegramId = authState.user.tg_id ?? authState.user.id;
    if (telegramId) {
      const link = `tg://user?id=${telegramId}`;
      if (tg?.openLink) tg.openLink(link);
      else window.open(link, '_blank', 'noopener,noreferrer');
    }
  }

  if (selectedProject) {
    return (
      <main className="app">
        <div className="screen-header">
          <h1 className="screen-title">{selectedProject.title}</h1>
          <p className="screen-subtitle">Задачи и спринты проекта</p>
        </div>

        <button className="back-btn" onClick={() => setSelectedProject(null)}>
          Назад к списку проектов
        </button>

        {boardError && <p className="auth-hint">{boardError}</p>}

        <div className="board-actions">
          <button className="open-btn" onClick={() => setShowTaskModal(true)}>
            Новая задача
          </button>
          <button className="open-btn" onClick={() => setShowSprintModal(true)}>
            Новый спринт
          </button>
        </div>

        {boardLoading && <div className="empty">Загружаем данные проекта...</div>}

        {!boardLoading && (
          <div className="board-grid">
            <section className="card">
              <h3>Задачи</h3>
              <p className="screen-subtitle">Перетащите задачу в спринт, чтобы добавить ее в план.</p>
              <div className="task-list">
                {backlogTasks.length === 0 && <div className="empty compact">Свободных задач нет</div>}
                {backlogTasks.map((task) => (
                  <article
                    key={task.id}
                    className="task-card"
                    draggable
                    onDragStart={(e) => e.dataTransfer.setData('text/task-id', String(task.id))}
                  >
                    <button type="button" className="task-open" onClick={() => openTaskDetails(task)}>
                      <strong>{task.title}</strong>
                      <span>{task.description || 'Без описания'}</span>
                    </button>
                    <TaskProgress status={task.status} />
                    <div className="task-meta">
                      Время выполнения: {task.execution_hours ? `${task.execution_hours} ч` : 'не указано'}
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <section className="card">
              <h3>Спринты</h3>
              <div className="sprint-list">
                {sprints.length === 0 && <div className="empty compact">Спринтов пока нет</div>}
                {sprints.map((sprint) => {
                  const sprintTasks = sprintTasksSorted(sprint.id);
                  const doneCount = sprintTasks.filter((task) => task.status === 'DONE').length;
                  const sprintProgress = sprintTasks.length ? Math.round((doneCount / sprintTasks.length) * 100) : 0;
                  const isOpen = !!expandedSprints[sprint.id];

                  return (
                    <article
                      key={sprint.id}
                      className="sprint-card"
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={(e) => {
                        const draggedTaskId = Number(e.dataTransfer.getData('text/task-id'));
                        if (draggedTaskId) void moveTaskToSprint(draggedTaskId, sprint.id);
                      }}
                    >
                      <button
                        type="button"
                        className="sprint-delete-btn"
                        onClick={(event) => {
                          event.stopPropagation();
                          void deleteSprint(sprint.id, sprint.title);
                        }}
                        aria-label="Удалить спринт"
                        title="Удалить спринт"
                      >
                        🗑
                      </button>
                      <button type="button" className="sprint-header" onClick={() => toggleSprint(sprint.id, isOpen)}>
                        <strong>{sprint.title}</strong>
                        <span>{isOpen ? 'Свернуть' : 'Открыть'}</span>
                      </button>
                      <p className="screen-subtitle sprint-dates">
                        Срок спринта: {toSprintDateLabel(sprint.start_date)} - {toSprintDateLabel(sprint.end_date)}
                      </p>
                      <div className="progress-line sprint-progress">
                        <div className="progress-fill" style={{ width: `${sprintProgress}%` }} />
                      </div>
                      <p className="screen-subtitle">
                        Выполнено: {doneCount} из {sprintTasks.length}
                      </p>
                      {isOpen && (
                        <>
                          <button
                            className="open-btn small-btn"
                            type="button"
                            onClick={() => {
                              setShowTaskModal(true);
                              setTaskForm((prev) => ({ ...prev, sprint_id: String(sprint.id) }));
                            }}
                          >
                            Добавить задачу в спринт
                          </button>
                          <div className="task-list">
                            {sprintTasks.length === 0 && <div className="empty compact">Задач в спринте нет</div>}
                            {sprintTasks.map((task) => (
                              <article key={task.id} className="task-card">
                                <button type="button" className="task-open" onClick={() => openTaskDetails(task)}>
                                  <strong>{task.title}</strong>
                                  <span>{task.description || 'Без описания'}</span>
                                </button>
                                <TaskProgress status={task.status} />
                                <div className="task-meta">
                                  Время выполнения: {task.execution_hours ? `${task.execution_hours} ч` : 'не указано'}
                                </div>
                              </article>
                            ))}
                          </div>
                        </>
                      )}
                    </article>
                  );
                })}
              </div>
            </section>
          </div>
        )}

        {showTaskModal && (
          <div className="modal-overlay" onClick={() => setShowTaskModal(false)}>
            <section className="modal-card" onClick={(e) => e.stopPropagation()}>
              <h3>Создать задачу</h3>
              <form className="form-card" onSubmit={createTask}>
                <input
                  className="search"
                  placeholder="Название"
                  value={taskForm.title}
                  onChange={(e) => setTaskForm((prev) => ({ ...prev, title: e.target.value }))}
                  required
                />
                <textarea
                  className="textarea"
                  placeholder="Описание"
                  value={taskForm.description}
                  onChange={(e) => setTaskForm((prev) => ({ ...prev, description: e.target.value }))}
                />
                <div className="form-row">
                  <label className="field">
                    <span>Время выполнения (ч)</span>
                    <input
                      type="number"
                      min="1"
                      value={taskForm.execution_hours}
                      onChange={(e) => setTaskForm((prev) => ({ ...prev, execution_hours: e.target.value }))}
                      placeholder="Например: 8"
                    />
                  </label>
                  <label className="field">
                    <span>Статус</span>
                    <select
                      value={taskForm.status}
                      onChange={(e) => setTaskForm((prev) => ({ ...prev, status: e.target.value }))}
                    >
                      {STATUS_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span>Спринт</span>
                    <select
                      value={taskForm.sprint_id}
                      onChange={(e) => setTaskForm((prev) => ({ ...prev, sprint_id: e.target.value }))}
                    >
                      <option value="">Без спринта</option>
                      {sprints.map((sprint) => (
                        <option key={sprint.id} value={sprint.id}>
                          {sprint.title}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <div className="meta">
                  <button className="open-btn" type="submit">
                    Создать задачу
                  </button>
                  <button className="back-btn" type="button" onClick={() => setShowTaskModal(false)}>
                    Отмена
                  </button>
                </div>
              </form>
            </section>
          </div>
        )}

        {showSprintModal && (
          <div className="modal-overlay" onClick={() => setShowSprintModal(false)}>
            <section className="modal-card" onClick={(e) => e.stopPropagation()}>
              <h3>Создать спринт</h3>
              <form className="form-card" onSubmit={createSprint}>
                <input
                  className="search"
                  placeholder="Название спринта"
                  value={sprintForm.title}
                  onChange={(e) => setSprintForm((prev) => ({ ...prev, title: e.target.value }))}
                  required
                />
                <div className="form-row">
                  <label className="field">
                    <span>Дата начала</span>
                    <input
                      type="date"
                      value={sprintForm.start_date}
                      onChange={(e) => setSprintForm((prev) => ({ ...prev, start_date: e.target.value }))}
                    />
                  </label>
                  <label className="field">
                    <span>Дата конца</span>
                    <input
                      type="date"
                      value={sprintForm.end_date}
                      onChange={(e) => setSprintForm((prev) => ({ ...prev, end_date: e.target.value }))}
                    />
                  </label>
                </div>
                <div className="meta">
                  <button className="open-btn" type="submit">
                    Создать спринт
                  </button>
                  <button className="back-btn" type="button" onClick={() => setShowSprintModal(false)}>
                    Отмена
                  </button>
                </div>
              </form>
            </section>
          </div>
        )}

        {taskDetails && (
          <div className="modal-overlay" onClick={() => setTaskDetails(null)}>
            <section className="modal-card" onClick={(e) => e.stopPropagation()}>
              <h3>Задача</h3>
              <form onSubmit={saveTaskDetails} className="form-card">
                <input
                  className="search"
                  value={taskDetails.title}
                  onChange={(e) => setTaskDetails((prev) => ({ ...prev, title: e.target.value }))}
                  required
                />
                <textarea
                  className="textarea"
                  value={taskDetails.description ?? ''}
                  onChange={(e) => setTaskDetails((prev) => ({ ...prev, description: e.target.value }))}
                />
                <div className="form-row">
                  <label className="field">
                    <span>Статус</span>
                    <select
                      value={taskDetails.status}
                      onChange={(e) => setTaskDetails((prev) => ({ ...prev, status: e.target.value }))}
                    >
                      {STATUS_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span>Время выполнения (ч)</span>
                    <input
                      type="number"
                      min="1"
                      value={taskDetails.execution_hours ?? ''}
                      onChange={(e) => setTaskDetails((prev) => ({ ...prev, execution_hours: e.target.value }))}
                      placeholder="Например: 8"
                    />
                  </label>
                </div>
                <button className="open-btn" type="submit">
                  Сохранить задачу
                </button>
              </form>

              <h3>Комментарии</h3>
              <div className="comment-list">
                {commentsLoading && <div className="empty compact">Загружаем комментарии...</div>}
                {!commentsLoading && comments.length === 0 && <div className="empty compact">Комментариев нет</div>}
                {!commentsLoading &&
                  comments.map((comment) => (
                    <article className="comment-card" key={comment.id}>
                      <strong>
                        {[comment.first_name, comment.last_name].filter(Boolean).join(' ').trim() ||
                          comment.username ||
                          `User ${comment.author_id}`}
                      </strong>
                      <p>{comment.text}</p>
                      <span>{toDeadlineLabel(comment.created_at)}</span>
                    </article>
                  ))}
              </div>
              <form className="comment-form" onSubmit={createComment}>
                <textarea
                  className="textarea"
                  placeholder="Оставить комментарий"
                  value={commentText}
                  onChange={(e) => setCommentText(e.target.value)}
                  required
                />
                <button className="open-btn" type="submit">
                  Отправить
                </button>
              </form>
            </section>
          </div>
        )}
      </main>
    );
  }

  return (
    <main className="app">
      <div className="screen-header">
        <h1 className="screen-title">Выбор проекта</h1>
        <p className="screen-subtitle">Выберите проект для работы.</p>
      </div>

      <button className="profile-banner" type="button" onClick={openProfile} disabled={!authState.user}>
        {authState.user?.photo_url ? (
          <img className="profile-avatar" src={authState.user.photo_url} alt={toDisplayName(authState.user)} />
        ) : (
          <span className="profile-avatar profile-avatar-fallback">{toInitials(authState.user)}</span>
        )}
        <span className="profile-info">
          <strong>{toDisplayName(authState.user)}</strong>
          <span>
            {authState.status === 'loading' && 'Проверяем Telegram авторизацию...'}
            {authState.status !== 'loading' &&
              (authState.source === 'telegram_verified' || authState.source === 'telegram_verified_db'
                ? 'Telegram: подтверждено'
                : 'Telegram: без проверки подписи')}
          </span>
        </span>
      </button>

      {authState.error && <p className="auth-hint">{authState.error}</p>}
      {projectsError && <p className="auth-hint">{projectsError}</p>}

      <input
        className="search"
        type="search"
        placeholder="Поиск по названию проекта"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        disabled={projectsLoading}
      />

      <section className="project-list">
        {projectsLoading && <div className="empty">Загружаем проекты...</div>}
        {!projectsLoading && visibleProjects.length === 0 && <div className="empty">Проекты не найдены</div>}

        {!projectsLoading &&
          visibleProjects.map((project) => (
            <article
              key={project.id}
              className="card project-card"
              role="button"
              tabIndex={0}
              onClick={() => setSelectedProject(project)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  setSelectedProject(project);
                }
              }}
            >
              <button
                className="delete-icon-btn"
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  void deleteProject(project);
                }}
                disabled={deletingProjectId === project.id}
                aria-label="Удалить проект"
                title="Удалить проект"
              >
                {deletingProjectId === project.id ? '…' : '🗑'}
              </button>
              <h3>{project.title}</h3>
              <p className="screen-subtitle">Откройте карточку, чтобы перейти в проект</p>
            </article>
          ))}
      </section>
    </main>
  );
}

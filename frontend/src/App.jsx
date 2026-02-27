import React, { useEffect, useMemo, useState } from 'react';

function applyTelegramTheme() {
  const tg = window.Telegram?.WebApp;
  if (!tg?.themeParams) return;

  const root = document.documentElement;
  const map = {
    '--bg': tg.themeParams.bg_color,
    '--text': tg.themeParams.text_color,
    '--muted': tg.themeParams.hint_color,
    '--card': tg.themeParams.secondary_bg_color,
    '--card-alt': tg.themeParams.section_bg_color,
    '--accent': tg.themeParams.button_color,
    '--accent-text': tg.themeParams.button_text_color,
    '--link': tg.themeParams.link_color,
    '--danger': tg.themeParams.destructive_text_color
  };

  Object.entries(map).forEach(([cssVar, value]) => {
    if (value) root.style.setProperty(cssVar, value);
  });
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
        const response = await fetch(`${apiBase}/auth/telegram`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            init_data: tg.initData,
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
          <h1 className="screen-title">Список задач</h1>
          <p className="screen-subtitle">Проект: {selectedProject.title}</p>
        </div>

        <button className="back-btn" onClick={() => setSelectedProject(null)}>
          Назад к списку проектов
        </button>

        <section className="card task-placeholder">
          <h3>Экран задач</h3>
          <p className="screen-subtitle">Здесь будет список задач выбранного проекта.</p>
        </section>
      </main>
    );
  }

  return (
    <main className="app">
      <div className="screen-header">
        <h1 className="screen-title">Выбор проекта</h1>
        <p className="screen-subtitle">Ваши проекты, полученные из базы данных.</p>
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
            <article key={project.id} className="card">
              <h3>{project.title}</h3>

              <div className="meta">
                {project.tg_chat_id ? <span className="badge">Чат: {project.tg_chat_id}</span> : null}
                <span className="badge badge-role">Роль: {project.role}</span>
              </div>

              <div className="meta">
                <button className="open-btn" onClick={() => setSelectedProject(project)}>
                  Открыть проект
                </button>
                {project.role === 'OWNER' && (
                  <button
                    className="back-btn"
                    type="button"
                    onClick={() => deleteProject(project)}
                    disabled={deletingProjectId === project.id}
                  >
                    {deletingProjectId === project.id ? 'Удаляем...' : 'Удалить проект'}
                  </button>
                )}
              </div>
            </article>
          ))}
      </section>
    </main>
  );
}

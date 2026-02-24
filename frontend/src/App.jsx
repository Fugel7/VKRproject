import React, { useEffect, useMemo, useState } from 'react';

const DEMO_PROJECTS = [
  {
    id: 1,
    key: 'f9f8c0fd-1775-44f2-8f56-53e24d655601',
    title: 'Разработка Telegram Mini App',
    type: 'Группа',
    role: 'OWNER'
  },
  {
    id: 2,
    key: 'b6fbe95d-37f3-4341-98e7-9f8cd8e5fdad',
    title: 'Личный проект: Дизайн и контент',
    type: 'Личный',
    role: 'MEMBER'
  },
  {
    id: 3,
    key: '355386db-a91b-41d4-8e7b-f6d394b0e728',
    title: 'QA и приёмка MVP',
    type: 'Группа',
    role: 'EXECUTOR'
  }
];

function applyTelegramTheme() {
  const tg = window.Telegram?.WebApp;
  if (!tg?.themeParams) return;

  const root = document.documentElement;
  const map = {
    '--bg': tg.themeParams.bg_color,
    '--text': tg.themeParams.text_color,
    '--card': tg.themeParams.secondary_bg_color,
    '--muted': tg.themeParams.hint_color,
    '--accent': tg.themeParams.button_color
  };

  Object.entries(map).forEach(([cssVar, value]) => {
    if (value) root.style.setProperty(cssVar, value);
  });
}

function toDisplayName(user) {
  if (!user) return 'Не авторизован';
  const full = [user.first_name, user.last_name].filter(Boolean).join(' ').trim();
  return full || user.username || `ID ${user.id}`;
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

export default function App() {
  const [query, setQuery] = useState('');
  const [selectedProject, setSelectedProject] = useState(null);
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

    const params = new URLSearchParams(window.location.search);
    const incomingProjectKey = params.get('project_key');
    if (incomingProjectKey) {
      const projectFromChat = DEMO_PROJECTS.find((item) => item.key === incomingProjectKey);
      if (projectFromChat) setSelectedProject(projectFromChat);
    }

    async function resolveTelegramUser() {
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
        const response = await fetch('http://127.0.0.1:8000/auth/telegram', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ init_data: tg.initData })
        });
        if (!response.ok) throw new Error(`Auth failed ${response.status}`);

        const data = await response.json();
        setAuthState({
          status: 'ready',
          user: data.user,
          source: 'telegram_verified',
          error: null
        });
      } catch (_error) {
        setAuthState({
          status: unsafeUser ? 'ready' : 'error',
          user: unsafeUser,
          source: unsafeUser ? 'telegram_unsafe' : null,
          error: 'Не удалось подтвердить Telegram подпись на бэке.'
        });
      }
    }

    resolveTelegramUser();
  }, []);

  const visibleProjects = useMemo(() => {
    if (!query.trim()) return DEMO_PROJECTS;
    const lowered = query.toLowerCase();
    return DEMO_PROJECTS.filter((project) => project.title.toLowerCase().includes(lowered));
  }, [query]);

  function openProfile() {
    if (!authState.user) return;
    const tg = window.Telegram?.WebApp;

    if (authState.user.username) {
      const link = `https://t.me/${authState.user.username}`;
      if (tg?.openTelegramLink) tg.openTelegramLink(link);
      else window.open(link, '_blank', 'noopener,noreferrer');
      return;
    }

    if (authState.user.id) {
      const link = `tg://user?id=${authState.user.id}`;
      if (tg?.openLink) tg.openLink(link);
      else window.open(link, '_blank', 'noopener,noreferrer');
    }
  }

  if (selectedProject) {
    return (
      <main className="app">
        <div className="screen-header">
          <h1 className="screen-title">Экран 2: Список задач</h1>
          <p className="screen-subtitle">Проект: {selectedProject.title}</p>
        </div>

        <button className="back-btn" onClick={() => setSelectedProject(null)}>
          Назад к выбору проектов
        </button>

        <section className="card task-placeholder">
          <h3>Заглушка списка задач</h3>
          <p className="screen-subtitle">
            На следующем шаге сюда подключим API и реальные задачи выбранного проекта.
          </p>
        </section>
      </main>
    );
  }

  return (
    <main className="app">
      <div className="screen-header">
        <h1 className="screen-title">Выбор проекта</h1>
        <p className="screen-subtitle">
          Экран 1 для пользователя, который состоит в нескольких чатах-проектах.
        </p>
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
              (authState.source === 'telegram_verified' ? 'Telegram: подтверждено' : 'Telegram: без проверки подписи')}
          </span>
        </span>
      </button>

      {authState.error && <p className="auth-hint">{authState.error}</p>}

      <input
        className="search"
        type="search"
        placeholder="Поиск по названию проекта"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />

      <section className="project-list">
        {visibleProjects.length === 0 && <div className="empty">Проекты не найдены</div>}

        {visibleProjects.map((project) => (
          <article key={project.id} className="card">
            <h3>{project.title}</h3>

            <div className="meta">
              <span className="badge">Тип: {project.type}</span>
              <span className="badge badge-role">Роль: {project.role}</span>
            </div>

            <button className="open-btn" onClick={() => setSelectedProject(project)}>
              Открыть проект
            </button>
          </article>
        ))}
      </section>
    </main>
  );
}

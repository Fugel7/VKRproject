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

export default function App() {
  const [query, setQuery] = useState('');
  const [selectedProject, setSelectedProject] = useState(null);

  useEffect(() => {
    window.Telegram?.WebApp?.ready?.();
    applyTelegramTheme();

    const params = new URLSearchParams(window.location.search);
    const incomingProjectKey = params.get('project_key');

    if (!incomingProjectKey) return;

    const projectFromChat = DEMO_PROJECTS.find((item) => item.key === incomingProjectKey);
    if (projectFromChat) {
      setSelectedProject(projectFromChat);
    }
  }, []);

  const visibleProjects = useMemo(() => {
    if (!query.trim()) return DEMO_PROJECTS;

    const lowered = query.toLowerCase();
    return DEMO_PROJECTS.filter((project) => project.title.toLowerCase().includes(lowered));
  }, [query]);

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


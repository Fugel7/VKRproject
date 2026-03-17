import React from 'react';

export default function ProjectSelectionView({
  authState,
  projectsError,
  projectsLoading,
  visibleProjects,
  query,
  setQuery,
  onSelectProject,
  onDeleteProject,
  deletingProjectId,
  openProfile,
  toDisplayName,
  toInitials,
}) {
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
              onClick={() => onSelectProject(project)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onSelectProject(project);
                }
              }}
            >
              <button
                className="delete-icon-btn"
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  void onDeleteProject(project);
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

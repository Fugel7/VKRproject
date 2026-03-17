import { useCallback, useEffect, useMemo, useState } from 'react';

import { getApiBase } from '../utils/api';

function applyTelegramTheme() {
  // Intentionally keep app branding independent from Telegram theme colors.
}

export function useProjects() {
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
    error: null,
  });

  const loadProjects = useCallback(async (apiBase, tgId, activeProject) => {
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
  }, []);

  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    tg?.ready?.();
    applyTelegramTheme();

    async function resolveTelegramUser() {
      const apiBase = getApiBase();

      if (!tg) {
        setAuthState({
          status: 'anonymous',
          user: null,
          source: null,
          error: 'Откройте приложение внутри Telegram для авторизации.',
        });
        return;
      }

      const unsafeUser = tg.initDataUnsafe?.user ?? null;
      if (!tg.initData) {
        setAuthState({
          status: unsafeUser ? 'ready' : 'anonymous',
          user: unsafeUser,
          source: unsafeUser ? 'telegram_unsafe' : null,
          error: unsafeUser ? null : 'Telegram initData не получен.',
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
            unsafe_chat_title: unsafeChat?.title ?? null,
          }),
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
          error: null,
        });

        await loadProjects(apiBase, dbUser.tg_id, activeProject);
      } catch (error) {
        setAuthState({
          status: unsafeUser ? 'ready' : 'error',
          user: unsafeUser,
          source: unsafeUser ? 'telegram_unsafe' : null,
          error: `Не удалось подтвердить Telegram подпись на бэке. ${error?.message ?? ''}`.trim(),
        });
        setProjects([]);
      }
    }

    resolveTelegramUser();
  }, [loadProjects]);

  const visibleProjects = useMemo(() => {
    if (!query.trim()) return projects;
    const lowered = query.toLowerCase();
    return projects.filter((project) => project.title.toLowerCase().includes(lowered));
  }, [projects, query]);

  const deleteProject = useCallback(
    async (project) => {
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
    },
    [authState.user?.tg_id]
  );

  const openProfile = useCallback(() => {
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
  }, [authState.user]);

  return {
    query,
    setQuery,
    selectedProject,
    setSelectedProject,
    projectsLoading,
    projectsError,
    deletingProjectId,
    authState,
    visibleProjects,
    deleteProject,
    openProfile,
  };
}

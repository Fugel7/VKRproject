import { useCallback, useEffect, useMemo, useState } from 'react';

import { getApiBase, toTimeMs } from '../utils/api';

export function useBoard({ selectedProject, tgId }) {
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
    sprint_id: '',
  });
  const [sprintForm, setSprintForm] = useState({
    title: '',
    start_date: '',
    end_date: '',
  });
  const [expandedSprints, setExpandedSprints] = useState({});
  const [taskDetails, setTaskDetails] = useState(null);
  const [taskDetailsEditing, setTaskDetailsEditing] = useState({
    title: false,
    description: false,
    status: false,
    execution_hours: false,
  });
  const [comments, setComments] = useState([]);
  const [commentsLoading, setCommentsLoading] = useState(false);
  const [commentText, setCommentText] = useState('');
  const [taskHistory, setTaskHistory] = useState([]);
  const [taskHistoryLoading, setTaskHistoryLoading] = useState(false);
  const [showTaskHistoryModal, setShowTaskHistoryModal] = useState(false);
  const [taskReadMap, setTaskReadMap] = useState({});

  const isTaskDetailsEditing = useMemo(
    () => Object.values(taskDetailsEditing).some(Boolean),
    [taskDetailsEditing]
  );
  const backlogTasks = useMemo(() => tasks.filter((task) => task.sprint_id == null), [tasks]);

  function taskReadStorageKey(projectId, userTgId) {
    return `vkr-task-read:${userTgId}:${projectId}`;
  }

  useEffect(() => {
    if (!selectedProject?.id || !tgId) {
      setTaskReadMap({});
      return;
    }
    const key = taskReadStorageKey(selectedProject.id, tgId);
    try {
      const raw = window.localStorage.getItem(key);
      if (!raw) {
        setTaskReadMap({});
        return;
      }
      const parsed = JSON.parse(raw);
      setTaskReadMap(parsed && typeof parsed === 'object' ? parsed : {});
    } catch {
      setTaskReadMap({});
    }
  }, [selectedProject?.id, tgId]);

  useEffect(() => {
    if (!selectedProject?.id || !tgId) return;
    const key = taskReadStorageKey(selectedProject.id, tgId);
    try {
      window.localStorage.setItem(key, JSON.stringify(taskReadMap));
    } catch {
      // ignore localStorage failures
    }
  }, [taskReadMap, selectedProject?.id, tgId]);

  const loadBoard = useCallback(async (projectId, userTgId) => {
    const apiBase = getApiBase();
    setBoardLoading(true);
    setBoardError(null);
    try {
      const [tasksRes, sprintsRes] = await Promise.all([
        fetch(`${apiBase}/projects/${projectId}/tasks?tg_id=${encodeURIComponent(userTgId)}`),
        fetch(`${apiBase}/projects/${projectId}/sprints?tg_id=${encodeURIComponent(userTgId)}`),
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
  }, []);

  useEffect(() => {
    if (!selectedProject?.id || !tgId) return;
    loadBoard(selectedProject.id, tgId);
  }, [selectedProject?.id, tgId, loadBoard]);

  const updateTask = useCallback(async (taskId, fields) => {
    if (!tgId) return;
    const apiBase = getApiBase();
    const response = await fetch(`${apiBase}/tasks/${taskId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tg_id: tgId, ...fields }),
    });
    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}));
      throw new Error(errorPayload?.detail || `Task update failed ${response.status}`);
    }
  }, [tgId]);

  const createTask = useCallback(async (event) => {
    event.preventDefault();
    if (!selectedProject?.id || !tgId) return;
    const apiBase = getApiBase();
    try {
      const response = await fetch(`${apiBase}/projects/${selectedProject.id}/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tg_id: tgId,
          title: taskForm.title,
          description: taskForm.description,
          execution_hours: taskForm.execution_hours ? Number(taskForm.execution_hours) : null,
          status: taskForm.status,
          sprint_id: taskForm.sprint_id ? Number(taskForm.sprint_id) : null,
        }),
      });
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({}));
        throw new Error(errorPayload?.detail || `Task create failed ${response.status}`);
      }
      setTaskForm({ title: '', description: '', execution_hours: '', status: 'NEW', sprint_id: '' });
      setShowTaskModal(false);
      await loadBoard(selectedProject.id, tgId);
    } catch (error) {
      setBoardError(`Не удалось создать задачу. ${error?.message ?? ''}`.trim());
    }
  }, [selectedProject?.id, tgId, taskForm, loadBoard]);

  const createSprint = useCallback(async (event) => {
    event.preventDefault();
    if (!selectedProject?.id || !tgId) return;
    const apiBase = getApiBase();
    try {
      const response = await fetch(`${apiBase}/projects/${selectedProject.id}/sprints`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tg_id: tgId,
          title: sprintForm.title,
          start_date: sprintForm.start_date || null,
          end_date: sprintForm.end_date || null,
        }),
      });
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({}));
        throw new Error(errorPayload?.detail || `Sprint create failed ${response.status}`);
      }
      setSprintForm({ title: '', start_date: '', end_date: '' });
      setShowSprintModal(false);
      await loadBoard(selectedProject.id, tgId);
    } catch (error) {
      setBoardError(`Не удалось создать спринт. ${error?.message ?? ''}`.trim());
    }
  }, [selectedProject?.id, tgId, sprintForm, loadBoard]);

  const moveTaskToSprint = useCallback(async (taskId, sprintId) => {
    try {
      await updateTask(taskId, { sprint_id: sprintId });
      if (selectedProject?.id && tgId) {
        await loadBoard(selectedProject.id, tgId);
      }
    } catch (error) {
      setBoardError(`Не удалось переместить задачу в спринт. ${error?.message ?? ''}`.trim());
    }
  }, [updateTask, selectedProject?.id, tgId, loadBoard]);

  const deleteSprint = useCallback(async (sprintId, sprintTitle) => {
    if (!tgId || !selectedProject?.id) return;
    const confirmed = window.confirm(`Удалить спринт "${sprintTitle}"? Задачи останутся и перейдут в общий список.`);
    if (!confirmed) return;
    try {
      const apiBase = getApiBase();
      const response = await fetch(
        `${apiBase}/sprints/${encodeURIComponent(sprintId)}?tg_id=${encodeURIComponent(tgId)}`,
        { method: 'DELETE' }
      );
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({}));
        throw new Error(errorPayload?.detail || `Sprint delete failed ${response.status}`);
      }
      await loadBoard(selectedProject.id, tgId);
    } catch (error) {
      setBoardError(`Не удалось удалить спринт. ${error?.message ?? ''}`.trim());
    }
  }, [tgId, selectedProject?.id, loadBoard]);

  const closeTaskDetails = useCallback(() => {
    setTaskDetails(null);
    setShowTaskHistoryModal(false);
    setTaskDetailsEditing({ title: false, description: false, status: false, execution_hours: false });
    setCommentText('');
    setTaskHistory([]);
  }, []);

  const deleteTask = useCallback(async (taskId, taskTitle) => {
    if (!tgId || !selectedProject?.id) return;
    const confirmed = window.confirm(`Удалить задачу "${taskTitle}"? Комментарии также будут удалены.`);
    if (!confirmed) return;
    try {
      const apiBase = getApiBase();
      const response = await fetch(
        `${apiBase}/tasks/${encodeURIComponent(taskId)}?tg_id=${encodeURIComponent(tgId)}`,
        { method: 'DELETE' }
      );
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({}));
        throw new Error(errorPayload?.detail || `Task delete failed ${response.status}`);
      }
      if (taskDetails?.id === taskId) closeTaskDetails();
      await loadBoard(selectedProject.id, tgId);
    } catch (error) {
      setBoardError(`Не удалось удалить задачу. ${error?.message ?? ''}`.trim());
    }
  }, [tgId, selectedProject?.id, taskDetails?.id, closeTaskDetails, loadBoard]);

  const markTaskCommentsRead = useCallback((taskId, readAt) => {
    const at = toTimeMs(readAt) || Date.now();
    setTaskReadMap((prev) => ({ ...prev, [String(taskId)]: at }));
  }, []);

  const taskUnreadCount = useCallback((task) => {
    const total = Number(task?.comment_count ?? 0);
    if (total <= 0) return 0;
    const backendUnread = Math.max(0, Number(task?.unread_comment_count ?? 0));
    const lastCommentAtMs = toTimeMs(task?.last_comment_at);
    const lastReadMs = Number(taskReadMap[String(task?.id)] ?? 0);
    if (lastReadMs > 0 && lastCommentAtMs > 0 && lastReadMs >= lastCommentAtMs) return 0;
    return backendUnread;
  }, [taskReadMap]);

  const loadTaskComments = useCallback(async (taskId) => {
    if (!tgId) return;
    setCommentsLoading(true);
    try {
      const apiBase = getApiBase();
      const response = await fetch(`${apiBase}/tasks/${taskId}/comments?tg_id=${encodeURIComponent(tgId)}`);
      if (!response.ok) {
        throw new Error(`Comments failed ${response.status}`);
      }
      const data = await response.json();
      const items = Array.isArray(data?.comments) ? data.comments : [];
      setComments(items);
      const lastCommentAt = items.length ? items[items.length - 1]?.created_at : null;
      markTaskCommentsRead(taskId, lastCommentAt);
      setTasks((prev) =>
        prev.map((task) =>
          task.id === taskId
            ? {
                ...task,
                comment_count: items.length,
                unread_comment_count: 0,
                last_comment_at: lastCommentAt || task.last_comment_at,
              }
            : task
        )
      );
    } catch (error) {
      setBoardError(`Не удалось загрузить комментарии. ${error?.message ?? ''}`.trim());
      setComments([]);
    } finally {
      setCommentsLoading(false);
    }
  }, [tgId, markTaskCommentsRead]);

  const loadTaskHistory = useCallback(async (taskId) => {
    if (!tgId) return;
    setTaskHistoryLoading(true);
    try {
      const apiBase = getApiBase();
      const response = await fetch(`${apiBase}/tasks/${taskId}/history?tg_id=${encodeURIComponent(tgId)}`);
      if (!response.ok) {
        if (response.status === 404) {
          setTaskHistory([]);
          return;
        }
        throw new Error(`History failed ${response.status}`);
      }
      const data = await response.json();
      setTaskHistory(Array.isArray(data?.history) ? data.history : []);
    } catch (error) {
      setBoardError(`Не удалось загрузить историю изменений. ${error?.message ?? ''}`.trim());
      setTaskHistory([]);
    } finally {
      setTaskHistoryLoading(false);
    }
  }, [tgId]);

  const openTaskDetails = useCallback((task) => {
    setTaskDetails({ ...task, execution_hours: task.execution_hours ?? '' });
    setTaskDetailsEditing({ title: false, description: false, status: false, execution_hours: false });
    setCommentText('');
    void loadTaskComments(task.id);
    void loadTaskHistory(task.id);
  }, [loadTaskComments, loadTaskHistory]);

  const saveTaskDetails = useCallback(async (event) => {
    event.preventDefault();
    if (!taskDetails?.id) return;
    try {
      await updateTask(taskDetails.id, {
        title: taskDetails.title,
        description: taskDetails.description,
        status: taskDetails.status,
        execution_hours: taskDetails.execution_hours === '' ? null : Number(taskDetails.execution_hours),
      });
      if (selectedProject?.id && tgId) {
        await loadBoard(selectedProject.id, tgId);
      }
      closeTaskDetails();
    } catch (error) {
      setBoardError(`Не удалось сохранить задачу. ${error?.message ?? ''}`.trim());
    }
  }, [taskDetails, updateTask, selectedProject?.id, tgId, loadBoard, closeTaskDetails]);

  const createComment = useCallback(async (event) => {
    event.preventDefault();
    if (!taskDetails?.id || !commentText.trim() || !tgId) return;
    try {
      const apiBase = getApiBase();
      const response = await fetch(`${apiBase}/tasks/${taskDetails.id}/comments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tg_id: tgId, text: commentText.trim() }),
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
  }, [taskDetails?.id, commentText, tgId, loadTaskComments]);

  const sprintTasksSorted = useCallback((sprintId) => {
    const order = { DONE: 0, IN_PROGRESS: 1, NEW: 2 };
    return tasks
      .filter((task) => task.sprint_id === sprintId)
      .sort((a, b) => {
        const statusDiff = (order[a.status] ?? 9) - (order[b.status] ?? 9);
        if (statusDiff !== 0) return statusDiff;
        return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
      });
  }, [tasks]);

  const toggleSprint = useCallback((sprintId, current) => {
    setExpandedSprints((prev) => ({ ...prev, [sprintId]: !current }));
  }, []);

  return {
    tasks,
    sprints,
    boardLoading,
    boardError,
    setBoardError,
    showTaskModal,
    setShowTaskModal,
    showSprintModal,
    setShowSprintModal,
    taskForm,
    setTaskForm,
    sprintForm,
    setSprintForm,
    expandedSprints,
    taskDetails,
    setTaskDetails,
    taskDetailsEditing,
    setTaskDetailsEditing,
    comments,
    commentsLoading,
    commentText,
    setCommentText,
    taskHistory,
    taskHistoryLoading,
    showTaskHistoryModal,
    setShowTaskHistoryModal,
    isTaskDetailsEditing,
    backlogTasks,
    createTask,
    createSprint,
    moveTaskToSprint,
    deleteSprint,
    deleteTask,
    taskUnreadCount,
    openTaskDetails,
    closeTaskDetails,
    saveTaskDetails,
    createComment,
    sprintTasksSorted,
    toggleSprint,
  };
}

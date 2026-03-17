import React from 'react';

import ProjectBoardView from './components/ProjectBoardView';
import ProjectSelectionView from './components/ProjectSelectionView';
import { useBoard } from './hooks/useBoard';
import { useProjects } from './hooks/useProjects';

const STATUS_OPTIONS = [
  { value: 'NEW', label: 'Запланирован', progress: 33 },
  { value: 'IN_PROGRESS', label: 'В работе', progress: 66 },
  { value: 'DONE', label: 'Готово', progress: 100 },
];

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
    minute: '2-digit',
  });
}

function historyEventLabel(eventType) {
  if (eventType === 'CREATE') return 'Создание задачи';
  if (eventType === 'STATUS_CHANGE') return 'Изменение статуса';
  return 'Изменение задачи';
}

function historyFieldLabel(field) {
  if (field === 'title') return 'Название';
  if (field === 'description') return 'Описание';
  if (field === 'status') return 'Статус';
  if (field === 'execution_hours') return 'Время выполнения';
  if (field === 'sprint_id') return 'Спринт';
  return field || 'Поле';
}

function historyValueLabel(value, field) {
  if (value == null || value === '') return '—';
  if (field === 'status' && typeof value === 'string') return statusMeta(value).label;
  if (field === 'execution_hours') return `${value} ч`;
  if (field === 'sprint_id') return value ? `#${value}` : 'Без спринта';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
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
  const projects = useProjects();
  const board = useBoard({
    selectedProject: projects.selectedProject,
    tgId: projects.authState.user?.tg_id,
  });

  if (projects.selectedProject) {
    return (
      <ProjectBoardView
        selectedProject={projects.selectedProject}
        onBack={() => projects.setSelectedProject(null)}
        boardError={board.boardError}
        boardLoading={board.boardLoading}
        onOpenTaskModal={() => board.setShowTaskModal(true)}
        onOpenSprintModal={() => board.setShowSprintModal(true)}
        backlogTasks={board.backlogTasks}
        taskUnreadCount={board.taskUnreadCount}
        onDeleteTask={board.deleteTask}
        onOpenTaskDetails={board.openTaskDetails}
        TaskProgressComponent={TaskProgress}
        sprints={board.sprints}
        sprintTasksSorted={board.sprintTasksSorted}
        expandedSprints={board.expandedSprints}
        toggleSprint={board.toggleSprint}
        moveTaskToSprint={board.moveTaskToSprint}
        setTaskForm={board.setTaskForm}
        showTaskModal={board.showTaskModal}
        setShowTaskModal={board.setShowTaskModal}
        createTask={board.createTask}
        taskForm={board.taskForm}
        setTaskFormState={board.setTaskForm}
        statusOptions={STATUS_OPTIONS}
        showSprintModal={board.showSprintModal}
        setShowSprintModal={board.setShowSprintModal}
        createSprint={board.createSprint}
        sprintForm={board.sprintForm}
        setSprintForm={board.setSprintForm}
        onDeleteSprint={board.deleteSprint}
        toSprintDateLabel={toSprintDateLabel}
        taskDetails={board.taskDetails}
        closeTaskDetails={board.closeTaskDetails}
        setShowTaskHistoryModal={board.setShowTaskHistoryModal}
        saveTaskDetails={board.saveTaskDetails}
        taskDetailsEditing={board.taskDetailsEditing}
        setTaskDetailsEditing={board.setTaskDetailsEditing}
        setTaskDetails={board.setTaskDetails}
        isTaskDetailsEditing={board.isTaskDetailsEditing}
        commentsLoading={board.commentsLoading}
        comments={board.comments}
        commentText={board.commentText}
        setCommentText={board.setCommentText}
        createComment={board.createComment}
        toDeadlineLabel={toDeadlineLabel}
        showTaskHistoryModal={board.showTaskHistoryModal}
        taskHistoryLoading={board.taskHistoryLoading}
        taskHistory={board.taskHistory}
        historyEventLabel={historyEventLabel}
        historyFieldLabel={historyFieldLabel}
        historyValueLabel={historyValueLabel}
      />
    );
  }

  return (
    <ProjectSelectionView
      authState={projects.authState}
      projectsError={projects.projectsError}
      projectsLoading={projects.projectsLoading}
      visibleProjects={projects.visibleProjects}
      query={projects.query}
      setQuery={projects.setQuery}
      onSelectProject={projects.setSelectedProject}
      onDeleteProject={projects.deleteProject}
      deletingProjectId={projects.deletingProjectId}
      openProfile={projects.openProfile}
      toDisplayName={toDisplayName}
      toInitials={toInitials}
    />
  );
}

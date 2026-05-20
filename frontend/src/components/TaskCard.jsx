import React from 'react';

export default function TaskCard({
  task,
  unreadCount,
  onDelete,
  onOpen,
  TaskProgressComponent,
  draggable = false,
  onDragStart,
}) {
  const executionHoursLabel = task.execution_hours ? `${task.execution_hours} ч` : 'Без оценки';
  const commentsCount = task.comment_count ?? 0;

  return (
    <article className="task-card" draggable={draggable} onDragStart={onDragStart}>
      <button
        type="button"
        className="task-delete-btn"
        onClick={(event) => {
          event.stopPropagation();
          onDelete(task);
        }}
        aria-label="Удалить задачу"
        title="Удалить задачу"
      >
        ×
      </button>
      <button type="button" className="task-open" onClick={() => onOpen(task)}>
        <div className="task-headline">
          <span className="task-kind">Задача</span>
          <div className="task-inline-meta">
            <span className="task-chip">v{task.version ?? 1}</span>
            <span className="task-chip">⏱ {executionHoursLabel}</span>
            <span className={`task-chip task-comments ${unreadCount > 0 ? 'unread' : ''}`}>
              💬 {commentsCount}
              {unreadCount > 0 && <span className="unread-badge">{unreadCount}</span>}
            </span>
          </div>
        </div>
        <strong className="task-title">{task.title}</strong>
        <span className="task-description">{task.description || 'Без описания'}</span>
      </button>
      <TaskProgressComponent status={task.status} />
    </article>
  );
}

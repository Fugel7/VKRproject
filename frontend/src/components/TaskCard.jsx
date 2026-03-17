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
        🗑
      </button>
      <button type="button" className="task-open" onClick={() => onOpen(task)}>
        <span className="task-kind">Задача · v{task.version ?? 1}</span>
        <strong>{task.title}</strong>
        <span>{task.description || 'Без описания'}</span>
      </button>
      <TaskProgressComponent status={task.status} />
      <div className="task-meta">
        <div className="task-meta-row">
          <span>Время выполнения: {task.execution_hours ? `${task.execution_hours} ч` : 'не указано'}</span>
        </div>
        <div className="task-meta-row">
          <span className={`task-comments ${unreadCount > 0 ? 'unread' : ''}`}>
            💬 {task.comment_count ?? 0}
            {unreadCount > 0 && <span className="unread-badge">{unreadCount}</span>}
          </span>
        </div>
      </div>
    </article>
  );
}

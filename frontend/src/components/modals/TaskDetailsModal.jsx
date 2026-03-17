import React from 'react';

export default function TaskDetailsModal({
  taskDetails,
  onClose,
  onOpenHistory,
  onSubmit,
  taskDetailsEditing,
  setTaskDetailsEditing,
  setTaskDetails,
  statusOptions,
  isTaskDetailsEditing,
  commentsLoading,
  comments,
  commentText,
  setCommentText,
  onCreateComment,
  toDeadlineLabel
}) {
  if (!taskDetails) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <section className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>
            Задача ·{' '}
            <button type="button" className="version-link-btn" onClick={onOpenHistory} title="Открыть историю версий">
              v{taskDetails.version ?? 1}
            </button>
          </h3>
          <button type="button" className="modal-close-btn" onClick={onClose} aria-label="Закрыть окно">
            ×
          </button>
        </div>
        <form onSubmit={onSubmit} className="form-card">
          <label className="field">
            <div className="field-top">
              <span>Название</span>
              <button
                type="button"
                className="edit-icon-btn"
                onClick={() => setTaskDetailsEditing((prev) => ({ ...prev, title: true }))}
                aria-label="Редактировать название"
                title="Редактировать название"
              >
                ✎
              </button>
            </div>
            <input
              className="search task-details-input"
              value={taskDetails.title}
              readOnly={!taskDetailsEditing.title}
              onChange={(e) => setTaskDetails((prev) => ({ ...prev, title: e.target.value }))}
              required
            />
          </label>
          <label className="field">
            <div className="field-top">
              <span>Описание</span>
              <button
                type="button"
                className="edit-icon-btn"
                onClick={() => setTaskDetailsEditing((prev) => ({ ...prev, description: true }))}
                aria-label="Редактировать описание"
                title="Редактировать описание"
              >
                ✎
              </button>
            </div>
            <textarea
              className="textarea"
              value={taskDetails.description ?? ''}
              readOnly={!taskDetailsEditing.description}
              onChange={(e) => setTaskDetails((prev) => ({ ...prev, description: e.target.value }))}
            />
          </label>
          <div className="form-row">
            <label className="field">
              <div className="field-top">
                <span>Статус</span>
                <button
                  type="button"
                  className="edit-icon-btn"
                  onClick={() => setTaskDetailsEditing((prev) => ({ ...prev, status: true }))}
                  aria-label="Редактировать статус"
                  title="Редактировать статус"
                >
                  ✎
                </button>
              </div>
              <select
                value={taskDetails.status}
                disabled={!taskDetailsEditing.status}
                onChange={(e) => setTaskDetails((prev) => ({ ...prev, status: e.target.value }))}
              >
                {statusOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <div className="field-top">
                <span>Время выполнения (ч)</span>
                <button
                  type="button"
                  className="edit-icon-btn"
                  onClick={() => setTaskDetailsEditing((prev) => ({ ...prev, execution_hours: true }))}
                  aria-label="Редактировать время выполнения"
                  title="Редактировать время выполнения"
                >
                  ✎
                </button>
              </div>
              <input
                type="number"
                min="1"
                value={taskDetails.execution_hours ?? ''}
                readOnly={!taskDetailsEditing.execution_hours}
                onChange={(e) => setTaskDetails((prev) => ({ ...prev, execution_hours: e.target.value }))}
                placeholder="Например: 8"
              />
            </label>
          </div>
          {isTaskDetailsEditing && (
            <button className="open-btn" type="submit">
              Сохранить задачу
            </button>
          )}
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
        <form className="comment-form" onSubmit={onCreateComment}>
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
  );
}

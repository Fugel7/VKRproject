import React, { useEffect, useRef } from 'react';

export default function TaskDetailsModal({
  taskDetails,
  onClose,
  onOpenHistory,
  onSubmit,
  taskDetailsEditing,
  setTaskDetails,
  startTaskFieldEdit,
  cancelTaskFieldEdit,
  statusOptions,
  sprints,
  isTaskDetailsEditing,
  commentsLoading,
  comments,
  commentText,
  setCommentText,
  onCreateComment,
  toDeadlineLabel
}) {
  const titleRef = useRef(null);
  const descriptionRef = useRef(null);
  const statusRef = useRef(null);
  const executionHoursRef = useRef(null);
  const sprintRef = useRef(null);

  useEffect(() => {
    if (taskDetailsEditing.title && titleRef.current) {
      titleRef.current.focus();
      titleRef.current.select();
    }
  }, [taskDetailsEditing.title]);

  useEffect(() => {
    if (taskDetailsEditing.description && descriptionRef.current) {
      descriptionRef.current.focus();
      descriptionRef.current.setSelectionRange?.(descriptionRef.current.value.length, descriptionRef.current.value.length);
    }
  }, [taskDetailsEditing.description]);

  useEffect(() => {
    if (taskDetailsEditing.status && statusRef.current) {
      statusRef.current.focus();
    }
  }, [taskDetailsEditing.status]);

  useEffect(() => {
    if (taskDetailsEditing.execution_hours && executionHoursRef.current) {
      executionHoursRef.current.focus();
      executionHoursRef.current.select?.();
    }
  }, [taskDetailsEditing.execution_hours]);

  useEffect(() => {
    if (taskDetailsEditing.sprint_id && sprintRef.current) {
      sprintRef.current.focus();
    }
  }, [taskDetailsEditing.sprint_id]);

  if (!taskDetails) return null;

  function renderEditButton(field, label) {
    const isEditing = !!taskDetailsEditing[field];
    return (
      <button
        type="button"
        className={`edit-icon-btn ${isEditing ? 'editing' : ''}`}
        onClick={() => (isEditing ? cancelTaskFieldEdit(field) : startTaskFieldEdit(field))}
        aria-label={isEditing ? `Отменить редактирование поля: ${label}` : `Редактировать поле: ${label}`}
        title={isEditing ? 'Отменить изменение' : `Редактировать: ${label}`}
      >
        {isEditing ? '×' : '✎'}
      </button>
    );
  }

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
          <label className={`field ${taskDetailsEditing.title ? 'is-editing' : 'is-readonly'}`}>
            <div className="field-top">
              <span>Название</span>
              {renderEditButton('title', 'Название')}
            </div>
            <input
              ref={titleRef}
              className="search task-details-input"
              value={taskDetails.title}
              readOnly={!taskDetailsEditing.title}
              onChange={(e) => setTaskDetails((prev) => ({ ...prev, title: e.target.value }))}
              required
            />
          </label>
          <label className={`field ${taskDetailsEditing.description ? 'is-editing' : 'is-readonly'}`}>
            <div className="field-top">
              <span>Описание</span>
              {renderEditButton('description', 'Описание')}
            </div>
            <textarea
              ref={descriptionRef}
              className="textarea"
              value={taskDetails.description ?? ''}
              readOnly={!taskDetailsEditing.description}
              onChange={(e) => setTaskDetails((prev) => ({ ...prev, description: e.target.value }))}
            />
          </label>
          <div className="form-row">
            <label className={`field ${taskDetailsEditing.status ? 'is-editing' : 'is-readonly'}`}>
              <div className="field-top">
                <span>Статус</span>
                {renderEditButton('status', 'Статус')}
              </div>
              <select
                ref={statusRef}
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
            <label className={`field ${taskDetailsEditing.execution_hours ? 'is-editing' : 'is-readonly'}`}>
              <div className="field-top">
                <span>Время выполнения (ч)</span>
                {renderEditButton('execution_hours', 'Время выполнения')}
              </div>
              <input
                ref={executionHoursRef}
                type="number"
                min="1"
                value={taskDetails.execution_hours ?? ''}
                readOnly={!taskDetailsEditing.execution_hours}
                onChange={(e) => setTaskDetails((prev) => ({ ...prev, execution_hours: e.target.value }))}
                placeholder="Например: 8"
              />
            </label>
          </div>
          <label className={`field ${taskDetailsEditing.sprint_id ? 'is-editing' : 'is-readonly'}`}>
            <div className="field-top">
              <span>Спринт</span>
              {renderEditButton('sprint_id', 'Спринт')}
            </div>
            <select
              ref={sprintRef}
              value={taskDetails.sprint_id ?? ''}
              disabled={!taskDetailsEditing.sprint_id}
              onChange={(e) => setTaskDetails((prev) => ({ ...prev, sprint_id: e.target.value }))}
            >
              <option value="">Без спринта</option>
              {sprints.map((sprint) => (
                <option key={sprint.id} value={String(sprint.id)}>
                  {sprint.title}
                </option>
              ))}
            </select>
          </label>
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

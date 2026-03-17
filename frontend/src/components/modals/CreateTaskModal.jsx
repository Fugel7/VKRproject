import React from 'react';

export default function CreateTaskModal({
  show,
  onClose,
  onSubmit,
  taskForm,
  setTaskForm,
  sprints,
  statusOptions
}) {
  if (!show) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <section className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>Создать задачу</h3>
          <button type="button" className="modal-close-btn" onClick={onClose} aria-label="Закрыть окно">
            ×
          </button>
        </div>
        <form className="form-card" onSubmit={onSubmit}>
          <input
            className="search"
            placeholder="Название"
            value={taskForm.title}
            onChange={(e) => setTaskForm((prev) => ({ ...prev, title: e.target.value }))}
            required
          />
          <textarea
            className="textarea"
            placeholder="Описание"
            value={taskForm.description}
            onChange={(e) => setTaskForm((prev) => ({ ...prev, description: e.target.value }))}
          />
          <div className="form-row">
            <label className="field">
              <span>Время выполнения (ч)</span>
              <input
                type="number"
                min="1"
                value={taskForm.execution_hours}
                onChange={(e) => setTaskForm((prev) => ({ ...prev, execution_hours: e.target.value }))}
                placeholder="Например: 8"
              />
            </label>
            <label className="field">
              <span>Статус</span>
              <select value={taskForm.status} onChange={(e) => setTaskForm((prev) => ({ ...prev, status: e.target.value }))}>
                {statusOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Спринт</span>
              <select value={taskForm.sprint_id} onChange={(e) => setTaskForm((prev) => ({ ...prev, sprint_id: e.target.value }))}>
                <option value="">Без спринта</option>
                {sprints.map((sprint) => (
                  <option key={sprint.id} value={sprint.id}>
                    {sprint.title}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="meta">
            <button className="open-btn" type="submit">
              Создать задачу
            </button>
            <button className="back-btn" type="button" onClick={onClose}>
              Отмена
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

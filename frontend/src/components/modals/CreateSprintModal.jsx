import React from 'react';

export default function CreateSprintModal({ show, onClose, onSubmit, sprintForm, setSprintForm }) {
  if (!show) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <section className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>Создать спринт</h3>
          <button type="button" className="modal-close-btn" onClick={onClose} aria-label="Закрыть окно">
            ×
          </button>
        </div>
        <form className="form-card" onSubmit={onSubmit}>
          <input
            className="search"
            placeholder="Название спринта"
            value={sprintForm.title}
            onChange={(e) => setSprintForm((prev) => ({ ...prev, title: e.target.value }))}
            required
          />
          <div className="form-row">
            <label className="field">
              <span>Дата начала</span>
              <input
                type="date"
                value={sprintForm.start_date}
                onChange={(e) => setSprintForm((prev) => ({ ...prev, start_date: e.target.value }))}
              />
            </label>
            <label className="field">
              <span>Дата конца</span>
              <input
                type="date"
                value={sprintForm.end_date}
                onChange={(e) => setSprintForm((prev) => ({ ...prev, end_date: e.target.value }))}
              />
            </label>
          </div>
          <div className="meta">
            <button className="open-btn" type="submit">
              Создать спринт
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

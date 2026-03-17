import React from 'react';

export default function TaskHistoryModal({
  show,
  onClose,
  taskVersion,
  taskHistoryLoading,
  taskHistory,
  historyEventLabel,
  historyFieldLabel,
  historyValueLabel,
  toDeadlineLabel
}) {
  if (!show) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <section className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>История версий · v{taskVersion ?? 1}</h3>
          <button type="button" className="modal-close-btn" onClick={onClose} aria-label="Закрыть окно">
            ×
          </button>
        </div>
        <div className="history-list">
          {taskHistoryLoading && <div className="empty compact">Загружаем историю...</div>}
          {!taskHistoryLoading && taskHistory.length === 0 && <div className="empty compact">Изменений пока нет</div>}
          {!taskHistoryLoading &&
            taskHistory.map((item) => {
              const actorName =
                [item.first_name, item.last_name].filter(Boolean).join(' ').trim() ||
                item.username ||
                `User ${item.actor_id}`;
              return (
                <article className="history-card" key={item.id}>
                  <strong>{historyEventLabel(item.event_type)}</strong>
                  {item.field && (
                    <p className="history-change">
                      <span>{historyFieldLabel(item.field)}:</span>{' '}
                      <span>
                        {historyValueLabel(item.old_value, item.field)} → {historyValueLabel(item.new_value, item.field)}
                      </span>
                    </p>
                  )}
                  {!item.field && item.new_value && <p className="history-change">Создана с начальными данными.</p>}
                  <span>
                    {toDeadlineLabel(item.created_at)} · {actorName}
                  </span>
                </article>
              );
            })}
        </div>
      </section>
    </div>
  );
}

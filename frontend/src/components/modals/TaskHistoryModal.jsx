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

  const groupedHistory = taskHistory.reduce((groups, item) => {
    const lastGroup = groups[groups.length - 1];
    const canMerge =
      lastGroup &&
      lastGroup.actor_id === item.actor_id &&
      lastGroup.created_at === item.created_at;

    if (canMerge) {
      lastGroup.items.push(item);
      return groups;
    }

    groups.push({
      id: item.id,
      actor_id: item.actor_id,
      first_name: item.first_name,
      last_name: item.last_name,
      username: item.username,
      created_at: item.created_at,
      items: [item],
    });
    return groups;
  }, []);

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
            groupedHistory.map((group) => {
              const actorName =
                [group.first_name, group.last_name].filter(Boolean).join(' ').trim() ||
                group.username ||
                `User ${group.actor_id}`;
              const primaryItem = group.items[0];
              const changedItems = group.items.filter((entry) => entry.field);
              const hasCreateItem = group.items.some((entry) => !entry.field && entry.new_value);
              const title =
                hasCreateItem
                  ? historyEventLabel('CREATE')
                  : group.items.length > 1
                    ? 'Изменение задачи'
                    : historyEventLabel(primaryItem.event_type);

              return (
                <article className="history-card" key={group.id}>
                  <strong>{title}</strong>
                  {changedItems.map((entry) => (
                    <p className="history-change" key={entry.id}>
                      <span>{historyFieldLabel(entry.field)}:</span>{' '}
                      <span>
                        {historyValueLabel(entry.old_value, entry.field)} → {historyValueLabel(entry.new_value, entry.field)}
                      </span>
                    </p>
                  ))}
                  {hasCreateItem && <p className="history-change">Создана с начальными данными.</p>}
                  <span>
                    {toDeadlineLabel(group.created_at)} · {actorName}
                  </span>
                </article>
              );
            })}
        </div>
      </section>
    </div>
  );
}

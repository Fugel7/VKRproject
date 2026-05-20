import React from 'react';

export default function ConfirmModal({
  show,
  title,
  message,
  confirmLabel = 'Подтвердить',
  cancelLabel = 'Отмена',
  confirmVariant = '',
  onConfirm,
  onCancel,
  busy = false,
}) {
  if (!show) return null;

  return (
    <div className="modal-overlay" onClick={busy ? undefined : onCancel}>
      <section className="modal-card confirm-modal" onClick={(event) => event.stopPropagation()}>
        <div className="modal-head">
          <h3>{title || 'Подтвердите действие'}</h3>
          <button
            type="button"
            className="modal-close-btn"
            onClick={onCancel}
            aria-label="Закрыть окно"
            disabled={busy}
          >
            ×
          </button>
        </div>
        <p className="confirm-message">{message}</p>
        <div className="confirm-actions">
          <button type="button" className="back-btn confirm-cancel-btn" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </button>
          <button
            type="button"
            className={`open-btn ${confirmVariant === 'danger' ? 'danger-btn' : ''}`.trim()}
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? 'Выполняем...' : confirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}

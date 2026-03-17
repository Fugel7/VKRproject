export function getApiBase() {
  const { hostname, port } = window.location;
  if (port === '5173' && (hostname === '127.0.0.1' || hostname === 'localhost')) {
    return 'http://127.0.0.1:8000';
  }
  return '/api';
}

export function toTimeMs(value) {
  if (!value) return 0;
  const dt = new Date(value);
  const ms = dt.getTime();
  return Number.isNaN(ms) ? 0 : ms;
}

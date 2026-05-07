import assert from 'node:assert/strict';
import test from 'node:test';

import { getApiBase, toTimeMs } from './api.js';

function withLocation(hostname, port, fn) {
  const previousWindow = globalThis.window;
  globalThis.window = { location: { hostname, port } };
  try {
    fn();
  } finally {
    globalThis.window = previousWindow;
  }
}

test('getApiBase returns backend URL during local Vite development', () => {
  withLocation('localhost', '5173', () => {
    assert.equal(getApiBase(), 'http://127.0.0.1:8000');
  });

  withLocation('127.0.0.1', '5173', () => {
    assert.equal(getApiBase(), 'http://127.0.0.1:8000');
  });
});

test('getApiBase returns reverse proxy path outside local Vite', () => {
  withLocation('example.com', '', () => {
    assert.equal(getApiBase(), '/api');
  });
});

test('toTimeMs converts valid dates and rejects invalid values', () => {
  assert.equal(toTimeMs(null), 0);
  assert.equal(toTimeMs('not a date'), 0);
  assert.equal(toTimeMs('2026-04-22T00:00:00Z'), Date.parse('2026-04-22T00:00:00Z'));
});

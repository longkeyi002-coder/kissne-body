import { beforeEach, expect, test, vi } from 'vitest';

async function historyScope() {
  vi.resetModules();
  globalThis.window = { KissneNativeTransport: { request() {} } };
  await import('../kissne-prototype/prototype/transport.js');
  return window.KissneHistoryScope;
}

beforeEach(() => {
  delete globalThis.window;
});

test('ordinary chat requests the continuous timeline on every page', async () => {
  const scope = await historyScope();
  const calls = [];
  const transport = {
    history(limit, before, sessionId) {
      calls.push({ limit, before, sessionId });
      return Promise.resolve({ messages: [], has_more: false });
    }
  };
  await scope.request(transport, 50, '', '', 'active-room');
  await scope.request(transport, 50, 'older-ref', '', 'active-room');
  expect(calls).toEqual([
    { limit: 50, before: '', sessionId: '' },
    { limit: 50, before: 'older-ref', sessionId: '' }
  ]);
});

test('a room chosen from the picker stays scoped while paging', async () => {
  const scope = await historyScope();
  const calls = [];
  const transport = {
    history(limit, before, sessionId) {
      calls.push({ limit, before, sessionId });
      return Promise.resolve({ messages: [], has_more: false });
    }
  };
  await scope.request(transport, 50, '', 'chosen-room', 'chosen-room');
  await scope.request(transport, 50, 'older-ref', 'chosen-room', 'chosen-room');
  expect(calls.map(call => call.sessionId)).toEqual(['chosen-room', 'chosen-room']);
  expect(calls[1].before).toBe('older-ref');
});

test('a stale picker selection does not scope a newly bound room', async () => {
  const scope = await historyScope();
  const calls = [];
  const transport = {
    history(_limit, _before, sessionId) {
      calls.push(sessionId);
      return Promise.resolve({});
    }
  };
  await scope.request(transport, 50, '', 'previous-room', 'new-room');
  expect(calls).toEqual(['']);
});

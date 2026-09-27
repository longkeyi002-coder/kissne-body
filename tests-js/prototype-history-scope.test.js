import { afterEach, beforeEach, expect, test, vi } from 'vitest';

async function historyScope() {
  vi.resetModules();
  globalThis.window = { KissneNativeTransport: { request() {} } };
  await import('../kissne-prototype/prototype/transport.js');
  return globalThis.window.KissneHistoryScope;
}

beforeEach(() => {
  delete globalThis.window;
});
afterEach(() => vi.unstubAllGlobals());

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

test('web history request forwards the chosen room to the server', async () => {
  vi.resetModules();
  vi.stubGlobal('window', {});
  vi.stubGlobal('location', { protocol: 'https:', origin: 'https://example.test' });
  vi.stubGlobal('localStorage', {
    getItem(key) { return key === 'kissne.web.device_token' ? 'paired' : ''; },
    setItem() {},
    removeItem() {}
  });
  const urls = [];
  vi.stubGlobal('fetch', async (url) => {
    urls.push(url);
    return { ok: true, text: async () => '{"messages":[]}' };
  });
  await import('../kissne-prototype/prototype/transport.js');
  await globalThis.window.KissneHistoryScope.request(globalThis.window.KissneTransport, 50, 'older-ref', 'chosen-room', 'chosen-room');
  await globalThis.window.KissneHistoryScope.request(globalThis.window.KissneTransport, 50, '', '', 'chosen-room');
  expect(urls[0]).toContain('before=older-ref&session_id=chosen-room');
  expect(urls[1]).toBe('https://example.test/mobile/history?limit=50');
});

import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { test } from 'node:test';
const require = createRequire(import.meta.url);
const { providerModels, eventAction, outboxWait, coalesceUserRows } = require('../kissne-prototype/prototype/chat-lifecycle.js');

test('a selected provider never borrows another provider models', () => {
  const rows = [{ p: 'a', raw: 'same' }, { p: 'b', raw: 'same' }];
  assert.deepEqual(providerModels(rows, 'empty'), []);
  assert.deepEqual(providerModels(rows, 'b'), [rows[1]]);
  assert.deepEqual(providerModels(rows, ''), rows);
});

test('late activity can enrich a terminal turn without reopening it', () => {
  for (const presentation of ['reasoning', 'tool_call', 'tool_result', 'tool_progress', 'commentary']) {
    assert.equal(eventAction({ presentation }, true), 'late_activity');
    assert.equal(eventAction({ presentation }, false), 'live');
  }
  for (const type of ['notice', 'approval_resolved']) {
    assert.equal(eventAction({ type }, true), 'live');
  }
  for (const type of ['pending', 'delta', 'completed', 'cancelled']) {
    assert.equal(eventAction({ type }, true), 'ignore');
  }
});

test('sent fragments wait for the final tap and sustained typing is bounded', () => {
  const items = [{ queuedAt: 1000 }];
  assert.equal(outboxWait({ items, now: 1000, updatedAt: 1000, inputAt: 0, composerText: '' }), 1600);
  items.push({ queuedAt: 2000 });
  assert.equal(outboxWait({ items, now: 2600, updatedAt: 2000, inputAt: 0, composerText: '' }), 1000);
  assert.equal(outboxWait({ items, now: 3600, updatedAt: 2000, inputAt: 0, composerText: '' }), 0);
  assert.equal(outboxWait({ items, now: 3600, updatedAt: 2000, inputAt: 3500, composerText: '尚未发送' }), 320);
  assert.equal(outboxWait({ items, now: 9000, updatedAt: 8800, inputAt: 8900, composerText: '尚未发送' }), 0);
  assert.equal(outboxWait({ items: [], now: 1000, updatedAt: 1000, inputAt: 1000, composerText: '草稿' }), 0);
});
test('one accepted batch produces one user history row without touching other messages', () => {
  const first = { html: '第一句', messageRef: 'turn:t:user', pendingSend: false };
  const second = { html: '第二句', messageRef: 'turn:t:user' };
  const other = { html: '另一个消息' };
  const log = [other, first, second], local = [first, second];
  assert.equal(coalesceUserRows([first, second], '第一句第二句', log, local), first);
  assert.deepEqual(log, [other, first]);
  assert.deepEqual(local, [first]);
  assert.equal(first.html, '第一句第二句');
  assert.equal(first.messageRef, 'turn:t:user');
  assert.equal(coalesceUserRows([], '', log, local), null);
});

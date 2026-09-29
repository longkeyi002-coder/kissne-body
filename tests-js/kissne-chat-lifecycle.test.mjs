import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { test } from 'node:test';
const require = createRequire(import.meta.url);
const { providerModels, eventAction } = require('../kissne-prototype/prototype/chat-lifecycle.js');

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

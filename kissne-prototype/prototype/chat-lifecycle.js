/* Shared chat decisions; transport and rendering remain in screens-a.js. */
(function (root) {
  'use strict';
  function providerModels(models, provider) {
    var selected = String(provider || '');
    return selected ? models.filter(function (m) { return m.p === selected; }) : models.slice();
  }
  function eventAction(event, terminal) {
    if (!terminal || event.type === 'notice' || event.type === 'approval_resolved') return 'live';
    var presentation = String(event.presentation || '');
    if (['reasoning', 'tool_progress', 'tool_call', 'tool_result', 'commentary'].indexOf(presentation) >= 0) {
      return 'late_activity';
    }
    return 'ignore';
  }
  function outboxWait(state) {
    if (!state.items.length) return 0;
    var remaining = 1600 - (state.now - state.updatedAt);
    if (state.composerText.trim() && state.inputAt) {
      remaining = Math.max(remaining, 420 - (state.now - state.inputAt));
    }
    // Bound sustained typing without sending any text still in the composer.
    var firstAt = state.items[0].queuedAt;
    if (typeof firstAt === 'number') remaining = Math.min(remaining, 8000 - (state.now - firstAt));
    return Math.max(0, remaining);
  }
  function coalesceUserRows(rows, html, chatLog, localRows) {
    if (!rows.length) return null;
    var first = rows[0];
    first.html = html;
    rows.slice(1).forEach(function (row) {
      [chatLog, localRows].forEach(function (list) {
        var at = list.indexOf(row);
        if (at >= 0) list.splice(at, 1);
      });
    });
    return first;
  }
  var api = { providerModels: providerModels, eventAction: eventAction,
    outboxWait: outboxWait, coalesceUserRows: coalesceUserRows };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.KissneChatLifecycle = api;
})(typeof window !== 'undefined' ? window : globalThis);

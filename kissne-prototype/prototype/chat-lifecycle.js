/* Shared chat decisions; transport and rendering remain in screens-a.js. */
(function (root) {
  'use strict';
  function providerModels(models, provider) {
    var selected = String(provider || '');
    return selected ? models.filter(function (m) { return m.p === selected; }) : models.slice();
  }
  function eventAction(event, terminal) {
    if (!terminal) return 'live';
    var presentation = String(event.presentation || '');
    if (['reasoning', 'tool_progress', 'tool_call', 'tool_result', 'commentary'].indexOf(presentation) >= 0) {
      return 'late_activity';
    }
    return 'ignore';
  }
  var api = { providerModels: providerModels, eventAction: eventAction };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.KissneChatLifecycle = api;
})(typeof window !== 'undefined' ? window : globalThis);

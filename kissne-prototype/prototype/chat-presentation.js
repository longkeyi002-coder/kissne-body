(function (root) {
  'use strict';
  function channels(value) {
    var reasoning = [];
    var answer = String(value || '').split(/(```[\s\S]*?```|`[^`\n]*`)/g).map(function (part) {
      if (part.charAt(0) === '`') return part;
      return part.replace(/<(think|thinking|analysis)\b[^>]*>([\s\S]*?)(?:<\/\1>|$)/gi, function (_, tag, content) {
        reasoning.push(content.trim());
        return '';
      });
    }).join('');
    return { answer: answer.trim(), reasoning: reasoning.join('\n\n') };
  }
  function delivery(emit, schedule, cancel, initialCount) {
    var count = initialCount || 0, pending = [], timer = null, stopped = false;
    function next() {
      timer = null;
      if (stopped || !pending.length) return;
      emit(pending.shift(), count++);
      if (pending.length) timer = schedule(next, 650);
    }
    return {
      update: function (parts) {
        if (stopped) return;
        pending = parts.slice(count);
        if (timer == null && pending.length) next();
      },
      stop: function (flush) {
        if (timer != null) cancel(timer);
        timer = null;
        if (flush) while (pending.length) emit(pending.shift(), count++);
        pending = [];
        stopped = true;
      }
    };
  }
  var api = { channels: channels, delivery: delivery };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.KissneChatPresentation = api;
})(typeof window !== 'undefined' ? window : globalThis);

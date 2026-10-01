/* Optional display-only template removal; no prompt changes or additional model calls. */
(function () {
  'use strict';
  var key = 'kissne.chat.expression_filter.v1';
  function enabled() { try { return localStorage.getItem(key) !== 'off'; } catch (ignore) { return true; } }
  function html(value) {
    var original = String(value || ''); if (!enabled()) return original;
    var template = document.createElement('template'); template.innerHTML = original;
    if (template.content.querySelector('pre,code,blockquote,a,img,svg') || /https?:\/\//i.test(template.content.textContent)) return original;
    var walker = document.createTreeWalker(template.content, NodeFilter.SHOW_TEXT), nodes = [], node;
    while ((node = walker.nextNode())) nodes.push(node);
    if (!nodes.length) return original;
    nodes[0].nodeValue = nodes[0].nodeValue.replace(/^(?:当然可以[！!。]|没问题[！!。]|好的，我来帮你[！!。])[ \t]*\n+/, '');
    var last = nodes[nodes.length - 1];
    last.nodeValue = last.nodeValue.replace(/\n+(?:希望这些(?:信息|建议|内容)对你有所帮助[。！!]?|如果你还有其他问题，随时(?:告诉我|问我)[。！!]?)[ \t]*$/, '');
    return template.content.textContent.trim() ? template.innerHTML : original;
  }
  window.KissneExpressionFilter = { html: html, enabled: enabled, setEnabled: function (value) { try { localStorage.setItem(key, value ? 'on' : 'off'); } catch (ignore) {} } };
})();

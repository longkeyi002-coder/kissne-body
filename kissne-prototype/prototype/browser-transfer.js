(function () {
  'use strict';
  var transfer = null;
  window.KissneBrowserTransfer = { pending: function () { return transfer; }, clear: function () { transfer = null; } };
  window.addEventListener('kissne-browser-return', function (event) {
    var data = event.detail; if (!data || typeof data.text !== 'string' || !data.text.trim()) return;
    transfer = { text: data.text.slice(0, 100000), source_url: String(data.source_url || ''), source_title: String(data.source_title || ''), session_id: String(data.session_id || '') };
    window.dispatchEvent(new CustomEvent('kissne-browser-transfer-ready'));
  });
})();

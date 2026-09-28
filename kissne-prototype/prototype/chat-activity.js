/* Presentation only: lifecycle identity comes from the gateway, never from text shape. */
(function (root) {
  'use strict';
  var pages = Object.create(null);
  function pageKey(ref, field) { return JSON.stringify([ref.turn_id, ref.tool_call_id, field]); }
  function page(ref, field) { return pages[pageKey(ref, field)]; }
  function addPage(ref, field, preview, response) {
    var key = pageKey(ref, field), old = pages[key];
    pages[key] = { text: (old ? old.text : preview) + response.text, next: response.next_offset };
  }
  function render(state, turnId, esc) {
    var rows = [];
    function fold(key, title, content, cls) {
      return '<div class="activity-item ' + (cls || '') + '" data-activity-key="' + esc(key) + '">'
        + '<button type="button" class="activity-row" data-activity-toggle aria-expanded="false">'
        + '<span class="activity-label">' + esc(title) + '</span><span aria-hidden="true">⌄</span></button>'
        + '<div class="activity-detail" hidden>' + content + '</div></div>';
    }
    if (state.reasoningText) rows.push('<section class="activity-section activity-section--reasoning" aria-label="思考">'
      + fold('reasoning', state.done ? '思考过程' : '正在思考', '<pre>' + esc(state.reasoningText) + '</pre>') + '</section>');
    if ((state.commentary || []).length) rows.push('<section class="activity-section activity-section--commentary" aria-label="过程说明">'
      + '<span class="activity-section__title">过程说明</span><div class="activity-commentary">'
      + state.commentary.map(function (text) { return '<p>' + esc(text) + '</p>'; }).join('') + '</div></section>');
    var tools = (state.toolOrder || []).map(function (key) {
      var tool = state.toolCalls[key];
      if (!tool) return '';
      var status = tool.status;
      var statusText = { failed: '失败', completed: '完成', cancelled: '已取消' }[status]
        || (state.done ? '未收到结果' : '进行中');
      var body = '<div class="activity-toolname">工具：' + esc(tool.name || '未提供名称') + '</div>';
      ['arguments', 'result'].forEach(function (field) {
        var preview = field === 'arguments' ? tool.detail : tool.result;
        if (!preview && !tool[field + 'Truncated']) return;
        var ref = tool.detailRef, loaded = ref && page(ref, field);
        var text = loaded ? loaded.text : preview;
        var next = loaded ? loaded.next : (tool[field + 'Truncated'] ? 2000 : null);
        body += '<div class="activity-section__title">' + (field === 'arguments' ? '参数 / 代码' : '返回结果') + '</div>'
          + '<pre data-tool-field="' + field + '">' + esc(text || '') + '</pre>';
        if (next !== null && ref) body += '<button type="button" class="activity-more" data-tool-more="' + field
          + '" data-turn="' + esc(ref.turn_id) + '" data-call="' + esc(ref.tool_call_id)
          + '" data-offset="' + next + '">加载更多（完整内容已保留）</button>';
      });
      return fold('tool:' + key, tool.label || ('调用 ' + (tool.name || '工具')),
        body, 'activity-item--' + status).replace('</span><span aria-hidden', '</span><span class="activity-count">'
          + esc(statusText) + '</span><span aria-hidden');
    }).join('');
    if (tools) rows.push('<section class="activity-section activity-section--tools" aria-label="工具调用"><span class="activity-section__title">工具调用</span>' + tools + '</section>');
    return rows.join('');
  }
  var api = { render: render, addPage: addPage, page: page };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.KissneChatActivity = api;
})(typeof window !== 'undefined' ? window : null);

// 消息分道探针：在 Node 里装载真·screens-a.js，按「结构化字段 → 道」逐条断言。
// 断言对象是运行期真正用的两个纯函数（K.laneForLiveEvent / K.laneForHistoryRow），
// 不是抄一份逻辑；另外用源码断言确认「文本长相识类」已不再改判正文归属。
// 跑法：node tools/lane_routing_probe.js
global.window = {};
global.document = {
  getElementById: function () { return null; },
  createElement: function () { return { set innerHTML(v) {}, get firstElementChild() { return null; }, appendChild() {}, insertBefore() {} }; },
  addEventListener: function () {},
  body: null,
  documentElement: {}
};
var fs = require('fs');
var path = require('path');
var base = path.join(__dirname, '..');
function load(p) { eval(fs.readFileSync(path.join(base, p), 'utf8')); }
load('core.js');
load('assets/_manifest.js');
load('assets/icons/sprite-data.js');
load('assets.js');
load('screens-a.js');
var K = global.window.KSN;

var failures = 0;
function assert(name, cond) {
  console.log((cond ? 'PASS' : 'FAIL') + ' · ' + name);
  if (!cond) { failures++; process.exitCode = 1; }
}
function lane(fn, a, b, extra) {
  return K[fn](a, b, extra);
}
function checkTable(fn, rows) {
  rows.forEach(function (row) {
    var got = fn === 'laneForLiveEvent' ? K.laneForLiveEvent(row[0], row[1]) : K.laneForHistoryRow(row[0], row[1]);
    assert(fn + '(' + JSON.stringify(row[0]) + ', ' + JSON.stringify(row[1]) + ') → ' + row[2] + '（实得 ' + got + '）', got === row[2]);
  });
}

console.log('== live 事件分道表（type, presentation）→ 道 ==');
checkTable('laneForLiveEvent', [
  ['delta', 'assistant_text', 'assistant'],
  ['completed', 'assistant_text', 'assistant'],
  ['delta', '', 'assistant'],
  ['completed', '', 'assistant'],
  ['delta', 'tool_call', 'tool'],
  ['delta', 'tool_progress', 'tool'],
  ['completed', 'tool_result', 'tool'],
  ['delta', 'reasoning', 'reasoning'],
  ['delta', 'commentary', 'commentary'],
  ['notice', '', 'notice'],
  ['notice', 'notice', 'notice'],
  ['completed', 'session_reset', 'notice'],
  ['delta', 'hidden', 'ignore'],
  ['delta', 'internal_notification', 'ignore'],
  ['pending', '', ''],
  ['cancelled', '', ''],
  ['approval_required', '', ''],
  ['approval_resolved', '', '']
]);

console.log('\n== 历史行分道表（role, presentation）→ 道 ==');
checkTable('laneForHistoryRow', [
  ['assistant', 'assistant_text', 'assistant'],
  ['assistant', '', 'assistant'],
  ['assistant', 'commentary', 'commentary'],
  ['assistant', 'reasoning', 'reasoning'],
  ['assistant', 'tool_call', 'tool'],
  ['assistant', 'notice', 'notice'],
  ['tool', '', 'tool'],
  ['tool', 'tool_result', 'tool'],
  ['system', '', 'notice'],
  ['system', 'notice', 'notice'],
  ['system', 'session_reset', 'notice'],
  ['system', 'tool_result', 'tool'],
  ['system', 'hidden', 'ignore'],
  ['user', '', 'user'],
  ['user', 'assistant_text', 'user'],
  ['mystery', '', '']
]);

console.log('\n== 分道判定看不见正文（多传正文也不改变结果） ==');
var TOOLISH = '```terminal\n$ git status\nReading gateway/run_busy.py L620\n```';
assert('live delta+assistant_text 带工具长相正文仍 → assistant',
  K.laneForLiveEvent('delta', 'assistant_text', TOOLISH) === 'assistant');
assert('live delta+空 presentation 带工具长相正文仍 → assistant',
  K.laneForLiveEvent('delta', '', TOOLISH) === 'assistant');
assert('history assistant+空 presentation 带工具长相正文仍 → assistant',
  K.laneForHistoryRow('assistant', '', TOOLISH) === 'assistant');
assert('history system+空 presentation 带工具长相正文仍 → notice（旧流水只在这里被抑制/折叠）',
  K.laneForHistoryRow('system', '', TOOLISH) === 'notice');

console.log('\n== 源码事实：文本长相识类是否还在改判助手正文 ==');
var src = fs.readFileSync(path.join(base, 'screens-a.js'), 'utf8');
[
  'looksLikeToolTranscript(deltaText)',
  'looksLikeToolTranscript(finalText)',
  'looksLikeToolTranscript(commentaryText)',
  'looksLikeToolTranscript(rawText) && role !== ',
  'history-commentary-tool:',
  'history-assistant-tool:'
].forEach(function (bad) {
  assert('已移除改判点：' + bad, src.indexOf(bad) < 0);
});
var toolHits = src.split('\n').map(function (line, i) { return [i + 1, line]; })
  .filter(function (r) { return r[1].indexOf('looksLikeToolTranscript(') >= 0 && r[1].indexOf('function looksLikeToolTranscript') < 0; });
console.log('仍存在的 looksLikeToolTranscript 调用点：');
toolHits.forEach(function (r) { console.log('  L' + r[0] + ': ' + r[1].trim()); });
var toolArgs = toolHits.map(function (r) { return (r[1].match(/looksLikeToolTranscript\(([^)]*)\)/) || [])[1]; }).sort();
assert('looksLikeToolTranscript 调用点只剩「抑制旧式原始工具流水」的 2 处（noticeText / rawText）',
  toolHits.length === 2 && toolArgs.join(',') === 'noticeText,rawText');
assert('历史 notice 道里那处紧随 LANE_NOTICE 判定',
  src.indexOf('if (historyLane === LANE_NOTICE) {') > 0
  && src.indexOf('if (historyLane === LANE_NOTICE) {') < src.indexOf('if (!historyPresentation && looksLikeToolTranscript(rawText)) {'));
assert('两处旧流水抑制都以「没有结构化 presentation」为前提',
  src.indexOf('if (!historyPresentation && looksLikeToolTranscript(rawText)) {') > 0
  && src.indexOf('if (!presentation && looksLikeToolTranscript(noticeText)) return;') > 0);
assert('live 三条正文道都由 lane 常量分派', src.indexOf('if (lane === LANE_TOOL) {') > 0
  && src.indexOf('if (lane === LANE_COMMENTARY) {') > 0 && src.indexOf('if (lane === LANE_NOTICE) {') > 0);
assert('sys 行只由 appendSystemNotice / 历史 notice 道产生',
  src.indexOf("pushLog({ who: 'sys'") >= 0
  && src.split("who: 'sys'").length - 1 === 2);
assert('本地缓存恢复 sys 行要求 clientNotice 标记',
  src.indexOf("m.who === 'sys' && m.localOnly && m.clientNotice === true") > 0);

console.log('\n' + (failures ? 'FAILED ' + failures + ' 条' : 'ALL PASS'));

console.log('== 活动流持久化（源码断言：工具/思考块不许在重画后消失）==');
var srcText = fs.readFileSync(path.join(base, 'screens-a.js'), 'utf8');
var persistBody = (/function persistChatLog\(\)[\s\S]*?\n  \}/.exec(srcText) || [''])[0];
assert('落盘白名单必须带上 activity（否则本地缓存重建时活动块整块消失）', /activity:\s*m\.activity/.test(persistBody));
var localRowsBody = (/var localRows = messageRef[\s\S]*?delete localByRef\[messageRef\]/.exec(srcText) || [''])[0];
assert('跟服务器对账时，缺活动流的本地行要能补回 activity', /m\.activity = activityMarkupForTurn/.test(localRowsBody));
assert('本地行若没有活动流时，还要能用最终正文兜底匹配', /m\.activity = FINAL_ACTIVITY_BY_TEXT\[rawText\]/.test(localRowsBody));
console.log('探针结束：' + (failures ? failures + ' 条失败' : '全部通过'));

console.log('== 工具行不许在「完成」时消失（源码断言）==');
assert('收尾前先接管 pending 账本', /adoptPendingActivity\(turnId\);\s*\n\s*finishActivities\(el, turnId\);/.test(srcText));
assert('目标账本已有内容时不接管', /if \(activityHasRows\(TURN_ACTIVITY\[id\]\)\) return false;/.test(srcText));
assert('接管后清掉 pending', /delete TURN_ACTIVITY\['pending'\];/.test(srcText));

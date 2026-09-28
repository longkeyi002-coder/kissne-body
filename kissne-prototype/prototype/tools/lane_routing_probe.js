// 消息分道探针：在 Node 里装载真·screens-a.js，按「结构化字段 → 道」逐条断言。
// 断言对象是运行期真正用的两个纯函数（K.laneForLiveEvent / K.laneForHistoryRow），
// 执行真实分道函数，不对源码形状做断言。
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
load('chat-activity.js');
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

console.log(failures ? 'FAILED' : 'ALL PASS');

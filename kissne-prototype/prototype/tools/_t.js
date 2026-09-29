// 运行时冒烟测试：在 Node 里用最小 window/document 桩跑通素材 API
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
load('screens-b.js');
var K = global.window.KSN;
function assert(name, cond) { console.log((cond ? 'PASS' : 'FAIL') + ' · ' + name); if (!cond) process.exitCode = 1; }

assert('KSN_ASSETS.chars 有 FOX_HOME_CHARACTER', !!(global.window.KSN_ASSETS.chars.FOX_HOME_CHARACTER));
assert('KSN_SPRITE 含 ic-home', global.window.KSN_SPRITE.indexOf('id="ic-home"') >= 0);
assert('KSN_SPRITE 含 ic-hoof', global.window.KSN_SPRITE.indexOf('id="ic-hoof"') >= 0);

var ic = K.icon('home');
assert('K.icon 返回 <use href="#ic-home">', ic.indexOf('<use href="#ic-home"') >= 0 && ic.indexOf('currentColor') >= 0);

var icBad = K.icon('nope');
assert('K.icon 未知图标降级为 info', icBad.indexOf('<use href="#ic-info"') >= 0);

/* 注意：清单里的路径相对 assets/，页面引用时由 K.rel() 补前缀，
   所以断言里必须带 "assets/"（早期没有前缀，此处已随 assets.js 的改动更新）。 */
var a = K.asset('FOX_HOME_CHARACTER');
assert('K.asset 指向 assets/ 文件', a.indexOf('src="assets/characters/yeqingxu/avatar/home-card.svg"') >= 0 && a.indexOf('onerror="KSN.assetBroken') >= 0);

var bg = K.bg('room-living');
assert('K.bg 指向 assets/backgrounds/', bg.indexOf('src="assets/backgrounds/room-living.svg"') >= 0 && bg.indexOf('bg-asset') >= 0);

var an = K.anim('chat/typing');
assert('K.anim 指向 assets/animations/ 且带 data-anim', an.indexOf('src="assets/animations/chat/typing.svg"') >= 0 && an.indexOf('data-anim="chat/typing"') >= 0);

var ch = K.char('yeqingxu', 'actions/pixel');
assert('K.char 拼出 assets/characters 路径', ch.indexOf('src="assets/characters/yeqingxu/actions/pixel.svg"') >= 0);

// ---- 渲染若干页面，确认不抛错且素材引用正确注入 ----
function renderScreen(id, state, params) {
  var s = K.screens.filter(function (x) { return x.id === id; })[0];
  if (!s) throw new Error('找不到屏幕 ' + id);
  return s.render({ state: state || (s.states[0] && s.states[0].key), nav: function () {}, params: params || new URLSearchParams('') });
}
var home, chat, uni, memory, stickers, uniScene;
try {
  home = renderScreen('home', 'online');
  chat = renderScreen('chat', 'empty');
  uni = renderScreen('universe', 'auto');
  memory = renderScreen('memory', 'list');
  stickers = renderScreen('stickers', 'default');
  uniScene = renderScreen('universe', 'scene', new URLSearchParams('room=living'));
} catch (e) {
  console.log('FAIL · 渲染抛错: ' + e.message);
  process.exitCode = 1;
}
/* 首页两张星卡已有真图（real/*.jpg），所以按**占位代码**断言引用，不写死路径。 */
assert('home 含星卡角色素材引用', home && home.indexOf('FOX_HOME_CHARACTER') >= 0 && home.indexOf('SHEEP_CHARACTER_RESERVED') >= 0);
assert('chat 含状态表情引用', chat && chat.indexOf('characters/yeqingxu/expressions/state.svg') >= 0);
assert('universe 俯视图含背景图层', uni && uni.indexOf('class="bg-asset"') >= 0 && uni.indexOf('backgrounds/scene-room.svg') >= 0);
assert('universe 场景视图可渲染', uniScene && uniScene.indexOf('screen--scene') >= 0);
assert('universe 小人带 data-asset', uni && uni.indexOf('data-asset="characters/yeqingxu/actions/pixel.svg"') >= 0);
assert('memory 页可渲染', memory && memory.indexOf('appbar__title">记忆库') >= 0);
assert('stickers 页可渲染', stickers && stickers.indexOf('appbar__title">表情包') >= 0);

/* Chat process UI contract: activity is independent from spoken assistant text,
   uses a compact label, and remains individually expandable. */
var screensSource = fs.readFileSync(path.join(base, 'screens-a.js'), 'utf8');
assert('过程记录不复用正文头像行', screensSource.indexOf('var process = activity ?') >= 0
  && screensSource.indexOf('data-live-message') >= 0);
assert('过程框不用大号“思考过程”标题', screensSource.indexOf("<b>思考过程</b>") < 0
  && screensSource.indexOf("closed ? '过程记录' : '处理中'") >= 0);
assert('工具与思考均可展开', screensSource.indexOf("row.closest('.process-step')") >= 0);

console.log('\n示例 K.icon(home):', ic);
console.log('示例 K.asset(FOX_HOME_CHARACTER):', a);

/* =====================================================================
   Kissne 手机端低保真原型 · assets.js
   ---------------------------------------------------------------------
   统一素材引用层：所有角色 / 背景 / 动画 / 图标 / 特效都从这里指向
   prototype/assets/ 目录，页面代码不再散落任何素材路径或内联 SVG。

   数据来源（自动生成，单点维护）：
     assets/_manifest.js   -> window.KSN_ASSETS
     assets/icons/sprite-data.js -> window.KSN_SPRITE（图标精灵，currentColor 可继承）
   改素材后只需重新运行 tools/gen-assets.py，本文件无需改。

   静态兜底：每个 <img> 都带 onerror -> KSN.assetBroken()，
   素材缺失/损坏时退化成内联灰盒，绝不出现裂图或破坏布局。
   动画占位自带 prefers-reduced-motion 静态降级（见各 SVG 内部 <style>）。
   ===================================================================== */
(function () {
  'use strict';
  var K = window.KSN;
  if (!K) { return; }                 /* core.js 未加载则跳过，避免报错 */
  var A = window.KSN_ASSETS || {};
  var esc = K.esc;

  /* ---------- 图标精灵注入（先于任何 K.icon 调用） ----------
     KSN_SPRITE 是一段 <svg style="display:none"><symbol id="ic-*" …/></svg>，
     注入文档后即可被 <use href="#ic-*"> 引用，且继承 host 的 currentColor。 */
  function injectSprite() {
    if (!window.KSN_SPRITE) return;
    if (document.getElementById('ksn-sprite')) return;
    /* 优先挂到 <body>；head 阶段 <body> 尚不存在时挂到 <html>，
       保证 app.js 在解析末尾渲染前精灵已就位（否则 <use> 解析不到图标）。 */
    var host = document.body || document.documentElement;
    if (!host) return;
    var tmp = document.createElement('div');
    tmp.innerHTML = window.KSN_SPRITE;
    var svg = tmp.firstElementChild;
    if (svg) { svg.id = 'ksn-sprite'; host.insertBefore(svg, host.firstChild); }
  }
  /* 立即注入（head 阶段即可，documentElement 一定存在），并兜底到 DOMContentLoaded */
  injectSprite();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', injectSprite);
  }

  /* ---------- 静态兜底：素材损坏时退化成灰盒 ---------- */
  K.assetBroken = function (img, code) {
    if (!img || !img.parentNode) return;
    var box = document.createElement('div');
    box.className = 'ph ph--broken';
    box.setAttribute('data-placeholder', code || (img.getAttribute('data-asset') || 'ASSET'));
    box.title = '素材缺失：' + (code || img.getAttribute('alt') || '');
    box.textContent = code || img.getAttribute('alt') || '缺失';
    img.parentNode.replaceChild(box, img);
  };

  /* 路径前缀统一走 core.js 的 assetRel —— 清单里的路径相对 assets/，
     页面在 prototype/ 根下，不补前缀会 404。 */
  function rel(path) { return K.rel ? K.rel(path) : path; }

  /* ---------- 通用素材引用 ---------- */
  /* K.asset(code, opts) —— 直接按清单里的逻辑码取素材（角色 / 插画占位） */
  K.asset = function (id, opts) {
    opts = opts || {};
    var path = (A.chars && A.chars[id]) || (A.icons && A.icons[id]) || id;
    if (!path) {
      return '<div class="ph ph--broken" data-placeholder="' + esc(id) + '">' + esc(id) + '</div>';
    }
    return '<img class="asset' + (opts.cls ? ' ' + opts.cls : '') + '"'
      + ' src="' + esc(rel(path)) + '"'
      + ' alt="' + esc(opts.alt || id) + '"'
      + ' loading="lazy"'
      + ' data-asset="' + esc(id) + '"'
      + ' onerror="KSN.assetBroken(this,\'' + esc(id).replace(/'/g, "\\'") + '\')">';
  };

  /* ---------- 角色 ---------- */
  /* K.char(role, sub, opts) —— 拼出 characters/<role>/<sub>.svg
     sub 形如 'avatar/splash' | 'expressions/state' | 'actions/pixel' … */
  K.char = function (role, sub, opts) {
    opts = opts || {};
    var path = 'characters/' + role + '/' + sub + '.svg';
    return '<img class="asset asset--char' + (opts.cls ? ' ' + opts.cls : '') + '"'
      + ' src="' + esc(rel(path)) + '"'
      + ' alt="' + esc(opts.alt || (role + ' ' + sub)) + '"'
      + ' loading="lazy"'
      + ' data-asset="' + esc(path) + '"'
      + ' onerror="KSN.assetBroken(this,\'' + esc(opts.alt || path).replace(/'/g, "\\'") + '\')">';
  };

  /* ---------- 背景 ---------- */
  /* K.bg(name, opts) —— 取 backgrounds/<name>.svg，作为可叠在色块上的半透明图层 */
  K.bg = function (name, opts) {
    opts = opts || {};
    var path = (A.backgrounds && A.backgrounds[name]) || ('backgrounds/' + name + '.svg');
    return '<img class="bg-asset' + (opts.cls ? ' ' + opts.cls : '') + '"'
      + ' src="' + esc(rel(path)) + '"'
      + ' alt="' + esc(opts.alt || ('背景 · ' + name)) + '"'
      + ' aria-hidden="true"'
      + ' data-asset="' + esc(path) + '"'
      + ' onerror="KSN.assetBroken(this,\'' + esc(path).replace(/'/g, "\\'") + '\')">';
  };

  /* ---------- 特效 ---------- */
  K.fx = function (name, opts) {
    opts = opts || {};
    var path = (A.effects && A.effects[name]) || ('effects/' + name + '.svg');
    return '<img class="fx-asset' + (opts.cls ? ' ' + opts.cls : '') + '"'
      + ' src="' + esc(rel(path)) + '"'
      + ' alt="' + esc(opts.alt || ('特效 · ' + name)) + '"'
      + ' aria-hidden="true"'
      + ' data-asset="' + esc(path) + '"'
      + ' onerror="KSN.assetBroken(this,\'' + esc(path).replace(/'/g, "\\'") + '\')">';
  };

  /* ---------- 动画（必须带静态 fallback）----------
     K.anim(name, opts) —— 取 animations/<name>.svg（轻量 CSS/SVG 动画占位）。
     静态兜底 = SVG 内部 @media (prefers-reduced-motion: reduce) 关闭动画即首帧；
     本层再补一层：reduced-motion 下 .anim 显示 .anim__poster（同文件静态帧）。 */
  K.anim = function (name, opts) {
    opts = opts || {};
    var path = (A.animations && A.animations[name]) || ('animations/' + name + '.svg');
    var group = (name.split('/')[0] || 'anim');
    return '<span class="anim anim--' + esc(group) + (opts.cls ? ' ' + opts.cls : '') + '"'
      + ' data-anim="' + esc(name) + '" title="' + esc(opts.alt || ('动画 · ' + name)) + '">'
      + '<img class="anim__img" src="' + esc(rel(path)) + '"'
      + ' alt="' + esc(opts.alt || ('动画占位 · ' + name)) + '" loading="lazy"'
      + ' onerror="KSN.assetBroken(this,\'' + esc(name).replace(/'/g, "\\'") + '\')">'
      + '</span>';
  };

  /* ---------- 图标（从 assets/icons 引用，保留 currentColor）---------- */
  /* 覆盖 core.js 里的内联版本：改为引用注入的精灵符号，单点维护在 assets/icons。 */
  K.icon = function (name, size, cls) {
    var ok = window.KSN_SPRITE && window.KSN_SPRITE.indexOf('id="ic-' + name + '"') >= 0;
    if (!ok) {                     /* 精灵缺该图标：退化成信息图标，绝不空白 */
      name = 'info';
    }
    var s = size || 20;
    return '<svg class="ic ' + (cls || '') + '" width="' + s + '" height="' + s + '"'
      + ' viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"'
      + ' stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
      + '<use href="#ic-' + esc(name) + '"></use></svg>';
  };

  /* ---------- 表情包 ----------
     素材由 tools/gen-assets.py 从 _inbox/stickers/ 生成，**白底已抠成透明**
     （角色身体本身就是白的，所以是"只抠与四边相连的白底"，见生成器的 _cut_white_bg）。
     清单里没有该 key 时退回灰块标签，绝不出现裂图。 */
  K.sticker = function (key, opts) {
    opts = opts || {};
    var path = A.stickers && A.stickers[key];
    if (!path) {
      return '<span class="stkmiss" data-placeholder="STICKER_PACK">'
        + esc(opts.alt || key) + '</span>';
    }
    return '<img class="stkimg' + (opts.cls ? ' ' + opts.cls : '') + '"'
      + ' src="' + esc(rel(path)) + '"'
      + ' alt="' + esc(opts.alt || key) + '"'
      + ' loading="lazy" draggable="false"'
      + ' data-sticker="' + esc(key) + '"'
      + ' onerror="KSN.assetBroken(this,\'STICKER_PACK\')">';
  };

  /* K.stickerList() —— 表情包清单，按 stickerGroups 的顺序排好（双人 → 叶青栩 → 小羊 → 配文）。
     页面拿它铺网格 / 分组，不必自己读清单结构。 */
  K.stickerList = function () {
    var map = A.stickers || {};
    var meta = A.stickerMeta || {};
    var order = A.stickerGroups || [];
    function rank(g) { var i = order.indexOf(g); return i < 0 ? order.length : i; }
    return Object.keys(map).map(function (k) {
      var m = meta[k] || {};
      return { k: k, label: m.label || k, group: m.group || '其他' };
    }).sort(function (a, b) {
      return rank(a.group) - rank(b.group) || (a.k < b.k ? -1 : a.k > b.k ? 1 : 0);
    });
  };

  /* 把清单挂到 KSN，供页面/素材总表页读取 */
  K.ASSETS = A;
})();

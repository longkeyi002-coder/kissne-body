/* =====================================================================
   Kissne 手机端低保真原型 · core.js
   ---------------------------------------------------------------------
   职责：素材占位登记表 / 通用组件拼装函数 / 线性图标集
   原则：灰阶、无渐变、无最终插画、不重绘角色；素材位置一律显式标注
   ===================================================================== */
window.KSN = (function () {
  'use strict';

  /* ---------- 1. 素材占位登记表（对应交接文档 · 第八节） ---------- */
  var PLACEHOLDERS = {
    FOX_SPLASH_CHARACTER:            { label: '开屏页·蓝狐狸角色素材', where: '入口页 · logo 动画后的左侧', size: '118×118' },
    SHEEP_SPLASH_CHARACTER:          { label: '开屏页·绿羊角色素材',   where: '入口页 · logo 动画后的右侧', size: '118×118' },
    FOX_CHAT_AVATAR:                 { label: '叶青栩头像素材',       where: '人人星 · 消息列表里 AI 一侧的头像', size: '34×34' },
    USER_AVATAR:                     { label: '用户头像素材',         where: '人人星 · 消息列表里我这一侧的头像', size: '34×34' },
    FOX_HOME_CHARACTER:              { label: '小机星卡片图素材',      where: '首页 · 小机星入口卡（右 · 叶青栩）', size: '卡片图' },
    FOX_NOTIFICATION_AVATAR:         { label: '叶青栩通知头像素材',    where: '通知与弹窗 · 新消息',       size: '40×40' },
    FOX_STATE_EMOTION:               { label: '叶青栩状态表情素材',    where: '聊天页 · 状态 / 空状态',    size: '32×32' },
    EARTH_STATE:                     { label: 'Earth 侧星球素材',      where: '（小机星页改为像素场景，暂未放置）', size: '120×120' },
    AI_WORLD_STATE:                  { label: 'AI World 侧星球素材',   where: '（小机星页改为像素场景，暂未放置）', size: '120×120' },
    FOX_PIXEL_SPRITE:                { label: '叶青栩·像素小人素材',    where: '小机星页 · 像素场景里的 AI 小人（当前用纯色块拼）', size: '32×40' },
    MEMORY_EMPTY_ILLUSTRATION:       { label: '记忆空状态插画',        where: '记忆库页 · 空状态',        size: '140×140' },
    CONNECTION_SUCCESS_ILLUSTRATION: { label: '连接成功插画',          where: '连接成功页 · 顶部',        size: '140×140' },
    OFFLINE_ILLUSTRATION:            { label: '离线状态插画',          where: '首页 / 聊天页 · 离线提示',  size: '120×120' },
    SHEEP_CHARACTER_RESERVED:        { label: '小羊羔·人人星卡片图素材', where: '首页 · 人人星入口卡（左 · 小羊）', size: '卡片图' },
    STICKER_PACK:                    { label: '表情包素材（用户上传）',  where: '表情包页 · 贴图网格 / 聊天消息里发出的表情', size: '≤512×512' }
  };

  /* ---------- 2. 通用工具 ---------- */
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function px(v) { return typeof v === 'number' ? v + 'px' : v; }

  /* 素材根目录前缀：assets/_manifest.js 里的路径一律**相对 assets/**，
     而页面本身在 prototype/ 根下，直接引用会 404（曾导致全部角色 / 背景 /
     动画素材加载失败、退化成兜底灰块）。这里统一补前缀；
     已是协议地址 / 根路径 / 相对路径 / 已带 assets/ 的原样返回。 */
  function assetRel(p) {
    p = String(p == null ? '' : p);
    return /^(?:[a-z][a-z0-9+.\-]*:|\/|\.{1,2}\/|assets\/)/i.test(p) ? p : 'assets/' + p;
  }

  /* 状态换图：同一个逻辑码可以按状态给不同的图。
     清单里 chars[code] 是兜底图，charStates[code][state] 是该状态的专用图；
     没给某个状态就回落到兜底图 —— 所以"只给一张"和"给十张"都不报错。

     例：叶青栩的聊天头像，
       chars.FOX_CHAT_AVATAR            = 平静（也算"在说话"）
       charStates.FOX_CHAT_AVATAR.think = 托腮思考
       charStates.FOX_CHAT_AVATAR.happy = 开心大笑
     加新表情 = 往 assets/_inbox/ 丢 fox-chat-avatar-<state>.png 再跑生成器。 */
  function assetPath(code, state) {
    var A = window.KSN_ASSETS;
    if (!A || !A.chars) return null;
    var st = A.charStates && A.charStates[code];
    if (state && st && st[state]) return st[state];
    return A.chars[code] || null;
  }

  /* 把一个 <img> 就地换成该状态的图（缺图自动回落）。换的时候做一次极短淡入，
     避免 34px 的小头像"啪"地跳一下。已在目标状态则什么都不做。 */
  function swapAsset(img, code, state) {
    if (!img) return;
    var path = assetPath(code, state);
    if (!path) return;
    var src = assetRel(path);
    img.setAttribute('data-state', state || '');
    if (img.getAttribute('src') === src) return;
    img.classList.add('is-swapping');
    img.setAttribute('src', src);
    var done = function () {
      requestAnimationFrame(function () { img.classList.remove('is-swapping'); });
    };
    if (img.complete) done();
    else {
      img.addEventListener('load', done, { once: true });
      setTimeout(done, 900);   /* 兜底：图挂了也要把淡出状态收回来 */
    }
  }

  /* ---------- 3. 线性图标（描边 currentColor，非最终图标定稿） ---------- */
  var ICONS = {
    home:    '<path d="M4 10.4 12 4l8 6.4V20a1 1 0 0 1-1 1h-4.5v-6h-5v6H5a1 1 0 0 1-1-1z"/>',
    chat:    '<path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v7A2.5 2.5 0 0 1 17.5 16H10l-4.4 3.5a.3.3 0 0 1-.6-.2z"/>',
    planet:  '<circle cx="12" cy="12" r="5.5"/><ellipse cx="12" cy="12" rx="10.2" ry="3.4" transform="rotate(-18 12 12)"/>',
    memory:  '<ellipse cx="12" cy="6.2" rx="6.8" ry="2.8"/><path d="M5.2 6.2v11.6c0 1.6 3 2.8 6.8 2.8s6.8-1.2 6.8-2.8V6.2"/><path d="M5.2 12c0 1.6 3 2.8 6.8 2.8s6.8-1.2 6.8-2.8"/>',
    back:    '<path d="M14.5 5 8 12l6.5 7"/>',
    chevron: '<path d="M9.5 5 16 12l-6.5 7"/>',
    gear:    '<path d="M4 7.5h9.2M17.4 7.5H20M4 16.5h5.2M13.4 16.5H20"/><circle cx="15.3" cy="7.5" r="2.3"/><circle cx="11.3" cy="16.5" r="2.3"/>',
    plus:    '<path d="M12 5v14M5 12h14"/>',
    search:  '<circle cx="11" cy="11" r="6.3"/><path d="M15.7 15.7 20.5 20.5"/>',
    sync:    '<path d="M20 12a8 8 0 0 1-13.6 5.7M4 12a8 8 0 0 1 13.6-5.7"/><path d="M17.6 3v3.6h-3.6M6.4 21v-3.6h3.6"/>',
    check:   '<path d="M5 12.6 10 17.5 19.2 7"/>',
    alert:   '<path d="M12 4.6 20.8 19.4H3.2z"/><path d="M12 10v4.2M12 17.1h.01"/>',
    close:   '<path d="M6 6l12 12M18 6 6 18"/>',
    trash:   '<path d="M4 7h16M9.2 7V4.8h5.6V7M6.2 7l.9 13h9.8l.9-13"/>',
    edit:    '<path d="M4 20h4L20 8l-4-4L4 16z"/>',
    wifioff: '<path d="M3.2 3.2 20.8 20.8"/><path d="M5.2 12.4a10 10 0 0 1 4.6-2.3M18.8 12.4a10 10 0 0 0-3.2-2.1"/><path d="M8.6 15.9a5 5 0 0 1 6.8 0"/><path d="M12 19.6h.01"/>',
    refresh: '<path d="M20 12a8 8 0 1 1-2.4-5.7"/><path d="M20 3.2v4.4h-4.4"/>',
    clock:   '<circle cx="12" cy="12" r="8"/><path d="M12 7.4V12l3.2 2"/>',
    user:    '<circle cx="12" cy="8.4" r="3.5"/><path d="M5.2 20a6.8 6.8 0 0 1 13.6 0"/>',
    server:  '<rect x="4" y="4.2" width="16" height="6" rx="2"/><rect x="4" y="13.8" width="16" height="6" rx="2"/><path d="M7.4 7.2h.01M7.4 16.8h.01"/>',
    cpu:     '<rect x="7" y="7" width="10" height="10" rx="2"/><path d="M10 3.2v2.2M14 3.2v2.2M10 18.6v2.2M14 18.6v2.2M3.2 10h2.2M3.2 14h2.2M18.6 10h2.2M18.6 14h2.2"/>',
    info:    '<circle cx="12" cy="12" r="8.4"/><path d="M12 11.2v4.6M12 7.9h.01"/>',
    bell:    '<path d="M6.2 16.2V11a5.8 5.8 0 1 1 11.6 0v5.2l1.4 2.4H4.8z"/><path d="M10.2 19.2a1.9 1.9 0 0 0 3.6 0"/>',
    link:    '<path d="M9.6 14.4 14.4 9.6"/><path d="M7.6 12 6.2 13.4a3.4 3.4 0 0 0 4.8 4.8L12.4 16.8"/><path d="M16.4 12l1.4-1.4a3.4 3.4 0 0 0-4.8-4.8L11.6 7.2"/>',
    send:    '<path d="M4 12 20 4.6 15.2 20l-3.4-5.6z"/><path d="M11.8 14.4 20 4.6"/>',
    image:   '<rect x="3.4" y="5" width="17.2" height="14" rx="2.4"/><circle cx="8.6" cy="10" r="1.6"/><path d="M4.4 17.4 9.6 12l4 4.2 2.8-2.6 3.2 3.4"/>',
    file:    '<path d="M13.4 3.4H7.2a2 2 0 0 0-2 2v13.2a2 2 0 0 0 2 2h9.6a2 2 0 0 0 2-2V9z"/><path d="M13.4 3.4V9h5.4"/>',
    smile:   '<circle cx="12" cy="12" r="8.4"/><path d="M8.6 14.4a4.4 4.4 0 0 0 6.8 0"/><path d="M9.4 9.7h.01M14.6 9.7h.01"/>',
    call:    '<path d="M5.2 4.6h3.4l1.6 4-2 1.4a11 11 0 0 0 5.8 5.8l1.4-2 4 1.6v3.4a1.6 1.6 0 0 1-1.8 1.6A15.6 15.6 0 0 1 3.6 6.4 1.6 1.6 0 0 1 5.2 4.6z"/>',
    mic:     '<rect x="9.2" y="3.4" width="5.6" height="10.2" rx="2.8"/><path d="M6.2 11.6a5.8 5.8 0 0 0 11.6 0"/><path d="M12 17.4v3.2"/>',
    micoff:  '<rect x="9.2" y="3.4" width="5.6" height="10.2" rx="2.8"/><path d="M6.2 11.6a5.8 5.8 0 0 0 11.6 0"/><path d="M12 17.4v3.2"/><path d="M4.2 4.2 19.8 19.8"/>',
    speaker: '<path d="M4.6 9.4h3.6L12.6 5.6v12.8L8.2 14.6H4.6z"/><path d="M15.6 9.4a3.6 3.6 0 0 1 0 5.2M18.2 7a7.2 7.2 0 0 1 0 10"/>',
    screen:  '<rect x="3.2" y="4.6" width="17.6" height="12" rx="2.2"/><path d="M9 20.2h6"/><path d="M12 13.4V8.6M9.6 11l2.4-2.4L14.4 11"/>',
    plug:    '<path d="M9 3.2v5M15 3.2v5"/><path d="M6.6 8.2h10.8v3.4a5.4 5.4 0 0 1-10.8 0z"/><path d="M12 17v3.8"/>',
    off:     '<path d="M12 3.4v7.4"/><path d="M6.6 7.4a7.6 7.6 0 1 0 10.8 0"/>',
    box:     '<path d="M12 3.4 20 7.6v8.8L12 20.6 4 16.4V7.6z"/><path d="M4 7.6 12 12l8-4.4M12 12v8.6"/>',
    /* 狐狸爪印 / 羊蹄印：仅作装饰纹样，不是角色素材 */
    paw:     '<path d="M12 20.6c2.7 0 4.7-1.6 4.7-3.7 0-1.8-1.4-2.7-2.6-3.3-.9-.5-1.4-.9-2.1-.9s-1.2.4-2.1.9c-1.2.6-2.6 1.5-2.6 3.3 0 2.1 2 3.7 4.7 3.7Z"/>'
             + '<ellipse cx="6.8" cy="10.6" rx="1.9" ry="2.3"/><ellipse cx="10.3" cy="7.1" rx="1.9" ry="2.4"/>'
             + '<ellipse cx="14.4" cy="7.3" rx="1.9" ry="2.4"/><ellipse cx="18" cy="11" rx="1.9" ry="2.3"/>',
    hoof:    '<path d="M9 4.4C7.2 6.2 6.3 9.1 6.3 12.6c0 4 1.3 7 3 7 1.6 0 2.4-1.7 2.4-4.1V8.9c0-2.4-1.3-5.7-2.7-4.5Z"/>'
             + '<path d="M15 4.4c1.8 1.8 2.7 4.7 2.7 8.2 0 4-1.3 7-3 7-1.6 0-2.4-1.7-2.4-4.1V8.9c0-2.4 1.3-5.7 2.7-4.5Z"/>'
  };

  function icon(name, size, cls) {
    var d = ICONS[name] || ICONS.info;
    var s = size || 20;
    return '<svg class="ic ' + (cls || '') + '" width="' + s + '" height="' + s + '" viewBox="0 0 24 24" '
      + 'fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
      + d + '</svg>';
  }

  /* ---------- 4. 素材占位块 ---------- */
  /* ph(code, {h, w, size, round, compact, state}) —— 始终带 data-placeholder 便于检索 */
  function ph(code, opts) {
    opts = opts || {};
    var meta = PLACEHOLDERS[code] || { label: code, where: '' };
    var cls = ['ph'];
    if (opts.round) cls.push('is-round');
    if (opts.compact) cls.push('is-compact');
    if (opts.tag) cls.push('is-tagged');
    var st = [];
    if (opts.size) { st.push('width:' + px(opts.size)); st.push('height:' + px(opts.size)); }
    if (opts.w) st.push('width:' + px(opts.w));
    if (opts.h) st.push('height:' + px(opts.h));
    /* 小尺寸占位（如头像 / 表情位）用短标签显示，完整代码保留在 data-placeholder 与 title 上 */
    /* 若清单里登记了该占位对应的素材文件，则直接从 assets/ 引用（静态兜底见 onerror）。
       页面里所有角色 / 插画占位都经由这里，不再散落素材路径。
       opts.state 会优先取该状态的图，取不到才用兜底图。 */
    var path = assetPath(code, opts.state);
    if (path) {
      /* 真素材：加 ph--img，让 CSS 去掉占位灰盒的底与虚线描边 ——
         透明底的角色素材要露出自己的轮廓，不能垫灰底、也不能被盒子裁切。 */
      cls.push('ph--img');
      return '<div class="' + cls.join(' ') + '" style="' + st.join(';') + '"'
        + ' data-placeholder="' + esc(code) + '" data-state="' + esc(opts.state || '') + '"'
        + ' title="' + esc(code + (opts.state ? '.' + opts.state : '') + ' · ' + (opts.label || meta.label)) + '">'
        + '<img class="ph__asset" src="' + esc(assetRel(path)) + '" alt="' + esc(opts.label || meta.label) + '"'
        + ' loading="lazy" onerror="KSN.assetBroken(this,\'' + esc(code).replace(/'/g, "\\'") + '\')"></div>';
    }
    var inner = opts.compact
      ? '<span class="ph__code">' + esc(opts.tag || code) + '</span>'
      : '<span class="ph__code">' + esc(code) + '</span><span class="ph__label">' + esc(opts.label || meta.label) + '</span>';
    return '<div class="' + cls.join(' ') + '" style="' + st.join(';') + '"'
      + ' data-placeholder="' + esc(code) + '" title="' + esc(code + ' · ' + (opts.label || meta.label)) + '">'
      + inner + '</div>';
  }

  /* ---------- 5. 基础组件 ---------- */
  function btn(label, opts) {
    opts = opts || {};
    var cls = ['btn', 'btn--' + (opts.kind || 'primary')];
    if (opts.block) cls.push('is-block');
    if (opts.small) cls.push('is-small');
    var at = [];
    if (opts.to) at.push('data-nav="' + opts.to + '"');
    if (opts.action) at.push('data-action="' + opts.action + '"');
    if (opts.disabled) at.push('disabled aria-disabled="true"');
    var left = opts.icon ? icon(opts.icon, opts.small ? 15 : 17) : '';
    var right = opts.iconRight ? icon(opts.iconRight, opts.small ? 15 : 17) : '';
    return '<button class="' + cls.join(' ') + '" ' + at.join(' ') + '>'
      + left + '<span>' + esc(label) + '</span>' + right + '</button>';
  }

  function chip(text, tone, withDot) {
    var cls = ['chip'];
    if (tone) cls.push('chip--' + tone);
    var dot = withDot === false ? '' : '<i class="dot"></i>';
    return '<span class="' + cls.join(' ') + '">' + dot + esc(text) + '</span>';
  }

  function appbar(o) {
    o = o || {};
    var l = o.back
      ? '<button class="iconbtn" data-nav="' + o.back + '" aria-label="返回">' + icon('back') + '</button>'
      : (o.left || '<span class="iconbtn is-ghost"></span>');
    return '<header class="appbar">'
      + '<div class="appbar__l">' + l + '</div>'
      + '<div class="appbar__c">'
      +   '<div class="appbar__title">' + esc(o.title || '') + '</div>'
      +   (o.sub ? '<div class="appbar__sub">' + esc(o.sub) + '</div>' : '')
      + '</div>'
      + '<div class="appbar__r">' + (o.right || '') + '</div>'
      + '</header>';
  }

  /* 全局底部导航：入口 / 人人星 / 小机星
     由 app.js 的外壳统一渲染（页面不再各自调用），保证「每个页面都能看到」。
     active 取值：entry | chat | universe */
  var TABBAR_TABS = [
    { key: 'entry',    label: '入口',   to: '#/home',     ic: 'home' },
    { key: 'chat',     label: '人人星', to: '#/chat',     ic: 'chat' },
    { key: 'universe', label: '小机星', to: '#/universe', ic: 'planet' }
  ];
  function tabbar(active) {
    /* 入口页（首页/控制台）保持白蓝主题，底栏跟着走 */
    var cls = 'tabbar' + (active === 'entry' ? ' tabbar--home' : '');
    /* 未读角标：人人星有新消息时挂一个小数字（数量由页面层通过 KSN.unreadBadge 提供）。
       ⚠️ 这里**不能写 K** —— 本文件的作用域里没有 K 这个别名，写 K 会 ReferenceError、把外壳渲染打断。
       要用 window.KSN（运行期调用时它已经构建完成）。 */
    var ns = window.KSN || {};
    var unread = ns.unreadBadge ? (ns.unreadBadge() || 0) : 0;
    return '<nav class="' + cls + '">' + TABBAR_TABS.map(function (t) {
      var badge = (t.key === 'chat' && unread)
        ? '<i class="tabbar__badge">' + (unread > 9 ? '9+' : unread) + '</i>' : '';
      return '<a class="tabbar__item' + (t.key === active ? ' is-active' : '') + '" data-nav="' + t.to + '">'
        + icon(t.ic, 16) + '<span>' + t.label + '</span>' + badge + '</a>';
    }).join('') + '</nav>';
  }

  function card(inner, opts) {
    opts = opts || {};
    var cls = ['card'];
    if (opts.flat) cls.push('is-flat');
    if (opts.tight) cls.push('is-tight');
    return '<div class="' + cls.join(' ') + '">' + inner + '</div>';
  }

  function listRow(o) {
    o = o || {};
    var tappable = !!(o.to || o.action);
    var tag = tappable ? 'a' : 'div';
    var at = o.to ? ' data-nav="' + o.to + '"' : (o.action ? ' data-action="' + o.action + '"' : '');
    var cls = 'row' + (tappable ? ' is-tappable' : '') + (o.tone ? ' row--' + o.tone : '');
    var left = o.icon ? '<span class="row__icon">' + icon(o.icon) + '</span>' : '';
    var right = o.right !== undefined && o.right !== '' ? o.right : (o.to ? icon('chevron', 18) : '');
    return '<' + tag + ' class="' + cls + '"' + at + '>'
      + left
      + '<span class="row__main">'
      +   '<span class="row__title">' + esc(o.title) + '</span>'
      +   (o.sub ? '<span class="row__sub">' + esc(o.sub) + '</span>' : '')
      + '</span>'
      + (right ? '<span class="row__right">' + right + '</span>' : '')
      + '</' + tag + '>';
  }

  function field(o) {
    o = o || {};
    var cls = ['field'];
    if (o.error) cls.push('is-error');
    var label = o.label ? '<label class="field__label">' + esc(o.label) + (o.required ? '<i>*</i>' : '') + '</label>' : '';
    var msg = o.error
      ? '<div class="field__msg is-error">' + icon('alert', 13) + '<span>' + esc(o.error) + '</span></div>'
      : (o.hint ? '<div class="field__msg">' + esc(o.hint) + '</div>' : '');
    return '<div class="' + cls.join(' ') + '">' + label
      + '<div class="field__box">'
      +   '<input class="field__input" type="text" readonly value="' + esc(o.value || '') + '" placeholder="' + esc(o.placeholder || '') + '">'
      + '</div>' + msg + '</div>';
  }

  function kv(label, value, opts) {
    opts = opts || {};
    return '<div class="kv' + (opts.strong ? ' is-strong' : '') + '">'
      + '<span class="kv__k">' + esc(label) + '</span>'
      + '<span class="kv__v">' + value + '</span></div>';
  }

  function sectionTitle(text, right) {
    return '<div class="sect"><span class="sect__t">' + esc(text) + '</span>'
      + (right ? '<span class="sect__r">' + right + '</span>' : '') + '</div>';
  }

  function note(text) {
    return '<div class="note">' + icon('info', 14) + '<span>' + text + '</span></div>';
  }

  function banner(o) {
    o = o || {};
    return '<div class="banner' + (o.kind ? ' banner--' + o.kind : '') + '">'
      + '<span class="banner__ic">' + icon(o.icon || 'info', 18) + '</span>'
      + '<span class="banner__main">'
      +   (o.title ? '<span class="banner__title">' + esc(o.title) + '</span>' : '')
      +   (o.body ? '<span class="banner__body">' + esc(o.body) + '</span>' : '')
      + '</span>'
      + (o.action ? btn(o.action.label, { kind: 'ghost', small: true, to: o.action.to, action: o.action.action }) : '')
      + '</div>';
  }

  function modal(o) {
    o = o || {};
    return '<div class="scrim"><div class="modal' + (o.kind ? ' modal--' + o.kind : '') + '">'
      + '<div class="modal__title">' + esc(o.title) + '</div>'
      + '<div class="modal__body">' + (o.body || '') + '</div>'
      + '<div class="modal__actions">'
      + (o.actions || []).map(function (a) {
          return btn(a.label, { kind: a.kind || 'ghost', to: a.to, action: a.action, block: true });
        }).join('')
      + '</div></div></div>';
  }

  function toast(o) {
    o = o || {};
    return '<div class="toast' + (o.kind ? ' toast--' + o.kind : '') + '">'
      + '<span class="toast__ic">' + (o.avatar ? o.avatar : icon(o.icon || 'bell', 18)) + '</span>'
      + '<span class="toast__main">'
      +   '<span class="toast__title">' + esc(o.title) + '</span>'
      +   (o.body ? '<span class="toast__body">' + esc(o.body) + '</span>' : '')
      + '</span>'
      + (o.time ? '<span class="toast__time">' + esc(o.time) + '</span>' : '')
      + '</div>';
  }

  /* ---------- 6. 页面注册 ---------- */
  var SCREENS = [];
  function registerScreen(s) { SCREENS.push(s); }

  return {
    PLACEHOLDERS: PLACEHOLDERS,
    esc: esc, icon: icon, ph: ph, btn: btn, chip: chip, appbar: appbar, tabbar: tabbar,
    rel: assetRel, assetRel: assetRel,
    assetPath: assetPath, swapAsset: swapAsset,
    card: card, listRow: listRow, field: field, kv: kv, sectionTitle: sectionTitle,
    note: note, banner: banner, modal: modal, toast: toast,
    registerScreen: registerScreen, screens: SCREENS
  };
})();

/* =====================================================================
   Kissne 手机端低保真原型 · app.js
   哈希路由 + 外壳渲染 + 侧栏（路由表 / 状态切换 / 占位图例）
   ===================================================================== */
(function () {
  'use strict';
  var K = window.KSN;
  var esc = K.esc;

  var $routeList = document.getElementById('routeList');
  var $stateList = document.getElementById('stateList');
  var $stageBody = document.getElementById('stageBody');
  var $routeLabel = document.getElementById('routeLabel');
  var $purpose = document.getElementById('screenPurpose');
  var $outList = document.getElementById('outList');


  /* ---------------- 冷启动开屏 ----------------
     冷启动（= 本次页面加载）才播放开屏动画，播完自动进下一页。
     在应用内切回 #/welcome 不会重播。 */
  var SPLASH_SESSION_KEY = 'kissne.splash.consumed';
  var COLD = true;
  try { COLD = sessionStorage.getItem(SPLASH_SESSION_KEY) !== '1'; } catch (e) {}
  var splashTimer = null;
  var SPLASH_MS = 9000;          /* 动画播放完成后的兜底计时 */
  function splashNext() {
    var T = window.KissneTransport;
    /* 首次使用、没有本地设备凭据：进入连接页。
       已经配对过：直接进入入口页。启动阶段不 bootstrap、不自动跳聊天。 */
    return T && typeof T.hasToken === 'function' && T.hasToken() ? '#/home' : '#/connect';
  }
  function finishSplash() {
    if (!COLD) return;
    COLD = false;
    try { sessionStorage.setItem(SPLASH_SESSION_KEY, '1'); } catch (e) {}
    clearTimeout(splashTimer);
    /* 开屏是启动过渡，不属于 App 导航历史。
       replace 掉 welcome，后续连接页/首页返回时绝不会翻回开屏。 */
    location.replace(splashNext());
  }

  /* ---------------- 路由解析 ---------------- */
  function parseHash() {
    var raw = (location.hash || '').replace(/^#/, '') || '/welcome';
    var i = raw.indexOf('?');
    return {
      path: i < 0 ? raw : raw.slice(0, i),
      params: new URLSearchParams(i < 0 ? '' : raw.slice(i + 1))
    };
  }

  function findScreen(path) {
    for (var i = 0; i < K.screens.length; i++) {
      if (K.screens[i].route === '#' + path) return K.screens[i];
    }
    return null;
  }

  function nav(to) {
    if (!to) return;
    if (!COLD && String(to).indexOf('#/welcome') === 0) {
      to = '#/home';
    }
    if (COLD && String(to).indexOf('#/welcome') !== 0) {
      COLD = false;
      clearTimeout(splashTimer);
    }
    /* Once anything leaves the splash, cancel every pending splash timer/event
       before changing hash. Connection/home/chat can never be pulled back. */
    if (COLD && String(to).indexOf('#/welcome') !== 0) {
      COLD = false;
      clearTimeout(splashTimer);
    }
    if (location.hash === to) { render(); return; }
    location.hash = to;
  }

  /* 切状态时保留其它查询参数（如 chat 页的 model / effort 选择），
     否则在侧栏点状态会把用户刚选好的模型/思考强度冲掉 */
  function setState(key) {
    var cur = parseHash();
    var p = new URLSearchParams(cur.params);
    p.set('state', key);
    location.hash = '#' + cur.path + '?' + p.toString();
  }

  /* 成品开屏自然结束后立即进入正确落点；9s timeout 只作解码失败兜底。 */
  document.addEventListener('kissne:splash-end', function () {
    var cur = parseHash();
    if (!COLD || cur.path !== '/welcome' || cur.params.get('state') !== 'animate') return;
    finishSplash();
  });

  /* ---------------- 手机外壳 ---------------- */
  function statusbar() {
    return '<div class="statusbar"><span class="statusbar__time">9:41</span>'
      + '<span class="statusbar__icons">'
      + '<i class="sb-bars"><b></b><b></b><b></b><b></b></i>'
      + '<i class="sb-wifi"></i>'
      + '<i class="sb-bat"><b></b></i>'
      + '</span></div>';
  }

  function phone(screen, state, interactive, params) {
    /* params 透传给页面，供「下拉里选中的值」这类非 state 参数使用 */
    var ctx = { state: state, nav: nav, params: params || null };
    /* 全局底栏：每个页面都显示，所以在外壳里统一挂载。
       只有开屏页（启动画面）不挂 —— 全屏品牌动画上压一条导航条会把它弄脏。 */
    var showTab = ['welcome', 'connect', 'connect-success'].indexOf(screen.id) < 0;
    /* 流体云（活动胶囊）：通话 / 屏幕共享在后台继续时，顶部留一条可点回来的提示。
       和底栏一样挂在**外壳层**，所以切任何页面都在。由页面层提供内容（K.activityPill）。 */
    var pill = (interactive !== false && K.activityPill) ? K.activityPill() : '';
    return '<div class="phone' + (interactive === false ? ' is-static' : '') + '">'
      + statusbar()
      + pill
      + '<div class="phone__screen">' + screen.render(ctx) + '</div>'
      + (showTab ? K.tabbar(screen.tab) : '')
      + '</div>';
  }

  /* ---------------- 侧栏 ---------------- */
  function renderRouteList(current) {
    $routeList.innerHTML = K.screens.map(function (s) {
      var active = s.route === '#' + current.path;
      return '<a class="rt' + (active ? ' is-active' : '') + '" data-nav="' + s.route + '">'
        + '<span class="rt__no">' + s.no + '</span>'
        + '<span class="rt__main"><span class="rt__name">' + esc(s.name) + '</span>'
        + '<span class="rt__path">' + s.route + '</span></span></a>';
    }).join('')
      + '<a class="rt' + (current.path === '/overview' ? ' is-active' : '') + '" data-nav="#/overview">'
      + '<span class="rt__no">★</span><span class="rt__main"><span class="rt__name">全部页面总览</span>'
      + '<span class="rt__path">#/overview</span></span></a>';
  }

  function renderStateList(screen, current) {
    if (!screen) { $stateList.innerHTML = '<span class="muted">总览模式无状态切换</span>'; return; }
    var cur = current.params.get('state') || screen.states[0].key;
    $stateList.innerHTML = screen.states.map(function (st) {
      return '<button class="stchip' + (st.key === cur ? ' is-active' : '') + '" data-state="' + st.key + '">'
        + esc(st.label) + '</button>';
    }).join('');
  }

  function renderMeta(screen) {
    if (!screen) {
      $purpose.textContent = '同时渲染全部页面，用于整体预览与截图。';
      $outList.innerHTML = '';
      return;
    }
    $purpose.textContent = screen.purpose || '';
    $outList.innerHTML = (screen.out || []).map(function (o) {
      return '<a class="outlink" data-nav="' + o + '">' + esc(o) + '</a>';
    }).join('');
  }

  /* ---------------- 总览 ---------------- */
  function renderOverview() {
    var frames = K.screens.map(function (s) {
      return '<figure class="mini">'
        + '<div class="mini__frame">' + phone(s, s.states[0].key, false) + '</div>'
        + '<figcaption><b>' + s.no + ' · ' + esc(s.name) + '</b><span>' + s.route + '</span></figcaption>'
        + '</figure>';
    }).join('');
    $stageBody.innerHTML = '<div class="overview">' + frames + '</div>';
  }

  /* ---------------- 页面级生命周期 ----------------
     页面默认只是「返回一段 HTML」，没有 JS 生命周期。
     遇到需要自己动起来的页面（如小机星页的像素场景），
     页面可以导出 mount(root, ctx) 并返回一个 dispose 函数，
     这里负责在切页/重渲染时把上一个页面的定时器清掉，避免越积越多。 */
  var screenDispose = null;
  function runMount(screen, root, ctx) {
    if (screenDispose) { try { screenDispose(); } catch (e) {} screenDispose = null; }
    if (screen && typeof screen.mount === 'function') {
      try { screenDispose = screen.mount(root, ctx) || null; } catch (e) { screenDispose = null; }
    }
  }

  /* ---------------- 主渲染 ---------------- */
  function render() {
    var current = parseHash();
    if (!COLD && current.path === '/welcome') {
      location.replace('#/home');
      return;
    }
    if (COLD && current.path !== '/welcome') {
      COLD = false;
      try { sessionStorage.setItem(SPLASH_SESSION_KEY, '1'); } catch (e) {}
      clearTimeout(splashTimer);
    }
    var isOverview = current.path === '/overview';
    var screen = findScreen(current.path);

    if (!screen && !isOverview) {
      $stageBody.innerHTML = '<div class="empty404"><b>未找到该路由</b><span>' + esc(current.path) + '</span></div>';
      renderRouteList(current); renderStateList(null, current); renderMeta(null);
      runMount(null);
      return;
    }

    if (isOverview) {
      renderOverview();
      $routeLabel.textContent = '#/overview';
      renderStateList(null, current);
      renderMeta(null);
      runMount(null);
    } else {
      var state = current.params.get('state') || screen.states[0].key;
      var valid = screen.states.some(function (s) { return s.key === state; });
      if (!valid) { state = screen.states[0].key; }
      $stageBody.innerHTML = '<div class="stage__inner">' + phone(screen, state, true, current.params) + '</div>';
      $routeLabel.textContent = '#' + current.path + (current.params.get('state') ? '?state=' + state : '');
      renderStateList(screen, current);
      renderMeta(screen);
      runMount(screen, $stageBody.querySelector('.phone'), { state: state, params: current.params });

      /* 冷启动：开屏动画播完自动进下一页；此后不再重播 */
      clearTimeout(splashTimer);
      if (screen.id === 'welcome' && state === 'animate' && COLD) {
        splashTimer = setTimeout(finishSplash, SPLASH_MS);
      }
    }
    renderRouteList(current);
  }

  /* ---------------- 交互 ---------------- */
  function nativeTap() {
    try {
      if (window.KissneNativeTransport && typeof window.KissneNativeTransport.haptic === 'function') {
        window.KissneNativeTransport.haptic();
      }
    } catch (e) {}
  }

  document.addEventListener('click', function (e) {
    var navEl = e.target.closest('[data-nav]');
    if (navEl) {
      e.preventDefault();
      nativeTap();
      nav(navEl.getAttribute('data-nav'));
      openDrawer(false);
      return;
    }
    var stEl = e.target.closest('[data-state]');
    if (stEl) { nativeTap(); setState(stEl.getAttribute('data-state')); openDrawer(false); return; }

    var actEl = e.target.closest('[data-action]');
    if (actEl) {
      nativeTap();
      var a = actEl.getAttribute('data-action');
      var cur = parseHash();
      if (a === 'connect') {
        /* 真 Transport 的 connect 由连接页 mount 处理；这里只保留纯静态总览的兜底。 */
        if (!window.KissneTransport) nav('#/connect/success');
      }
      else if (a === 'splash-skip') {
        finishSplash();
      }
      else if (a === 'check-update') {
        try {
          if (window.KissneNativeTransport && typeof window.KissneNativeTransport.checkForUpdates === 'function') {
            window.KissneNativeTransport.checkForUpdates();
          }
        } catch (e) {}
      }
      else if (a === 'disconnect') {
        var T = window.KissneTransport;
        if (!T || typeof T.revoke !== 'function') {
          if (T && typeof T.clearToken === 'function') T.clearToken();
          nav('#/home?state=offline');
        } else {
          T.revoke().then(function () {
            nav('#/home?state=offline');
          }).catch(function () {
            /* Do not pretend the server revoked the token. Keep the device
               page open so the user can retry instead of creating split state. */
            nav('#/device?state=disconnect-confirm');
          });
        }
      }
      else if (a === 'sync') nav('#/memory?state=syncing');
      else if (a === 'resend') nav('#/chat?state=replying');
      return;
    }
  });

  /* 流体云上的计时：每秒刷一次文本（不重渲染整个页面） */
  setInterval(function () {
    var el = document.querySelector('[data-pill-time]');
    if (el && K.activityPillTime) el.textContent = K.activityPillTime();
  }, 1000);

  /* ---------------- 手机抽屉（替代侧栏） ---------------- */
  var $panel = document.querySelector('.panel');
  var $drawerBtn = document.getElementById('drawerBtn');
  var $drawerScrim = document.getElementById('drawerScrim');

  function openDrawer(open) {
    if (!$panel) return;
    $panel.classList.toggle('is-open', !!open);
    if ($drawerScrim) $drawerScrim.classList.toggle('is-open', !!open);
  }

  if ($drawerBtn) {
    $drawerBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      openDrawer(!$panel.classList.contains('is-open'));
    });
  }
  if ($drawerScrim) $drawerScrim.addEventListener('click', function () { openDrawer(false); });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { openDrawer(false); return; }
    var current = parseHash();
    var screen = findScreen(current.path);
    if (!screen) return;
    var idx = screen.states.findIndex(function (s) {
      return s.key === (current.params.get('state') || screen.states[0].key);
    });
    if (e.key === 'ArrowRight' && idx < screen.states.length - 1) setState(screen.states[idx + 1].key);
    if (e.key === 'ArrowLeft' && idx > 0) setState(screen.states[idx - 1].key);
  });

  window.addEventListener('hashchange', render);
  /* ---------------- 启动 ---------------- */
  /* ?shot=1 进入截图模式：手机框固定在视口左上角，便于按 390×844 裁切 */
  if (new URLSearchParams(location.search).get('shot')) {
    document.body.classList.add('is-shot');
  }
  /* 冷启动走开屏动画，其余情况直接落到开屏页的定格态 */
  if (!location.hash || location.hash === '#') {
    location.hash = COLD ? '#/welcome?state=animate' : '#/welcome';
  }
  render();

})();
})();

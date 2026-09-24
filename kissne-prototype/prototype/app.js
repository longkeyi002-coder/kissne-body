/* =====================================================================
   Kissne 手机端 UI · app.js
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


  /* ---------------- 会话索引 ---------------- */
  window.KissneSessionIndex = window.KissneSessionIndex || {
    sessions: [], raw: null, loaded: false, fetchedAt: 0, error: ''
  };

  function normalizeRemoteSessions(payload) {
    var raw = payload || {};
    var list = Array.isArray(raw) ? raw : (Array.isArray(raw.sessions) ? raw.sessions : []);
    var explicitActiveId = String(raw.active_session_id || raw.activeSessionId || '');
    var fallbackActiveId = '';
    if (!explicitActiveId) {
      for (var ai = 0; ai < list.length; ai++) {
        var candidate = list[ai] || {};
        if (candidate.active === true || candidate.current === true || candidate.is_current === true) {
          fallbackActiveId = String(candidate.session_id || candidate.id || candidate.sessionId || '');
          if (fallbackActiveId) break;
        }
      }
    }
    var activeId = explicitActiveId || fallbackActiveId;
    return list.map(function (item, index) {
      item = item || {};
      var id = String(item.session_id || item.id || item.sessionId || '');
      var titleSource = String(item.title_source || item.titleSource || '');
      var rawTitle = String(item.title || item.name || item.label || '').trim();
      if (!titleSource && (/^Kissne Mobile\b/i.test(rawTitle) || /^kissne_mobile\s*[:/]/i.test(rawTitle))) {
        rawTitle = '';
      }
      return {
        id: id,
        key: String(item.session_key || item.key || item.sessionKey || ''),
        title: rawTitle || ('会话 ' + (index + 1)),
        titleSource: titleSource,
        updatedAt: item.last_active || item.updated_at || item.updatedAt || null,
        createdAt: item.created_at || item.createdAt || null,
        messageCount: Number(item.message_count || item.messageCount || 0) || 0,
        source: String(item.source || ''),
        active: !!activeId && id === activeId
      };
    }).filter(function (item) { return !!(item.id || item.key); });
  }

  async function loadRemoteSessionsAtStartup(T) {
    if (!T || typeof T.sessions !== 'function') return;
    var index = window.KissneSessionIndex;
    try {
      /* Update-safe path: first use the token already stored by Android
         EncryptedSharedPreferences. Only a real 401 is allowed to rotate it. */
      if (typeof T.ensureToken === 'function') await T.ensureToken(false);
      var payload;
      try {
        payload = await T.sessions();
      } catch (err) {
        if (!err || Number(err.status) !== 401 || typeof T.ensureToken !== 'function') throw err;
        await T.ensureToken(true);
        payload = await T.sessions();
      }
      index.raw = payload || {};
      index.sessions = normalizeRemoteSessions(payload);
      index.loaded = true;
      index.fetchedAt = Date.now();
      index.error = '';
      document.dispatchEvent(new CustomEvent('kissne:sessions-loaded', { detail: index }));
    } catch (err) {
      index.loaded = false;
      index.error = String((err && err.message) || 'sessions_unavailable');
      document.dispatchEvent(new CustomEvent('kissne:sessions-error', { detail: index }));
    }
  }

  window.KissneRefreshSessions = function () {
    return loadRemoteSessionsAtStartup(window.KissneTransport);
  };

  /* ---------------- 路由解析 ---------------- */
  function parseHash() {
    var raw = (location.hash || '').replace(/^#/, '') || '/home';
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
    /* 全局底栏由外壳统一挂载。 */
    var showTab = true;
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

  /* Long-press a chat message to hand only that message to a temporary web AI. */
  var webAiPressTimer = null;
  var webAiPressTarget = null;
  var webAiPressStartX = 0;
  var webAiPressStartY = 0;
  function closeWebAiSheet() {
    var old = document.querySelector('.webai-sheet');
    if (old) old.remove();
  }
  function openWebAiSheet(msg) {
    closeWebAiSheet();
    var text = msg && msg.getAttribute('data-message-text') || '';
    if (!text.trim()) return;
    var sheet = document.createElement('div');
    sheet.className = 'webai-sheet';
    sheet.innerHTML = '<button class="webai-sheet__scrim" type="button" data-webai-close aria-label="关闭"></button>'
      + '<div class="webai-sheet__panel"><div class="webai-sheet__grab"></div>'
      + '<div class="webai-sheet__title">处理这条消息</div>'
      + '<button class="webai-sheet__item" type="button" data-webai-copy>复制<span>复制当前消息文本</span></button>'
      + '<button class="webai-sheet__item" type="button" data-webai-provider="deepseek">DeepSeek<span>临时网页 · 不共享上下文</span></button>'
      + '<button class="webai-sheet__item" type="button" data-webai-provider="chatgpt">ChatGPT<span>临时网页 · 不共享上下文</span></button>'
      + '<div class="webai-sheet__note">只发送当前这条消息，不会带上 Kissne 记忆或其他聊天内容。</div></div>';
    sheet.dataset.messageText = text;
    document.body.appendChild(sheet);
  }
  document.addEventListener('pointerdown', function (e) {
    var msg = e.target.closest && e.target.closest('[data-chat-message]');
    if (!msg) return;
    webAiPressTarget = msg;
    webAiPressStartX = e.clientX;
    webAiPressStartY = e.clientY;
    clearTimeout(webAiPressTimer);
    webAiPressTimer = setTimeout(function () {
      nativeTap();
      openWebAiSheet(webAiPressTarget);
      webAiPressTimer = null;
    }, 520);
  });
  ['pointerup','pointercancel'].forEach(function (name) {
    document.addEventListener(name, function () {
      clearTimeout(webAiPressTimer);
      webAiPressTimer = null;
    }, { passive: true });
  });
  document.addEventListener('pointermove', function (e) {
    if (!webAiPressTimer) return;
    var dx = e.clientX - webAiPressStartX;
    var dy = e.clientY - webAiPressStartY;
    if ((dx * dx + dy * dy) > 100) {
      clearTimeout(webAiPressTimer);
      webAiPressTimer = null;
    }
  }, { passive: true });

  document.addEventListener('click', function (e) {
    var webAiClose = e.target.closest('[data-webai-close]');
    if (webAiClose) { closeWebAiSheet(); return; }
    var webAiCopy = e.target.closest('[data-webai-copy]');
    if (webAiCopy) {
      var copySheet = webAiCopy.closest('.webai-sheet');
      var copyText = copySheet ? copySheet.dataset.messageText || '' : '';
      if (copyText) {
        try {
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(copyText).catch(function () {});
          } else {
            var ta = document.createElement('textarea');
            ta.value = copyText;
            ta.setAttribute('readonly', '');
            ta.style.position = 'fixed';
            ta.style.opacity = '0';
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            ta.remove();
          }
        } catch (err) {}
      }
      closeWebAiSheet();
      return;
    }
    var webAiProvider = e.target.closest('[data-webai-provider]');
    if (webAiProvider) {
      var provider = webAiProvider.getAttribute('data-webai-provider');
      var sheet = webAiProvider.closest('.webai-sheet');
      var text = sheet ? sheet.dataset.messageText || '' : '';
      var webAiUrls = {
        deepseek: 'https://chat.deepseek.com/',
        chatgpt: 'https://chatgpt.com/'
      };
      if (webAiUrls[provider]) {
        try {
          if (window.KissneNativeTransport && typeof window.KissneNativeTransport.openBrowserWithText === 'function') {
            window.KissneNativeTransport.openBrowserWithText(webAiUrls[provider], text);
          }
        } catch (err) {}
        closeWebAiSheet();
      }
      return;
    }

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
      if (a === 'open-browser') {
        try {
          if (window.KissneNativeTransport && typeof window.KissneNativeTransport.openBrowser === 'function') {
            window.KissneNativeTransport.openBrowser('https://chat.deepseek.com/');
          }
        } catch (e) {}
      }
      else if (a === 'check-update') {
        try {
          if (window.KissneNativeTransport && typeof window.KissneNativeTransport.checkForUpdates === 'function') {
            window.KissneNativeTransport.checkForUpdates();
          }
        } catch (e) {}
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
  if (!location.hash || location.hash === '#') {
    location.hash = '#/home';
  }
  render();

  /* Authentication and session discovery are background concerns. */
  (function startBackgroundServices() {
    var T = window.KissneTransport;
    if (T && typeof T.sessions === 'function') {
      loadRemoteSessionsAtStartup(T).catch(function () {});
    } else if (T && typeof T.ensureToken === 'function') {
      T.ensureToken(false).catch(function () {});
    }
  })();

})();

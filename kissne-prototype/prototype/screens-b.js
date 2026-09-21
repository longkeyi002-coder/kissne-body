/* =====================================================================
   Kissne 手机端 UI · screens-b.js
   页面 07–10：记忆库 / 设备管理 / 设置 / 通知与弹窗
   ===================================================================== */
(function () {
  'use strict';
  var K = window.KSN;
  var ph = K.ph, btn = K.btn, icon = K.icon, chip = K.chip, appbar = K.appbar,
      card = K.card, field = K.field, tabbar = K.tabbar, modal = K.modal,
      note = K.note, sectionTitle = K.sectionTitle, listRow = K.listRow,
      banner = K.banner, kv = K.kv, toast = K.toast, esc = K.esc;

  /* =====================================================================
     07 记忆库页
     ===================================================================== */
  var MEMORY_STATES = [
    { key: 'list', label: '记忆列表' },
    { key: 'detail', label: '记忆详情' },
    { key: 'delete-confirm', label: '删除确认' }
  ];
  var MEMORY_INDEX = { items: [], loaded: false, error: '' };

  function memoryItemById(id) {
    id = String(id || '');
    for (var i = 0; i < MEMORY_INDEX.items.length; i++) {
      if (String(MEMORY_INDEX.items[i].id || '') === id) return MEMORY_INDEX.items[i];
    }
    return null;
  }
  function memoryTitle(item) {
    var text = String(item && item.text || '').replace(/\s+/g, ' ').trim();
    return text.length > 34 ? text.slice(0, 34) + '…' : (text || '未命名记忆');
  }
  function memoryListHtml() {
    if (!MEMORY_INDEX.loaded && MEMORY_INDEX.error) {
      return '<div class="mempty"><div class="mempty__t">暂时无法读取记忆库</div>'
        + '<div class="mempty__s">这里只显示 Hermes 的真实记忆，不再使用演示数据。</div></div>';
    }
    if (!MEMORY_INDEX.loaded) {
      return '<div class="mempty"><div class="mempty__t">正在读取记忆…</div></div>';
    }
    if (!MEMORY_INDEX.items.length) {
      return '<div class="mempty">' + ph('MEMORY_EMPTY_ILLUSTRATION', { size: 140 })
        + '<div class="mempty__t">暂无记忆</div>'
        + '<div class="mempty__s">这里只显示真实写入 MEMORY.md / USER.md 的内容。</div></div>';
    }
    return card(MEMORY_INDEX.items.map(function (item) {
      var source = item.target === 'user' ? '用户资料' : '长期记忆';
      return listRow({
        title: memoryTitle(item),
        sub: source + ' · ' + String(item.source || ''),
        to: '#/memory?state=detail&id=' + encodeURIComponent(String(item.id || '')),
        right: icon('chevron', 16)
      });
    }).join(''), { tight: true });
  }

  K.registerScreen({
    no: '07', id: 'memory', name: '记忆库页', route: '#/memory', tab: null,
    purpose: '直接读取 Hermes 的真实 MEMORY.md / USER.md；支持查看和真实删除，不展示演示记忆。',
    out: ['#/home', '#/memory?state=detail'],
    states: MEMORY_STATES,
    render: function (ctx) {
      var s = ctx.state || 'list';
      var id = ctx.params && ctx.params.get('id') || '';
      var item = memoryItemById(id);

      if (s === 'detail' || s === 'delete-confirm') {
        var detail = item
          ? '<div class="memdetail"><h2 class="memdetail__t">' + esc(memoryTitle(item)) + '</h2>'
            + '<div class="memdetail__meta">' + chip(item.target === 'user' ? '用户资料' : '长期记忆')
            + '<span class="muted">' + esc(item.source || '') + '</span></div>'
            + '<p class="memdetail__body">' + esc(item.text || '') + '</p></div>'
          : '<div class="mempty"><div class="mempty__t">这条记忆不存在</div></div>';
        return '<div class="screen">'
          + appbar({ title: '记忆详情', back: '#/memory' })
          + '<div class="screen__body">' + detail + '</div>'
          + (item ? '<div class="screen__foot">'
              + btn('删除记忆', { to: '#/memory?state=delete-confirm&id=' + encodeURIComponent(id), block: true, kind: 'danger' })
              + '</div>' : '')
          + (s === 'delete-confirm' && item ? modal({
              title: '删除这条记忆？',
              kind: 'danger',
              body: '<p>将从 Hermes 的真实记忆文件中永久删除这条内容。</p>',
              actions: [
                { label: '取消', to: '#/memory?state=detail&id=' + encodeURIComponent(id), kind: 'ghost' },
                { label: '确认删除', action: 'delete-memory', kind: 'danger' }
              ]
            }) : '')
          + '</div>';
      }

      return '<div class="screen">'
        + appbar({
            title: '记忆库',
            sub: MEMORY_INDEX.loaded ? ('真实记忆 · ' + MEMORY_INDEX.items.length + ' 条') : 'Hermes 真实记忆',
            back: '#/home',
            right: '<button class="iconbtn" data-memory-refresh aria-label="刷新">' + icon('sync') + '</button>'
          })
        + '<div class="screen__body"><div class="adminnotice" data-memory-notice hidden></div>'
        + '<div data-memory-list>' + memoryListHtml() + '</div></div></div>';
    },
    mount: function (root, ctx) {
      var T = window.KissneTransport;
      var host = root.querySelector('[data-memory-list]');
      var refresh = root.querySelector('[data-memory-refresh]');
      var notice = root.querySelector('[data-memory-notice]');
      var del = root.querySelector('[data-action="delete-memory"]');
      var stopped = false;

      function show(text) {
        if (!notice) return;
        notice.hidden = !text;
        notice.textContent = text || '';
      }
      function paint() {
        if (host && !stopped) host.innerHTML = memoryListHtml();
      }
      async function reload() {
        if (!T || typeof T.memories !== 'function') {
          MEMORY_INDEX.loaded = false;
          MEMORY_INDEX.error = 'transport_unavailable';
          paint();
          return;
        }
        show('正在读取真实记忆…');
        try {
          if (typeof T.ensureToken === 'function') await T.ensureToken(false);
          var payload = await T.memories();
          MEMORY_INDEX.items = Array.isArray(payload && payload.items) ? payload.items : [];
          MEMORY_INDEX.loaded = true;
          MEMORY_INDEX.error = '';
          if (!stopped) { show(''); paint(); }
        } catch (err) {
          MEMORY_INDEX.loaded = false;
          MEMORY_INDEX.error = String(err && err.message || 'memory_unavailable');
          if (!stopped) { show('记忆库读取失败'); paint(); }
        }
      }
      async function onDelete(e) {
        e.preventDefault();
        e.stopPropagation();
        var id = ctx && ctx.params && ctx.params.get('id') || '';
        if (!id || !T || typeof T.deleteMemory !== 'function') return;
        del.disabled = true;
        try {
          await T.deleteMemory(id);
          MEMORY_INDEX.items = MEMORY_INDEX.items.filter(function (entry) {
            return String(entry.id || '') !== String(id);
          });
          location.hash = '#/memory';
        } catch (err) {
          del.disabled = false;
          del.textContent = '删除失败 · 重试';
        }
      }
      function onRefresh(e) { e.preventDefault(); e.stopPropagation(); reload(); }

      if (refresh) refresh.addEventListener('click', onRefresh);
      if (del) del.addEventListener('click', onDelete);
      if ((ctx && ctx.state || 'list') === 'list') reload();

      return function () {
        stopped = true;
        if (refresh) refresh.removeEventListener('click', onRefresh);
        if (del) del.removeEventListener('click', onDelete);
      };
    }
  });

  /* =====================================================================
     08 设备管理页
     ===================================================================== */
  K.registerScreen({
    no: '08', id: 'device', name: '设备管理页', route: '#/device', tab: null,
    purpose: '查看 installation_id、服务器地址和真实连接状态。token 由 App 自动领取与刷新。',
    out: ['#/home', '#/settings'],
    states: [{ key: 'normal', label: '自动状态' }],
    render: function () {
      return `
      <div class="screen">
        ${appbar({ title: '设备管理', back: '#/home',
          right: '<button class="iconbtn" data-device-refresh aria-label="刷新">' + icon('refresh') + '</button>' })}
        <div class="screen__body">
          <div class="adminnotice" data-device-notice hidden></div>
          ${card(
            kv('当前设备', 'Kissne Mobile', { strong: true })
            + kv('在线状态', '<span data-device-status>检测中…</span>')
            + kv('Installation ID', '<code data-device-id>—</code>')
            + kv('服务器地址', '<span data-device-base>—</span>')
            + kv('认证', '<span data-device-auth>自动 device token</span>')
            + kv('当前模型', '跟随 Hermes')
          )}
          ${note('无需配对码。App 会用 installation_id 自动领取 device token；token 失效时会自动重新领取。')}
        </div>
      </div>`;
    },
    mount: function (root) {
      var T = window.KissneTransport;
      var refresh = root.querySelector('[data-device-refresh]');
      var notice = root.querySelector('[data-device-notice]');
      var stopped = false;

      function setText(sel, value) {
        var el = root.querySelector(sel);
        if (el) el.textContent = value == null ? '—' : String(value);
      }
      function show(kind, text) {
        if (!notice) return;
        notice.hidden = !text;
        notice.className = 'adminnotice' + (kind ? ' is-' + kind : '');
        notice.textContent = text || '';
      }
      async function probe() {
        if (!T) {
          setText('[data-device-status]', '离线');
          show('error', 'Mobile Transport 不可用');
          return;
        }
        setText('[data-device-id]', typeof T.installationId === 'function' ? T.installationId() : '—');
        setText('[data-device-base]', typeof T.base === 'function' ? T.base() : '—');
        setText('[data-device-status]', '检测中…');
        show('', '');
        try {
          if (typeof T.ensureToken === 'function') await T.ensureToken(false);
          var boot = await T.bootstrap();
          if (!boot || !boot.bound) {
            if (!stopped) {
              setText('[data-device-status]', '准备中');
              setText('[data-device-auth]', 'device token 有效 · 会话尚未绑定');
            }
            return;
          }
          if (!stopped) {
            setText('[data-device-status]', '在线');
            setText('[data-device-auth]', 'device token 有效');
          }
        } catch (err) {
          if (err && err.status === 401 && typeof T.ensureToken === 'function') {
            try {
              await T.ensureToken(true);
              var retryBoot = await T.bootstrap();
              if (!retryBoot || !retryBoot.bound) {
                if (!stopped) {
                  setText('[data-device-status]', '准备中');
                  setText('[data-device-auth]', 'token 已刷新 · 会话尚未绑定');
                }
                return;
              }
              if (!stopped) {
                setText('[data-device-status]', '在线');
                setText('[data-device-auth]', 'device token 已自动刷新');
              }
              return;
            } catch (retryErr) {}
          }
          if (!stopped) {
            setText('[data-device-status]', '离线');
            setText('[data-device-auth]', '等待自动恢复');
            show('error', '当前无法访问 Kissne 服务端。');
          }
        }
      }
      function onRefresh(e) {
        e.preventDefault();
        e.stopPropagation();
        probe();
      }
      if (refresh) refresh.addEventListener('click', onRefresh);
      probe();
      return function () {
        stopped = true;
        if (refresh) refresh.removeEventListener('click', onRefresh);
      };
    }
  });

  /* =====================================================================
     08b 会话列表 —— 直接读取 /admin/sessions
     ===================================================================== */
  function sessionsPageRows(query) {
    var idx = window.KissneSessionIndex || {};
    var sessions = Array.isArray(idx.sessions) ? idx.sessions.slice() : [];
    var q = String(query || '').trim().toLowerCase();

    if (!idx.loaded && idx.error) {
      return card('<div class="sessiondrawer__empty">暂时无法读取服务器会话列表</div>');
    }
    if (!sessions.length) {
      return card('<div class="sessiondrawer__empty">' + (idx.loaded ? '服务器暂无会话' : '正在读取会话…') + '</div>');
    }

    if (q) {
      sessions = sessions.filter(function (s) {
        return (String(s.title || '') + ' ' + String(s.key || '') + ' ' + String(s.source || ''))
          .toLowerCase().indexOf(q) >= 0;
      });
    }
    if (!sessions.length) {
      return card('<div class="sessiondrawer__empty">没有匹配的会话</div>');
    }

    sessions.sort(function (x, y) {
      var ax = new Date(x.updatedAt || x.createdAt || 0).getTime() || 0;
      var ay = new Date(y.updatedAt || y.createdAt || 0).getTime() || 0;
      return ay - ax;
    });

    return card(sessions.map(function (s) {
      var parts = [];
      if (s.messageCount) parts.push(s.messageCount + ' 条消息');
      var when = s.updatedAt || s.createdAt;
      if (when) {
        var d = new Date(when);
        parts.push(isNaN(d.getTime()) ? String(when) : d.toLocaleString([], {
          month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'
        }));
      }
      if (s.source) parts.push(String(s.source));
      return '<button type="button" class="row is-tappable sessionpage__row"'
        + ' data-session-page-id="' + esc(s.id || '') + '" data-session-page-key="' + esc(s.key || '') + '"'
        + ' data-session-page-active="' + (s.active ? '1' : '0') + '">'
        + '<span class="row__icon">' + icon('chat') + '</span>'
        + '<span class="row__main"><span class="row__title">' + esc(s.title || '未命名会话') + '</span>'
        + '<span class="row__sub">' + esc(parts.join(' · ') || '服务器会话') + '</span></span>'
        + '<span class="row__right">' + (s.active ? chip('当前', 'solid') : icon('chevron', 18)) + '</span>'
        + '</button>';
    }).join(''), { tight: true });
  }

  K.registerScreen({
    no: '08b', id: 'sessions', name: '会话列表', route: '#/sessions', tab: null,
    purpose: '读取 /admin/sessions，查看 Hermes Runtime 中属于当前安装的全部对话。',
    out: ['#/home', '#/chat'],
    states: [{ key: 'default', label: '全部会话' }],
    render: function () {
      return `
      <div class="screen">
        ${appbar({
          title: '会话列表',
          sub: '全部对话',
          back: '#/home',
          right: '<button class="iconbtn" data-sessions-refresh aria-label="刷新会话">' + icon('refresh') + '</button>'
        })}
        <div class="screen__body">
          <div class="srchbox">
            ${icon('search', 15)}
            <input class="srchbox__in" data-sessions-search type="text" placeholder="搜索会话" aria-label="搜索会话">
          </div>
          <div class="adminnotice" data-sessions-notice hidden></div>
          <div data-sessions-page-list>${sessionsPageRows('')}</div>
          ${note('数据来自 /mobile/admin/sessions；点按历史会话会按稳定 session_id 切换到对应 Hermes 对话。')}
        </div>
      </div>`;
    },
    mount: function (root) {
      var search = root.querySelector('[data-sessions-search]');
      var refresh = root.querySelector('[data-sessions-refresh]');
      var host = root.querySelector('[data-sessions-page-list]');
      var notice = root.querySelector('[data-sessions-notice]');
      var stopped = false;

      function paint() {
        if (!host || stopped) return;
        host.innerHTML = sessionsPageRows(search ? search.value : '');
      }
      function show(text) {
        if (!notice) return;
        notice.hidden = !text;
        notice.textContent = text || '';
      }
      async function reload() {
        if (typeof window.KissneRefreshSessions !== 'function') {
          show('Mobile Transport 暂不可用');
          return;
        }
        show('正在刷新会话…');
        try {
          await window.KissneRefreshSessions();
          if (!stopped) {
            show('');
            paint();
          }
        } catch (e) {
          if (!stopped) {
            show('会话列表刷新失败');
            paint();
          }
        }
      }
      async function onSessionSelect(e) {
        var row = e.target && e.target.closest ? e.target.closest('[data-session-page-id]') : null;
        if (!row || !host || !host.contains(row)) return;
        e.preventDefault();
        e.stopPropagation();
        if (row.getAttribute('data-session-page-active') === '1') {
          location.hash = '#/chat';
          return;
        }
        var id = String(row.getAttribute('data-session-page-id') || '');
        var key = String(row.getAttribute('data-session-page-key') || '');
        var T = window.KissneTransport;
        if (!T || typeof T.selectSession !== 'function') { show('当前版本无法切换会话'); return; }
        show('正在切换会话…');
        try {
          await T.selectSession(key, id);
          if (typeof window.KissneRefreshSessions === 'function') await window.KissneRefreshSessions();
          location.hash = '#/chat';
        } catch (err) {
          show('会话切换失败，请重试');
        }
      }
      function onSearch() { paint(); }
      function onRefresh(e) {
        e.preventDefault();
        e.stopPropagation();
        reload();
      }

      if (search) search.addEventListener('input', onSearch);
      if (refresh) refresh.addEventListener('click', onRefresh);
      if (host) host.addEventListener('click', onSessionSelect);
      paint();
      reload();

      return function () {
        stopped = true;
        if (search) search.removeEventListener('input', onSearch);
        if (refresh) refresh.removeEventListener('click', onRefresh);
        if (host) host.removeEventListener('click', onSessionSelect);
      };
    }
  });

  /* =====================================================================
     09 设置页
     ===================================================================== */
  K.registerScreen({
    no: '09', id: 'settings', name: '设置页', route: '#/settings', tab: null,
    purpose: '账号信息、设备状态、通知、运维与版本更新入口。',
    out: ['#/home', '#/device', '#/admin'],
    states: [{ key: 'default', label: '默认' }],
    render: function () {
      return `
      <div class="screen">
        ${appbar({ title: '设置', back: '#/home' })}
        <div class="screen__body">
          ${card(
            '<div class="acct">'
            + ph('FOX_NOTIFICATION_AVATAR', { size: 44, compact: true, tag: '头像' })
            + '<div class="acct__main"><div class="acct__name">龙柯伊</div>'
            + '<div class="acct__sub">本地账号 · 未登录云端</div></div>'
            + '</div>'
          )}
          ${card(
            listRow({ title: '账号信息', sub: '昵称 / 头像 / 本地数据', icon: 'user' })
            + listRow({ title: '设备管理', sub: '当前设备', icon: 'plug', to: '#/device' })
            + listRow({ title: '会话列表', sub: '查看服务器上的全部对话', icon: 'chat', to: '#/sessions' })
            + listRow({ title: '模型设置', sub: '跟随 Hermes', icon: 'cpu' })
            + listRow({ title: '通知设置', sub: '新消息 / 服务状态 / 记忆同步', icon: 'bell', to: '#/notifications' })
            + listRow({ title: '运维与部署', sub: '版本 / 上游合并 / 回滚 / 部署日志', icon: 'server', to: '#/admin' })
          , { tight: true })}
          ${card(
            listRow({ title: '检查更新', sub: '检查并下载最新 Kissne APK', icon: 'refresh', action: 'check-update', right: chip('自动检查', 'solid') })
            + listRow({ title: '关于 Kissne', sub: 'V0.2.1 · Android 合体版', icon: 'info' })
          , { tight: true })}
          ${note('版本更新会自动检查；发现新版本后可在 App 内直接下载，再由 Android 系统确认安装。')}
        </div>
      </div>`;
    }
  });

  /* =====================================================================
     10 通知和弹窗
     ===================================================================== */
  K.registerScreen({
    no: '10', id: 'notifications', name: '通知和弹窗', route: '#/notifications', tab: null,
    purpose: '消息、连接、记忆同步、配对与确认操作的通知状态。',
    out: ['#/chat', '#/device', '#/memory'],
    states: [{ key: 'default', label: '全部' }],
    render: function () {
      var foxNotify = ph('FOX_NOTIFICATION_AVATAR', { size: 40, compact: true, tag: '头像' });
      return `
      <div class="screen">
        ${appbar({ title: '通知和弹窗', back: '#/home' })}
        <div class="screen__body">
          ${sectionTitle('轻提示')}
          ${card(
            '<div class="demo">' + toast({ avatar: foxNotify, title: '叶青栩', body: '在的，今天想聊什么？', time: '刚刚' }) + '</div>'
            + '<div class="demo">' + toast({ icon: 'check', kind: 'ok', title: '连接成功', body: '设备已连接', time: '09:41' }) + '</div>'
            + '<div class="demo">' + toast({ icon: 'check', title: '记忆已保存', body: '「周末计划」已写入记忆库', time: '09:38' }) + '</div>'
          , { tight: true })}

          ${sectionTitle('状态横幅')}
          ${card(
            '<div class="demo">' + banner({ icon: 'wifioff', kind: 'warn', title: '设备离线',
              body: '聊天与同步暂不可用。', action: { label: '重新连接', to: '#/device' } }) + '</div>'
            + '<div class="demo">' + banner({ icon: 'alert', kind: 'warn', title: '记忆同步失败',
              body: '无法访问设备，请检查连接。', action: { label: '重试', action: 'sync' } }) + '</div>'

          , { tight: true })}

          ${sectionTitle('确认弹窗')}
          <div class="demo demo--modal">
            ${modal({ title: '断开设备？', kind: 'danger',
              body: '<p>断开后将无法聊天，记忆同步也会暂停。</p>',
              actions: [{ label: '取消', kind: 'ghost' }, { label: '确认断开', kind: 'danger' }] })}
          </div>
          <div class="demo demo--modal">
            ${modal({ title: '删除这条记忆？', kind: 'danger',
              body: '<p>「周末计划」将被永久删除，且无法恢复。</p>',
              actions: [{ label: '取消', kind: 'ghost' }, { label: '确认删除', kind: 'danger' }] })}
          </div>
        </div>
      </div>`;
    }
  });


  /* =====================================================================
     11 运维与部署
     ===================================================================== */
  K.registerScreen({
    no: '11', id: 'admin', name: '运维与部署', route: '#/admin', tab: null,
    purpose: '查看服务端版本与运行状态，执行上游合并、回滚，并实时查看部署日志。',
    out: ['#/settings'],
    states: [{ key: 'default', label: '默认' }],
    render: function () {
      return `
      <div class="screen screen--admin">
        ${appbar({
          title: '运维与部署',
          sub: 'Kissne Admin',
          back: '#/settings',
          right: '<button class="iconbtn" data-admin-refresh aria-label="刷新状态">' + icon('refresh') + '</button>'
        })}
        <div class="screen__body">
          <div class="adminnotice" data-admin-notice hidden></div>

          ${sectionTitle('运行状态')}
          ${card(
            kv('版本', '<code data-admin-head>读取中…</code>', { strong: true })
            + kv('分支', '<span data-admin-branch>—</span>')
            + kv('运行时长', '<span data-admin-uptime>—</span>')
            + kv('本地修改', '<span data-admin-dirty>—</span>')
            + kv('部署状态', '<span data-admin-deploy>—</span>')
          )}

          ${sectionTitle('部署操作')}
          <div class="adminops">
            <button type="button" class="btn btn--primary is-block" data-admin-op="merge">
              ${icon('sync', 17)}<span>合并上游更新</span>
            </button>
            <button type="button" class="btn btn--ghost is-block" data-admin-op="rollback">
              ${icon('refresh', 17)}<span>回滚到 GitHub 最新版</span>
            </button>
          </div>

          <div class="adminconfirm" data-admin-confirm hidden>
            <div class="adminconfirm__title" data-admin-confirm-title></div>
            <div class="adminconfirm__body" data-admin-confirm-body></div>
            <div class="adminconfirm__actions">
              <button type="button" class="btn btn--ghost is-block" data-admin-cancel><span>取消</span></button>
              <button type="button" class="btn btn--primary is-block" data-admin-run><span>确认执行</span></button>
            </div>
          </div>

          ${sectionTitle('部署日志')}
          <pre class="adminlog" data-admin-log>尚无部署日志</pre>
          ${note('合并或回滚会重启网关，App 可能短暂断连；恢复后页面会继续查询部署结果。')}
        </div>
      </div>`;
    },
    mount: function (root) {
      var T = window.KissneTransport;
      if (!T || typeof T.adminStatus !== 'function') return null;

      var disposed = false;
      var pollTimer = null;
      var confirmKind = '';
      var notice = root.querySelector('[data-admin-notice]');
      var log = root.querySelector('[data-admin-log]');
      var confirmBox = root.querySelector('[data-admin-confirm]');
      var mergeBtn = root.querySelector('[data-admin-op="merge"]');
      var rollbackBtn = root.querySelector('[data-admin-op="rollback"]');

      function setText(sel, value) {
        var el = root.querySelector(sel);
        if (el) el.textContent = value == null ? '—' : String(value);
      }
      function showNotice(kind, text) {
        if (!notice) return;
        notice.hidden = !text;
        notice.className = 'adminnotice' + (kind ? ' is-' + kind : '');
        notice.textContent = text || '';
      }
      function formatUptime(seconds) {
        var n = Math.max(0, Number(seconds) || 0);
        var h = Math.floor(n / 3600);
        var m = Math.floor((n % 3600) / 60);
        if (h) return h + ' 小时 ' + m + ' 分钟';
        return m + ' 分钟';
      }
      function setBusy(busy) {
        [mergeBtn, rollbackBtn].forEach(function (el) {
          if (!el) return;
          el.disabled = !!busy;
          el.setAttribute('aria-disabled', busy ? 'true' : 'false');
        });
      }
      function applyStatus(data) {
        data = data || {};
        var git = data.git || {};
        var deploy = data.deploy || {};
        setText('[data-admin-head]', git.describe || git.head || '—');
        setText('[data-admin-branch]', git.branch || '—');
        setText('[data-admin-uptime]', formatUptime(data.uptime_seconds));
        setText('[data-admin-dirty]', Number(git.dirty_files || 0) + ' 个文件');
        var label = deploy.running
          ? ((deploy.type === 'rollback' ? '回滚' : '合并') + '进行中')
          : (deploy.success === true ? '上次部署成功' : (deploy.success === false ? '上次部署失败' : '空闲'));
        setText('[data-admin-deploy]', label);
        setBusy(!!deploy.running);
        return !!deploy.running;
      }
      function handleError(err, retryDeployLog) {
        var status = Number(err && err.status) || 0;
        if (status === 401) {
          showNotice('working', 'device token 已失效，正在自动刷新认证…');
          if (T && typeof T.ensureToken === 'function') {
            T.ensureToken(true).then(function () {
              if (retryDeployLog) pollDeployLog(100);
              else loadStatus();
            }).catch(function () {
              showNotice('error', '暂时无法恢复设备认证，请稍后重试。');
              setBusy(false);
            });
          } else {
            showNotice('error', '暂时无法恢复设备认证，请稍后重试。');
            setBusy(false);
          }
          return;
        }
        if (status === 409) {
          showNotice('working', '已有部署操作正在进行，已切换到当前部署日志。');
          pollDeployLog(0);
          return;
        }
        if (status === 404) {
          showNotice('error', '部署脚本不存在，请联系管理员。');
          setBusy(false);
          return;
        }
        if (retryDeployLog) {
          showNotice('working', '网关正在重启或暂时不可达，正在继续等待部署恢复。');
          schedulePoll(3000);
          return;
        }
        showNotice('error', '无法读取运维状态，请检查连接后重试。');
        setBusy(false);
      }
      async function loadStatus() {
        try {
          if (typeof T.ensureToken === 'function') await T.ensureToken(false);
          var data = await T.adminStatus();
          if (disposed) return;
          var running = applyStatus(data);
          showNotice('', '');
          if (running) pollDeployLog(0);
        } catch (err) {
          if (!disposed) handleError(err, false);
        }
      }
      function schedulePoll(ms) {
        clearTimeout(pollTimer);
        if (!disposed) pollTimer = setTimeout(function () { pollDeployLog(100); }, ms);
      }
      async function pollDeployLog(lines) {
        try {
          var data = await T.adminDeployLog(lines || 100);
          if (disposed) return;
          if (log) {
            log.textContent = String(data.log || '暂无部署日志');
            log.scrollTop = log.scrollHeight;
          }
          var running = !!data.running;
          var success = data.success;
          setBusy(running);
          setText('[data-admin-deploy]', running
            ? ((data.type === 'rollback' ? '回滚' : '合并') + '进行中')
            : (success === true ? '部署成功' : (success === false ? '部署失败' : '状态待确认')));
          if (running) {
            showNotice('working', '部署正在进行，日志每 3 秒自动刷新。');
            schedulePoll(3000);
          } else if (success === true) {
            showNotice('ok', '部署成功。');
            loadStatus();
          } else if (success === false) {
            showNotice('error', '部署失败，请查看日志。');
            loadStatus();
          } else {
            /* Gateway restart resets in-memory deploy state. Do not turn an
               unknown post-restart state into a false failure. */
            showNotice('working', '网关已恢复，正在重新确认部署状态。');
            loadStatus();
          }
        } catch (err) {
          if (!disposed) handleError(err, true);
        }
      }
      function openConfirm(kind) {
        confirmKind = kind;
        if (!confirmBox) return;
        confirmBox.hidden = false;
        setText('[data-admin-confirm-title]', kind === 'rollback' ? '确认回滚？' : '确认合并上游更新？');
        setText(
          '[data-admin-confirm-body]',
          kind === 'rollback'
            ? '代码将恢复到 GitHub 上 kissne-main 的最新版本，随后网关会重启。'
            : '将合并上游更新并重启网关，App 会短暂断连。'
        );
      }
      function closeConfirm() {
        confirmKind = '';
        if (confirmBox) confirmBox.hidden = true;
      }
      async function runConfirmed() {
        var kind = confirmKind;
        closeConfirm();
        if (!kind) return;
        setBusy(true);
        showNotice('working', kind === 'rollback' ? '正在启动回滚…' : '正在启动上游合并…');
        try {
          if (kind === 'rollback') await T.adminRollback();
          else await T.adminMerge();
          if (disposed) return;
          pollDeployLog(100);
        } catch (err) {
          if (!disposed) handleError(err, false);
        }
      }
      function onClick(e) {
        var op = e.target.closest('[data-admin-op]');
        if (op) {
          e.preventDefault();
          openConfirm(op.getAttribute('data-admin-op'));
          return;
        }
        if (e.target.closest('[data-admin-cancel]')) {
          e.preventDefault();
          closeConfirm();
          return;
        }
        if (e.target.closest('[data-admin-run]')) {
          e.preventDefault();
          runConfirmed();
          return;
        }
        if (e.target.closest('[data-admin-refresh]')) {
          e.preventDefault();
          loadStatus();
        }
      }

      root.addEventListener('click', onClick);
      loadStatus();

      return function () {
        disposed = true;
        clearTimeout(pollTimer);
        root.removeEventListener('click', onClick);
      };
    }
  });


})();

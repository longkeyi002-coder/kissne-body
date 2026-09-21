/* =====================================================================
   Kissne 手机端低保真原型 · screens-b.js
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
    { key: 'list',            label: '记忆列表' },
    { key: 'empty',           label: '暂无记忆' },
    { key: 'syncing',         label: '正在同步' },
    { key: 'sync-ok',         label: '同步成功' },
    { key: 'sync-fail',       label: '同步失败' },
    { key: 'detail',          label: '记忆详情' },
    { key: 'edit',            label: '编辑记忆' },
    { key: 'delete-confirm',  label: '删除确认' }
  ];

  var MEMORY_ITEMS = [
    { t: '周末计划',      s: '「周六去美术馆，周日下午收拾房间」', c: '生活', time: '今天' },
    { t: '项目代号',      s: '「内部代号定为 Kissne」',            c: '工作', time: '昨天' },
    { t: '饮食偏好',      s: '「不吃香菜，喜欢偏甜口」',            c: '偏好', time: '3 天前' }
  ];

  K.registerScreen({
    no: '07', id: 'memory', name: '记忆库页', route: '#/memory', tab: null,
    purpose: '记忆列表 / 分类筛选 / 详情 / 编辑 / 删除二次确认，覆盖空、同步中、同步成功与失败状态。',
    out: ['#/home', '#/memory?state=detail'],
    states: MEMORY_STATES,
    render: function (ctx) {
      var s = ctx.state || 'list';

      /* --- 详情 --- */
      if (s === 'detail') {
        return `
        <div class="screen">
          ${appbar({ title: '记忆详情', back: '#/memory',
                     right: '<button class="iconbtn" data-nav="#/memory?state=edit" aria-label="编辑">' + icon('edit') + '</button>' })}
          <div class="screen__body">
            <div class="memdetail">
              <h2 class="memdetail__t">周末计划</h2>
              <div class="memdetail__meta">${chip('生活')}${chip('已同步', 'warn')}<span class="muted">更新于今天 09:12</span></div>
              <p class="memdetail__body">周六去美术馆，周日下午收拾房间。用户希望上午出发、避开人流高峰。</p>
              ${card(
                kv('来源', '聊天页 · 叶青栩')
                + kv('写入方式', '自动提取')
                + kv('记忆 ID', 'mem_20260917_001')
              )}
            </div>
          </div>
          <div class="screen__foot">
            ${btn('编辑记忆', { to: '#/memory?state=edit', block: true, kind: 'ghost' })}
            ${btn('删除记忆', { to: '#/memory?state=delete-confirm', block: true, kind: 'danger' })}
          </div>
        </div>`;
      }

      /* --- 编辑 --- */
      if (s === 'edit') {
        return `
        <div class="screen">
          ${appbar({ title: '编辑记忆', back: '#/memory?state=detail' })}
          <div class="screen__body">
            ${field({ label: '标题', value: '周末计划' })}
            ${field({ label: '内容', value: '周六去美术馆，周日下午收拾房间。' })}
            ${field({ label: '分类', value: '生活' })}
            </div>
          <div class="screen__foot">
            ${btn('保存', { to: '#/memory?state=sync-ok', block: true, kind: 'primary' })}
            ${btn('取消', { to: '#/memory?state=detail', block: true, kind: 'ghost' })}
          </div>
        </div>`;
      }

      /* --- 列表 / 空 / 同步 --- */
      var topBanner = '';
      if (s === 'syncing')  topBanner = banner({ icon: 'sync', title: '正在同步', body: '正在与设备同步记忆库…' });
      if (s === 'sync-ok')  topBanner = banner({ icon: 'check', kind: 'ok', title: '同步成功', body: '记忆库已是最新（12 条）。' });
      if (s === 'sync-fail') topBanner = banner({ icon: 'alert', kind: 'warn', title: '同步失败',
        body: '无法访问设备，请检查连接后重试。', action: { label: '重试', action: 'sync' } });

      var body;
      if (s === 'empty') {
        body = '<div class="mempty">'
          + ph('MEMORY_EMPTY_ILLUSTRATION', { size: 140 })
          + '<div class="mempty__t">暂无记忆</div>'
          + '<div class="mempty__s">对话中值得保留的内容会自动写入这里。</div>'
          + '</div>';
      } else {
        body = '<div class="searchbar is-todo">' + icon('search', 17)
          + '<span class="searchbar__ph">搜索记忆</span>'

          + '<span class="searchbar__filter">' + icon('box', 17) + '筛选</span></div>'
          + '<div class="chips is-todo">' + chip('全部', 'solid') + chip('生活') + chip('工作') + chip('偏好')
          + '</div>'
          + sectionTitle('全部记忆', '<span class="muted">12 条</span>')
          + card(MEMORY_ITEMS.map(function (m) {
              return listRow({
                title: m.t, sub: m.s, to: '#/memory?state=detail',
                right: '<span class="row__time">' + m.time + '</span>'
              });
            }).join(''), { tight: true });
      }

      return `
      <div class="screen">
        ${appbar({ title: '记忆库', sub: 'Kissne · 已同步',
                   right: '<button class="iconbtn" data-action="sync" aria-label="同步">' + icon('sync') + '</button>' })}
        ${topBanner}
        <div class="screen__body">
          ${body}
        </div>
        ${s === 'delete-confirm' ? modal({
          title: '删除这条记忆？',
          kind: 'danger',
          body: '<p>「周末计划」将被永久删除，且无法恢复。</p><p class="muted">删除操作需要二次确认。</p>',
          actions: [
            { label: '取消', to: '#/memory?state=list', kind: 'ghost' },
            { label: '确认删除', to: '#/memory?state=empty', kind: 'danger' }
          ]
        }) : ''}
      </div>`;
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
          await T.bootstrap();
          if (!stopped) {
            setText('[data-device-status]', '在线');
            setText('[data-device-auth]', 'device token 有效');
          }
        } catch (err) {
          if (err && err.status === 401 && typeof T.ensureToken === 'function') {
            try {
              await T.ensureToken(true);
              await T.bootstrap();
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

/* =====================================================================
   Kissne 手机端低保真原型 · screens-b.js
   页面 07–10：记忆库 / 设备管理 / 设置 / 通知与弹窗
   附加：素材占位总表（占位标记登记页）
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
              <div class="memdetail__meta">${chip('生活')}${chip('已同步 · 示例', 'warn')}<span class="muted">更新于今天 09:12</span></div>
              <p class="memdetail__body">周六去美术馆，周日下午收拾房间。用户希望上午出发、避开人流高峰。</p>
              ${card(
                kv('来源', '聊天页 · 叶青栩')
                + kv('写入方式', '自动提取（待接入）')
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
            ${note('低保真原型：输入框不可编辑，保存动作不写入真实数据。')}
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
          + '<span class="searchbar__tag">待实现</span>'
          + '<span class="searchbar__filter">' + icon('box', 17) + '筛选</span></div>'
          + '<div class="chips is-todo">' + chip('全部', 'solid') + chip('生活') + chip('工作') + chip('偏好')
          + '<span class="chips__tag">筛选待实现</span></div>'
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
        ${appbar({ title: '记忆库', sub: 'Kissne 设备 · 已同步（示例）',
                   right: '<button class="iconbtn" data-action="sync" aria-label="同步">' + icon('sync') + '</button>' })}
        ${topBanner}
        <div class="screen__body">
          ${body}
          ${s !== 'empty' ? note('搜索与筛选目前只是界面占位（已标注「待实现」），不产生真实过滤；删除记忆必须二次确认。') : ''}
        </div>
        ${s !== 'empty' ? '<div class="screen__foot">' + btn('新建记忆（占位）', { block: true, kind: 'ghost', icon: 'plus', disabled: true }) + '</div>' : ''}
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
  var DEVICE_STATES = [
    { key: 'normal',             label: '已连接（示例）' },
    { key: 'offline',            label: '设备离线' },
    { key: 'reconnecting',       label: '重新连接中' },
    { key: 'disconnect-confirm', label: '断开确认' }
  ];

  K.registerScreen({
    no: '08', id: 'device', name: '设备管理页', route: '#/device', tab: null,
    purpose: '查看当前设备信息、重新连接、断开设备（断开必须二次确认）。',
    out: ['#/home', '#/connect', '#/settings'],
    states: DEVICE_STATES,
    render: function (ctx) {
      var s = ctx.state || 'normal';
      var offline = s === 'offline';
      var reconnecting = s === 'reconnecting';

      var topBanner = '';
      if (offline) topBanner = banner({ icon: 'wifioff', kind: 'warn', title: '设备离线',
        body: '最后一次在线：3 小时前。', action: { label: '重新连接', to: '#/device?state=reconnecting' } });
      if (reconnecting) topBanner = banner({ icon: 'sync', title: '正在重新连接',
        body: '正在尝试与设备握手…' });

      return `
      <div class="screen">
        ${appbar({ title: '设备管理', back: '#/home' })}
        ${topBanner}
        <div class="screen__body">
          ${card(
            kv('当前设备', '<span class="is-pending">待接入</span>', { strong: true })
            + kv('在线状态', chip(offline ? '离线' : (reconnecting ? '连接中' : '在线（示例）'), (offline || reconnecting) ? 'warn' : 'solid'))
            + kv('服务器地址', '<span class="is-pending">待接入</span>')
            + kv('当前模型', '默认模型（待接入）')
            + kv('最近连接时间', offline ? '3 小时前' : '刚刚 · 09:41')
          )}
          ${sectionTitle('连接操作')}
          ${card(
            listRow({ title: '重新连接', sub: '重新与设备建立连接', icon: 'refresh', to: '#/device?state=reconnecting' })
            + listRow({ title: '连接设置', sub: '配对码 / Key / 服务器地址', icon: 'link', to: '#/connect' })
            + listRow({ title: '断开设备', sub: '断开后聊天与同步将不可用', icon: 'off', tone: 'danger', to: '#/device?state=disconnect-confirm' })
          , { tight: true })}
          ${note('断开设备必须弹出确认框。')}
        </div>
        ${s === 'disconnect-confirm' ? modal({
          title: '断开设备？',
          kind: 'danger',
          body: '<p>断开后将无法聊天，记忆同步也会暂停。</p><p class="muted">你可以随时重新连接。</p>',
          actions: [
            { label: '取消', to: '#/device?state=normal', kind: 'ghost' },
            { label: '确认断开', to: '#/home?state=offline', action: 'disconnect', kind: 'danger' }
          ]
        }) : ''}
      </div>`;
    }
  });

  /* =====================================================================
     09 设置页
     ===================================================================== */
  K.registerScreen({
    no: '09', id: 'settings', name: '设置页', route: '#/settings', tab: null,
    purpose: '账号信息、设备、连接、通知与版本更新入口。',
    out: ['#/home', '#/device', '#/connect', '#/assets'],
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
            + chip('待接入', 'warn')
            + '</div>'
          )}
          ${card(
            listRow({ title: '账号信息', sub: '昵称 / 头像 / 本地数据', icon: 'user', right: chip('后续页面', 'warn') })
            + listRow({ title: '设备管理', sub: '当前设备 · 待接入', icon: 'plug', to: '#/device' })
            + listRow({ title: '模型设置', sub: '默认模型（待接入）', icon: 'cpu', right: chip('后续页面', 'warn') })
            + listRow({ title: '连接设置', sub: '配对码 / Key / 服务器地址', icon: 'link', to: '#/connect' })
            + listRow({ title: '通知设置', sub: '新消息 / 连接状态 / 记忆同步', icon: 'bell', to: '#/notifications' })
            + listRow({ title: '素材占位总表', sub: '全部占位标记的登记与说明', icon: 'box', to: '#/assets' })
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
    purpose: '8 种低保真通知 / 弹窗状态：新消息、连接成功、设备离线、记忆已保存、同步失败、配对码错误、断开确认、删除确认。',
    out: ['#/chat', '#/device', '#/memory'],
    states: [{ key: 'default', label: '全部' }],
    render: function () {
      var foxNotify = ph('FOX_NOTIFICATION_AVATAR', { size: 40, compact: true, tag: '头像' });
      return `
      <div class="screen">
        ${appbar({ title: '通知和弹窗', sub: '低保真状态集 · 灰阶', back: '#/home' })}
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
            + '<div class="demo">' + banner({ icon: 'alert', kind: 'warn', title: '配对码错误',
              body: '配对码不正确，请重新核对。' }) + '</div>'
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
          ${note('全部为灰阶低保真状态，最终配色与图标待确认后替换。')}
        </div>
      </div>`;
    }
  });

  /* =====================================================================
     附加：素材占位总表
     ===================================================================== */
  K.registerScreen({
    no: '11', id: 'assets', name: '素材占位总表', route: '#/assets', tab: null,
    excludeFromOverview: false,
    purpose: '登记本原型中全部占位标记：代码、用途、出现位置、尺寸、当前状态。正式素材确认后按代码替换。',
    out: ['#/home'],
    states: [{ key: 'default', label: '默认' }],
    render: function () {
      var rows = Object.keys(K.PLACEHOLDERS).map(function (code) {
        var m = K.PLACEHOLDERS[code];
        return '<div class="prow">'
          + '<div class="prow__head"><code>' + esc(code) + '</code>' + chip('待接入', 'warn') + '</div>'
          + '<div class="prow__meta">' + esc(m.label) + ' · 尺寸 ' + esc(m.size) + '</div>'
          + '<div class="prow__where">' + esc(m.where) + '</div>'
          + '</div>';
      }).join('');

      /* 统一素材目录结构（与 assets/ 物理目录一致；角色/背景/动画/图标/特效都从这里引用） */
      var assetTree = '<div class="assetdir">'
        + '<div><b>assets/</b></div>'
        + '<div class="d">├─ characters/ → yeqingxu（avatar·expressions·actions·notifications）· sheep · duo</div>'
        + '<div class="d">├─ animations/ → entry · chat · aiworld · memory · transitions</div>'
        + '<div class="d">├─ backgrounds/ → 房间 / 室外 / 星球</div>'
        + '<div class="d">├─ icons/ → 单文件 + 精灵 sprites.svg（currentColor，主题可继承）</div>'
        + '<div class="d">├─ effects/ → glow · ripple · pulse · shimmer</div>'
        + '<div class="d">└─ placeholders/ → 插画占位</div>'
        + '</div>';

      /* 动画占位展示：每个都带 prefers-reduced-motion 静态降级 */
      var animKeys = ['entry/logo-morph', 'chat/typing', 'aiworld/orbit',
        'memory/sync', 'transitions/page-fade', 'transitions/route-push'];
      var animGrid = '<div class="animgrid">' + animKeys.map(function (k) {
        return '<div class="animgrid__i">'
          + '<div class="animgrid__box">' + K.anim(k) + '</div>'
          + '<div class="animgrid__t"><code>' + esc(k) + '</code><span class="tag">静态兜底</span></div>'
          + '</div>';
      }).join('') + '</div>';

      return `
      <div class="screen">
        ${appbar({ title: '素材占位总表', sub: Object.keys(K.PLACEHOLDERS).length + ' 个占位标记 · 正式素材确认后替换', back: '#/home' })}
        <div class="screen__body">
          ${banner({ icon: 'box', title: '替换方式',
            body: '正式素材完成后，按 data-placeholder 代码替换 assets/ 下同名文件即可，页面结构不变。' })}
          ${sectionTitle('统一素材目录（assets/）')}
          ${card(assetTree, { tight: true })}
          ${sectionTitle('动画占位（均带静态 fallback）')}
          ${animGrid}
          ${note('动画占位用轻量 CSS/SVG 实现；开启系统「减少动态效果」即自动退化为静态首帧，不会闪、不会动。')}
          ${sectionTitle('占位标记登记')}
          ${card(rows, { tight: true })}
          ${sectionTitle('小羊羔素材说明')}
          ${card(
            '<div class="prow__head"><code>SHEEP_CHARACTER_RESERVED</code>' + chip('保留入口', 'warn') + '</div>'
            + '<p class="prow__note">小羊羔暂不放入核心聊天页面。后续可用于双角色页面、特殊状态、关于页面、组合通知、小机星或关系展示页面。当前只保留素材入口，不自行生成或修改小羊羔形象。</p>'
          )}
          ${note('本页只登记占位，不包含任何最终角色或插画素材。')}
        </div>
      </div>`;
    }
  });
})();

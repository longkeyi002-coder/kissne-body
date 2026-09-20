/* =====================================================================
   Kissne 手机端低保真原型 · screens-a.js
   页面 01–06：欢迎 / 设备连接 / 连接成功 / 首页 / 聊天 / 小机星
   ===================================================================== */
(function () {
  'use strict';
  var K = window.KSN;
  var ph = K.ph, btn = K.btn, icon = K.icon, chip = K.chip, appbar = K.appbar,
      card = K.card, field = K.field, tabbar = K.tabbar, modal = K.modal,
      note = K.note, sectionTitle = K.sectionTitle, listRow = K.listRow,
      banner = K.banner, kv = K.kv, esc = K.esc;

  /* =====================================================================
     01 欢迎 / 入口页
     ===================================================================== */
  K.registerScreen({
    no: '01', id: 'welcome', name: '欢迎 / 入口页', route: '#/welcome', tab: null,
    purpose: '按真实素材对象编排的连续开屏：Logo、胶囊、球、带球角色、动作帧、双人贴贴。',
    out: ['#/connect'],
    states: [
      { key: 'final',   label: '定格 · 双人贴贴' },
      { key: 'animate', label: '播放完整开屏动画' },
      { key: 'intro',   label: '定格 · 只有 Logo' }
    ],
    render: function () {
      return `
      <div class="screen screen--splash">
        <div class="splash-redesign" data-splash-redesign>
          <canvas class="splash-redesign__canvas" aria-label="Kissne 开屏动画"></canvas>
        </div>
      </div>`;
    },
    mount: function (root, ctx) {
      var stage = root.querySelector('[data-splash-redesign]');
      var canvas = stage && stage.querySelector('canvas');
      if (!stage || !canvas) return null;
      var g = canvas.getContext('2d');
      var state = ctx.state || 'final';
      var disposed = false, raf = 0, dpr = 1;
      var started = performance.now();
      var v = '20260920f';
      var manifest = {
        logo: ['logo/frame-0.png','logo/frame-1.png','logo/frame-2.png','logo/frame-3.png'],
        fox: [], sheep: [], duo: [],
        pills: ['orbs/blue-pill.png','orbs/green-pill.png'],
        orbs: ['orbs/orb-pair.png','orbs/orb-pair-stands.png'],
        foxOrb: ['characters/fox-with-orb.png'],
        sheepOrb: ['characters/sheep-with-orb.png'],
        duoFinal: ['characters/duo-final.png']
      };
      for (var n = 0; n < 8; n++) {
        manifest.fox.push('frames/fox/frame-' + n + '.png');
        manifest.sheep.push('frames/sheep/frame-' + n + '.png');
        manifest.duo.push('frames/duo/frame-' + n + '.png');
      }
      var images = {};
      var loadCount = 0, total = 0;
      function resize() {
        var r = stage.getBoundingClientRect();
        dpr = Math.min(window.devicePixelRatio || 1, 2);
        canvas.width = Math.max(1, Math.round(r.width * dpr));
        canvas.height = Math.max(1, Math.round(r.height * dpr));
        canvas.style.width = r.width + 'px';
        canvas.style.height = r.height + 'px';
        g.setTransform(dpr, 0, 0, dpr, 0, 0);
      }
      function loadAll() {
        Object.keys(manifest).forEach(function (group) {
          images[group] = [];
          manifest[group].forEach(function (path, i) {
            total++;
            var img = new Image();
            img.onload = function () { loadCount++; };
            img.src = 'assets/real/splash-generated/' + path + '?v=' + v;
            images[group][i] = img;
          });
        });
      }
      function img(group, i) {
        var list = images[group] || [];
        return list[Math.max(0, Math.min(list.length - 1, i))];
      }
      function ease(t) {
        return t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      }
      function fit(source, x, y, w, h, alpha) {
        if (!source || !source.naturalWidth) return;
        var s = Math.min(w / source.naturalWidth, h / source.naturalHeight);
        var dw = source.naturalWidth * s, dh = source.naturalHeight * s;
        g.globalAlpha = alpha == null ? 1 : alpha;
        g.drawImage(source, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh);
        g.globalAlpha = 1;
      }
      function cross(p) {
        return Math.max(0, Math.min(1, p < .5 ? p * 2 : (1 - p) * 2));
      }
      function drawLogo(t, w, h) {
        var p = Math.min(1, t / 2200);
        var i = Math.min(3, Math.floor(p * 4));
        fit(img('logo', i), w * .12, h * .28, w * .76, h * .22, 1);
      }
      function drawPills(t, w, h) {
        var p = Math.max(0, Math.min(1, (t - 1900) / 1100));
        var q = ease(p);
        var size = Math.min(120, w * .28);
        fit(img('pills', 0), w * .16 - (1 - q) * 55, h * .43, size, size * .48, p);
        fit(img('pills', 1), w * .56 + (1 - q) * 55, h * .43, size, size * .48, p);
      }
      function drawOrbs(t, w, h) {
        var p = Math.max(0, Math.min(1, (t - 2800) / 1300));
        var q = ease(p);
        fit(img('orbs', p < .58 ? 0 : 1), w * .16, h * .40 - q * 5, w * .68, h * .25, p);
      }
      function drawOrbCharacters(t, w, h) {
        var p = Math.max(0, Math.min(1, (t - 3900) / 1500));
        var q = ease(p);
        var size = Math.min(165, w * .43);
        fit(img('foxOrb', 0), -size * .62 + q * (w * .18), h * .48, size, size * .62, p);
        fit(img('sheepOrb', 0), w - size * .38 - q * (w * .18), h * .48, size, size * .62, p);
      }
      function drawActors(t, w, h) {
        var p = Math.max(0, Math.min(1, (t - 5000) / 1900));
        var q = ease(p);
        var i = Math.min(7, Math.floor(p * 8));
        var size = Math.min(155, w * .39);
        fit(img('fox', i), -size * .65 + q * (w * .43), h * .42, size, size, 1);
        fit(img('sheep', i), w - size * .35 - q * (w * .43), h * .42, size, size, 1);
      }
      function drawDuo(t, w, h) {
        var p = Math.max(0, Math.min(1, (t - 6800) / 1900));
        var i = Math.min(7, Math.floor(p * 8));
        fit(img('duo', i), w * .08, h * .43, w * .84, h * .30, Math.min(1, p * 4));
      }
      function draw(now) {
        if (disposed) return;
        var r = stage.getBoundingClientRect(), w = r.width, h = r.height;
        if (!canvas.width || canvas.width !== Math.round(w * dpr)) resize();
        g.clearRect(0, 0, w, h);
        g.fillStyle = '#fff';
        g.fillRect(0, 0, w, h);
        var t = now - started;
        if (state === 'intro') drawLogo(800, w, h);
        else if (state === 'final') fit(img('duoFinal', 0), w * .08, h * .42, w * .84, h * .32, 1);
        else {
          drawLogo(t, w, h);
          drawPills(t, w, h);
          drawOrbs(t, w, h);
          drawOrbCharacters(t, w, h);
          drawActors(t, w, h);
          drawDuo(t, w, h);
        }
        raf = requestAnimationFrame(draw);
      }
      resize();
      loadAll();
      window.addEventListener('resize', resize);
      raf = requestAnimationFrame(draw);
      return function () {
        disposed = true;
        cancelAnimationFrame(raf);
        window.removeEventListener('resize', resize);
      };
    }
  });

  /* =====================================================================
     02 设备连接页
     ===================================================================== */
  var CONNECT_STATES = [
    { key: 'idle',               label: '等待输入' },
    { key: 'incomplete',         label: '输入不完整' },
    { key: 'connecting',         label: '正在连接' },
    { key: 'success',            label: '连接成功' },
    { key: 'code-error',         label: '配对码错误' },
    { key: 'key-error',          label: 'Key 错误' },
    { key: 'network-error',      label: '网络错误' },
    { key: 'device-unavailable', label: '设备不可用' },
    { key: 'advanced',           label: '高级设置展开' }
  ];

  K.registerScreen({
    no: '02', id: 'connect', name: '设备连接页', route: '#/connect', tab: null,
    purpose: '填写配对码与 Key 完成设备连接，覆盖 8 种输入/连接状态。',
    out: ['#/welcome', '#/connect/success', '#/device'],
    states: CONNECT_STATES,
    render: function (ctx) {
      var s = ctx.state || 'idle';
      var filled = ['connecting', 'key-error', 'network-error', 'device-unavailable', 'success'].indexOf(s) >= 0;
      var plain = (s === 'idle' || s === 'advanced');
      var codeVal = filled ? 'KS-7391' : (plain ? '' : 'KS-739');
      var keyVal  = filled ? '••••••••••••4f2a' : '';
      var codeErr = s === 'code-error' ? '配对码错误，请重新核对设备上显示的 6 位配对码' : '';
      var keyErr  = s === 'key-error' ? 'Key 校验失败，请确认设备 Key 是否已更新' : '';
      var incErr  = s === 'incomplete' ? '请填写完整的配对码与 Key' : '';
      var connecting = s === 'connecting';
      var ok = s === 'success';

      var topBanner = '';
      if (s === 'network-error') {
        topBanner = banner({ icon: 'wifioff', kind: 'warn', title: '网络错误',
          body: '无法访问服务器地址，请检查网络或服务器地址是否正确。',
          action: { label: '重试', action: 'connect' } });
      } else if (s === 'device-unavailable') {
        topBanner = banner({ icon: 'alert', kind: 'warn', title: '设备不可用',
          body: '该设备当前不可达或已被其他连接占用。',
          action: { label: '重新连接', action: 'connect' } });
      } else if (ok) {
        topBanner = banner({ icon: 'check', kind: 'ok', title: '连接成功',
          body: '已与 Kissne 设备建立连接。',
          action: { label: '下一步', to: '#/connect/success' } });
      }

      var foot = ok
        ? btn('进入聊天', { to: '#/chat', block: true, kind: 'primary' })
          + btn('管理设备', { to: '#/device', block: true, kind: 'ghost' })
        : btn(connecting ? '正在连接…' : '连接设备', {
            block: true, kind: 'primary', action: 'connect',
            disabled: connecting, icon: connecting ? 'sync' : undefined
          })
          + (connecting ? '<div class="hintline">' + icon('sync', 14) + '<span>正在与设备握手，请勿关闭页面…</span></div>' : '');

      /* 高级设置展开态：单独一个状态位，方便逐项核对展开后的内容 */
      var advOpen = s === 'advanced';

      return `
      <div class="screen">
        ${appbar({ title: '设备连接', sub: '连接一台 Kissne 设备', back: '#/welcome' })}
        <div class="screen__body">
          ${topBanner}
          ${note('低保真原型：输入框不可编辑，不实现真实配对逻辑。')}
          ${field({ label: '配对码', required: true, value: codeVal, placeholder: '6 位配对码',
                    error: codeErr || incErr,
                    hint: '请在 Kissne 设备或电脑端查看配对码。' })}
          ${field({ label: 'Key', required: true, value: keyVal, placeholder: '设备 Key', error: keyErr })}
          ${field({ label: '服务器地址', value: filled ? '192.168.1.24:8420' : '', placeholder: 'host:port',
                    hint: '局域网直连时留空将自动发现设备' })}
          <details class="adv"${advOpen ? ' open' : ''}>
            <summary>${icon('gear', 16)}<span>高级设置</span>${icon('chevron', 16)}</summary>
            <div class="adv__body">
              ${field({ label: '连接超时（秒）', value: '10' })}
              ${field({ label: '使用加密通道', value: '开启' })}
              ${field({ label: '断线自动重连', value: '开启' })}
              ${field({ label: '连接方式', value: '局域网直连' })}
            </div>
          </details>
        </div>
        <div class="screen__foot">${foot}</div>
      </div>`;
    },

    mount: function (root) {
      var T = window.KissneTransport;
      if (!T) return null;
      var inputs = root.querySelectorAll('.field__input');
      if (inputs.length < 3) return null;
      var code = inputs[0], key = inputs[1], address = inputs[2];
      code.readOnly = false;
      key.readOnly = false;
      address.readOnly = false;
      code.value = '';
      key.value = T.sessionKey() || '';
      address.value = T.base() || '';

      var action = root.querySelector('[data-action="connect"]');
      if (!action) return null;

      async function onConnect(e) {
        e.preventDefault();
        e.stopPropagation();
        var pairingCode = (code.value || '').trim();
        var sessionKey = (key.value || '').trim();
        var apiBase = (address.value || '').trim();
        if (!pairingCode || !sessionKey) {
          (pairingCode ? key : code).focus();
          return;
        }
        action.disabled = true;
        try {
          T.setSessionKey(sessionKey);
          if (apiBase) T.setBase(apiBase);
          var paired = await T.pair({ pairingCode: pairingCode, sessionKey: sessionKey, apiBase: apiBase });
          if (!paired || !paired.device_token) throw new Error('pairing_failed');
          var boot = await T.bootstrap();
          location.hash = boot && boot.bound ? '#/connect?state=success' : '#/connect?state=key-error';
        } catch (err) {
          var name = err && err.payload && err.payload.error;
          if (name === 'invalid_pairing_code' || name === 'pairing_code_expired' || name === 'pairing_code_replayed') {
            location.hash = '#/connect?state=code-error';
          } else if (name === 'conversation_not_bound' || name === 'installation_not_bound_to_a_runtime_conversation') {
            location.hash = '#/connect?state=key-error';
          } else {
            location.hash = '#/connect?state=network-error';
          }
        } finally {
          action.disabled = false;
        }
      }
      action.addEventListener('click', onConnect);
      return function () { action.removeEventListener('click', onConnect); };
    }
  });

  /* =====================================================================
     03 连接成功页
     ===================================================================== */
  K.registerScreen({
    no: '03', id: 'connect-success', name: '连接成功页', route: '#/connect/success', tab: null,
    purpose: '确认设备已连接，展示设备名称 / 在线状态 / 当前模型 / 最近同步时间。',
    out: ['#/home', '#/chat', '#/device'],
    states: [{ key: 'default', label: '默认' }],
    render: function () {
      return `
      <div class="screen">
        ${appbar({ title: '连接成功', back: '#/home' })}
        <div class="screen__body screen__body--center">
          <div class="succ__hero">${ph('CONNECTION_SUCCESS_ILLUSTRATION', { size: 112 })}</div>
          <div class="succ__head">
            <h2 class="succ__title">设备已连接</h2>
            <p class="succ__sub">Kissne 已与你的设备建立连接。</p>
          </div>
          ${card(
            kv('设备名称', '人人星')
            + kv('在线状态', chip('在线', 'ok'))
            + kv('当前模型', 'MiMo v2.5')
            + kv('最近同步时间', '刚刚')
          )}
          ${note('配对成功后，设备信息由系统自动返回。')}
        </div>
        <div class="screen__foot">
          ${btn('进入聊天', { to: '#/chat', block: true, kind: 'primary' })}
          ${btn('管理设备', { to: '#/device', block: true, kind: 'ghost' })}
        </div>
      </div>`;
    }
  });

  /* =====================================================================
     04 首页 / 控制台
     ===================================================================== */
  /* 首页两张星卡用的是**整幅插画**（自带背景），白天 / 夜晚各一版。
     默认按本机时间自动切（6:00–18:00 算白天）；day / night 两个状态是给review用的强制开关。 */
  var HOME_STATES = [
    { key: 'online',  label: '设备在线（昼 / 夜按本机时间自动）' },
    { key: 'day',     label: '白天外观（强制）' },
    { key: 'night',   label: '夜晚外观（强制）' },
    { key: 'offline', label: '设备离线' }
  ];
  function dayPart(ctx) {
    if (ctx.state === 'day' || ctx.state === 'night') return ctx.state;
    var h = new Date().getHours();
    return (h >= 6 && h < 18) ? 'day' : 'night';
  }

  K.registerScreen({
    no: '04', id: 'home', name: '首页 / 控制台', route: '#/home', tab: 'entry',
    purpose: '手机桌面式入口页。最上方左侧「人人星」（小羊素材）→ 聊天页，右侧「小机星」（叶青栩素材）→ AI World；两张星卡是整幅插画，白天 / 夜晚各一版，按本机时间自动切。其余功能以手机桌面式图标网格排列。只有桌面内容，不做列表式的最近活动。白蓝配色。',
    out: ['#/chat', '#/universe', '#/memory', '#/device', '#/settings', '#/connect', '#/notifications', '#/assets'],
    states: HOME_STATES,
    render: function (ctx) {
      var offline = ctx.state === 'offline';
      var part = dayPart(ctx);        /* 'day' | 'night' —— 星卡插画用哪一版 */

      var head = `
        <header class="appbar appbar--brand">
          <div class="appbar__l"><span class="brand">Kissne</span></div>
          <div class="appbar__c"></div>
          <div class="appbar__r">
            <button class="iconbtn" data-nav="#/notifications" aria-label="通知">${icon('bell')}</button>
            <button class="iconbtn" data-nav="#/settings" aria-label="设置">${icon('gear')}</button>
          </div>
        </header>`;

      /* —— 最上方：人人星 ｜ 小机星，左右各占一半，整幅插画素材 —— */
      /* 两张星卡**只有素材**：不放名称、不放箭头、也不再加爪印/蹄印那些提示 ——
         素材本身就是辨认依据（左边小羊 = 人人星，右边叶青栩 = 小机星），点素材进对应页面。
         插画白天/夜晚各一版，用 part 决定（见 dayPart）。 */
      var stars = `
        <div class="starcards">
          <div class="starcard starcard--sheep${offline ? ' is-disabled' : ''}"${offline ? '' : ' data-nav="#/chat"'}>
            <div class="starcard__art">
              ${ph('SHEEP_CHARACTER_RESERVED', { state: part })}
            </div>
          </div>
          <div class="starcard" data-nav="#/universe">
            <div class="starcard__art">
              ${ph('FOX_HOME_CHARACTER', { state: part })}
            </div>
          </div>
        </div>`;

      var devstrip = `
        <div class="devstrip">
          <span class="devstrip__ic">${icon('server', 18)}</span>
          <span class="devstrip__main">
            <span class="devstrip__t">当前设备 ${chip(offline ? '离线' : '在线', offline ? 'warn' : 'solid')}</span>
            <span class="devstrip__s">人人星 · MiMo v2.5</span>
          </span>
          ${offline ? btn('重连', { small: true, kind: 'ghost', to: '#/connect?state=connecting' }) : ''}
        </div>`;

      var offlineBlock = offline
        ? '<div class="offline">'
          +   ph('OFFLINE_ILLUSTRATION', { size: 104 })
          +   '<div class="offline__title">设备已离线</div>'
          +   '<div class="offline__sub">聊天与记忆同步暂时不可用，请先重新连接设备。</div>'
          + '</div>'
        : '';

      /* —— 其余功能：手机桌面式小图标网格 —— */
      var APPS = [
        { t: '记忆库',   ic: 'memory', to: '#/memory' },
        { t: '设备管理', ic: 'plug',   to: '#/device' },
        { t: '连接设置', ic: 'link',   to: '#/connect' },
        { t: '模型设置', ic: 'cpu',    to: '#/settings' },
        { t: '通知',     ic: 'bell',   to: '#/notifications' },
        { t: '设置',     ic: 'gear',   to: '#/settings' },
        { t: '表情包',   ic: 'smile',  to: '#/stickers' },
        { t: '关于',     ic: 'info',   to: '#/settings' },
        /* 以下 4 项为功能占位：本阶段只摆位置、不定功能细节 */
        { t: '语音设置', ic: 'mic',    to: '#/settings' },
        { t: '对话记录', ic: 'clock',  to: '#/chat' },
        { t: '账号安全', ic: 'user',   to: '#/settings' },
        { t: '数据备份', ic: 'refresh', to: '#/settings' }
      ];
      var appgrid = '<div class="appgrid">' + APPS.map(function (a) {
        return '<a class="appgrid__item" data-nav="' + a.to + '">'
          + '<span class="appgrid__ic">' + icon(a.ic, 21) + '</span>'
          + '<span class="appgrid__label">' + a.t + '</span></a>';
      }).join('') + '</div>';

      return `
      <div class="screen screen--home">
        ${head}
        <div class="screen__body">
          ${stars}
          ${devstrip}
          ${offlineBlock}
          ${sectionTitle('全部功能')}
          ${appgrid}
          <div class="motifrow">${icon('paw', 15)}${icon('hoof', 15)}${icon('paw', 15)}</div>
          ${offline ? note('设备离线时「人人星」不可进入，避免误以为仍可聊天。') : ''}
        </div>
      </div>`;
    }
  });

  /* =====================================================================
     05 聊天页
     ===================================================================== */
  var CHAT_STATES = [
    /* **第一个 = 默认状态**：必须是"有对话"的那个。
       之前第一项是"空聊天"，于是 `#/chat`（不带 state）永远显示"还没有消息"，
       从通话页挂断回来就以为"记录全没了"。空态现在只能从侧栏手动切。 */
    { key: 'normal',        label: '默认对话' },
    { key: 'empty',         label: '空聊天' },
    { key: 'keyboard',      label: '键盘弹出（打字中）' },
    { key: 'unread',        label: '有未读消息（示例）' },
    { key: 'search',        label: '历史搜索' },
    { key: 'sending',       label: '消息发送中' },
    { key: 'typing',        label: '正在输入' },
    { key: 'thinking',      label: '正在思考' },
    { key: 'replying',      label: '正在回复' },
    { key: 'failed',        label: '回复失败' },
    { key: 'device-offline',label: '设备离线' },
    { key: 'network-lost',  label: '网络断开' },
    { key: 'cot',           label: '思考链（示例）' },
    { key: 'tool',          label: '工具调用 · 记忆检索（示例）' },
    { key: 'tool-web',      label: '工具调用 · 联网搜索（示例）' },
    { key: 'tool-cal',      label: '工具调用 · 看日程（示例）' },
    { key: 'tool-write',    label: '工具调用 · 写备忘录（示例）' },
    { key: 'request-enter', label: '小机星进入请示' },
    { key: 'plus-menu',     label: '「+」菜单展开' },
    { key: 'model-menu',    label: '模型下拉展开' },
    { key: 'effort-menu',   label: '思考强度下拉展开' }
  ];

  /* —— 模型 / 思考强度：可切换项 ——
     真实列表由 Hermes 返回（自带模型供应商与思考强度档位），
     本阶段按占位示例摆放：模型名用 Hermes 风格的示例名（非真实模型表），
     真实列表由 Hermes 返回后整体替换。 */
  /* Runtime is the source of truth. These are offline-only fallbacks, never a model catalog. */
  var MODELS = [{ k: 'auto', v: '自动', d: '跟随 Hermes 当前模型' }];
  var EFFORTS = [{ k: 'auto', v: '自动', d: '跟随 Hermes 当前设置' }];
  var MODEL_OPTIONS_LOADING = false;
  function refreshModelOptions() {
    var T = window.KissneTransport;
    if (!T || !T.hasToken || !T.hasToken() || MODEL_OPTIONS_LOADING) return;
    MODEL_OPTIONS_LOADING = true;
    T.modelOptions().then(function (data) {
      MODELS = [{ k: 'auto', v: '自动', d: '跟随 Hermes 当前模型' }].concat(
        (data.models || []).map(function (m) {
          return { k: m.provider + '/' + m.model, v: m.label || m.model, d: m.provider_label || m.provider || '' };
        }));
      EFFORTS = [{ k: 'auto', v: '自动', d: '跟随 Hermes 当前设置' }].concat(
        (data.efforts || []).map(function (e) {
          return { k: e.value, v: e.label || e.value, d: '' };
        }));
      try {
        sessionStorage.setItem('kissne.current_model', data.current_model || 'auto');
        sessionStorage.setItem('kissne.current_effort', data.current_effort || 'auto');
      } catch (e) {}
      if ((location.hash || '').indexOf('#/chat') === 0) window.dispatchEvent(new HashChangeEvent('hashchange'));
    }).catch(function () {
      /* Offline: keep only Auto; do not pretend stale hard-coded models are available. */
    }).finally(function () { MODEL_OPTIONS_LOADING = false; });
  }
  function pick(list, key, fallback) {
    for (var i = 0; i < list.length; i++) { if (list[i].k === key) return list[i]; }
    for (var j = 0; j < list.length; j++) { if (list[j].k === fallback) return list[j]; }
    return list[0];
  }
  /* 下拉面板：标题 + 若干可选项 + 底部说明
     origin = 从哪个状态点开的菜单，选中后回到那个状态，
     否则选完模型会把正在看的对话丢掉、退回空态。
     注意：面板里的值**全部是占位示例**，真实列表由 Hermes 返回，不要当成真实数据。 */
  function dropdown(title, items, curKey, param, origin) {
    return '<div class="dd">'
      + '<div class="dd__head"><span>' + esc(title) + '</span>'
      + '</div>'
      + '<div class="dd__list">' + items.map(function (it) {
          return '<a class="dd__item' + (it.k === curKey ? ' is-active' : '') + '"'
            + ' href="#/chat?state=' + origin + '&' + param + '=' + encodeURIComponent(it.k) + '"'
            + ' data-model-choice="' + param + '" data-model-value="' + esc(it.k) + '">'
            + '<span class="dd__main"><span class="dd__v">' + esc(it.v) + '</span>'
            + '<span class="dd__d">' + esc(it.d) + '</span></span>'
            + (it.k === curKey ? icon('check', 16) : '') + '</a>';
        }).join('') + '</div>'
      + '</div>';
  }

  /* 「+」点开后的浮层：**紧贴加号上方**弹出的小框（不是从屏幕底端滑上来的面板）。
     只剩照片 / 文件两个占位入口 —— 表情包 / 语音通话 / 屏幕共享已移到
     输入框上方的磁吸快捷条（.quickbar），不再藏在「＋」里。 */
  function plusPopLayer(origin) {
    var items = [
      { ic: 'image', t: '照片',        d: '从相册选择图片', action: 'pick-image' },
      { ic: 'file',  t: '文件',        d: '发送 PDF / 文本 / CSV / JSON / ZIP', action: 'pick-file' }
    ];
    return '<div class="pop">'
      + items.map(function (it) {
          return '<button class="pop__item" type="button" data-chat-action="' + it.action + '">'
            + '<span class="pop__ic">' + icon(it.ic, 17) + '</span>'
            + '<span class="pop__main"><span class="pop__t">' + esc(it.t) + '</span>'
            + '<span class="pop__d">' + esc(it.d) + '</span></span></button>';
        }).join('')
      + '</div>';
  }

  /* 消息两侧都带头像：AI 一侧是叶青栩的头像，我这一侧是用户头像。
     每条消息都带时间戳 —— 真实聊天不可能没有时间。

     **叶青栩的头像不是一张固定图，而是跟着状态换的** —— 思考一张、开心一张、
     没听懂一张……换图只改 <img> 的 src（K.swapAsset），消息结构不动。
     素材放在 assets/_inbox/，命名 = fox-chat-avatar-<state>.png；缺哪个状态
     就自动回落到 fox-chat-avatar.png（平静），所以少给几张也不会破。

     **tag** 只是占位盒上的一行小字（真素材上线后基本看不见），保留是为了
     占位阶段还能读懂这一步在干嘛。 */
  var AVA_STATES = {
    idle:     '平静',        /* 兜底：普通消息、闲着 */
    think:    '思考中',      /* 托腮 + 问号泡泡 */
    work:     '干活中',      /* 手忙脚乱那张（暂无正脸"在忙"素材，先借它） */
    talk:     '说话',        /* 平静微笑，正好也是兜底图 */
    happy:    '开心',        /* 大笑 */
    confused: '没听懂',      /* 问号（词表里留着，等页面用得上再接） */
    sad:      '委屈 / 出错',
    sleep:    '睡着 / 离线',
    panic:    '卡住了'
  };

  function ava(code, tag, state) {
    /* 头像是**透明底**素材，**不切圆形** —— 狐狸耳朵是尖的，切圆会吃掉耳朵和蝴蝶结。
       直接按素材自己的轮廓显示（圆角/底色由 .ph--img 在 CSS 里清掉）。 */
    return '<div class="msg__ava">'
      + ph(code, { size: 34, compact: true, tag: tag || '头像', state: state })
      + '</div>';
  }
  function aiMsg(html, cls, time, tag, state, ref) {
    return '<div class="msg msg--ai"' + (ref ? ' data-history-ref="' + esc(ref) + '"' : '') + '>' + ava('FOX_CHAT_AVATAR', tag, state)
      + '<div class="msg__body"><div class="msg__text' + (cls ? ' ' + cls : '') + '">' + html + '</div>'
      + '<span class="msg__time">' + (time || '09:41') + '</span></div>'
      + '</div>';
  }
  /* 「我」这一侧：头像是**小羊**（人人星）。
     状态词表和狐狸共用一套（AVA_STATES），缺图自动回落兜底那张平静脸。

     MY_AVA 是**模块级**的当前表情 —— 渲染时按页面状态写一次，meMsg 默认读它，
     省得每个调用点都传一个参数（和 UNREAD / LAST_SENT_HASH 一个路子）：
       设备离线 / 断网 = 人不在 → 睡着；上一条没发出去 → 委屈；其余平静。 */
  var MY_AVA = 'idle';
  var MSG_SEQ = 0;
  function meMsg(html, meta, time, state, ref) {
    var mid = 'local-msg-' + (++MSG_SEQ);
    return '<div class="msg msg--me" data-msg-id="' + mid + '"' + (ref ? ' data-history-ref="' + esc(ref) + '"' : '') + ' tabindex="0">' + ava('USER_AVATAR', '我', state || MY_AVA)
      + '<div class="msg__body"><div class="bubble">' + html + '</div>'
      + (meta ? '<div class="msg__meta">' + meta + '</div>' : '')
      + '<span class="msg__time">' + (time || '09:41') + '</span></div>'
      + '</div>';
  }
  function dots() { return '<span class="dots"><i></i><i></i><i></i></span>'; }

  /* ============ 思考过程 / 工具调用：一行小字 + 一条装饰分割线 ============
     两者**同一个组件**（.tlog）：没有气泡、没有底色，字号 12px（比正文小一号），
     平时收起、点一下展开。收起后每条下面压一条分割线 —— 「思考 + 工具」正好两根。
     真实思考内容 / 工具参数一律由 Hermes 返回，原型里都是占位。 */
  var TLOG_GLYPH = 'ˋˏ✄ ❤︎ ✄ˏˋ';   /* 分割线中间那枚小符号；想换风格只改这里：
                                        '☆♪ 🤍 ♪☆' / '𐙚 𓏵𓏵𓏵𓏵𐙚' / '⋆｡ﾟ☁︎｡⋆｡ ﾟ☾ ﾟ｡⋆' 都行 */
  function tlogSep() {
    return '<div class="tlog__sep" aria-hidden="true"><i>' + TLOG_GLYPH + '</i></div>';
  }
  function tlogBlock(kind, title, bodyHtml, open) {
    return '<div class="tlog' + (open ? ' is-open' : '') + '" data-tlog-block="' + kind + '">'
      + '<button class="tlog__row" type="button" data-tlog-toggle>'
      + '<span class="tlog__t"' + (kind === 'think' ? ' data-tlog-t' : '') + '>'
      + title + '</span><i class="tlog__car">▼</i></button>'
      + '<div class="tlog__body">' + bodyHtml + '</div>'
      + tlogSep()
      + '</div>';
  }
  /* 思考过程（示例）。opts.head 换标题 —— 演"正在思考…"那一步时用它。 */
  function cotBlock(opts) {
    opts = opts || {};
    var head = opts.head || ('已深度思考 · 用时 ' + (opts.cost || '1.1s'));
    var lines = (opts.lines || []).map(function (l) {
      return '<div class="tlog__line">' + l + '</div>';
    }).join('');
    return tlogBlock('think', head, lines, opts.open);
  }
  /* 工具调用（示例）。status 不传就是"已完成 · 耗时"；演"调用中"那一步时传进来。 */
  function toolCard(name, rows, cost, status, open) {
    var kv = rows.map(function (r) {
      return '<div class="tlog__kv"><span>' + r[0] + '</span><b>' + r[1] + '</b></div>';
    }).join('')
      + '<div class="tlog__kv"><span>状态</span><b data-tool-status>'
      + (status || ('已完成 · ' + (cost || '0.8s'))) + '</b></div>';
    return tlogBlock('tool', '调用工具 · ' + name + '（示例）', kv, open);
  }

  /* —— 聊天记录：**模块级**，切页（含去通话页再回来）都不会丢 ——
     之前消息是每次 render 现拼的，去一次通话页回来就"记录全没了"。 */
  var CHAT_LOG = [];
  function clockNow() {
    var d = new Date();
    return ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2);
  }
  function sysMsg(html, time) {
    return '<div class="msg msg--sys"><div class="msg__sysline">' + html + '</div>'
      + '<span class="msg__time is-center">' + (time || '') + '</span></div>';
  }
  function sessionResetMsg(text, time, ref) {
    return '<div class="msg msg--sys msg--session-reset" data-session-reset'
      + (ref ? ' data-history-ref="' + esc(ref) + '"' : '') + '>'
      + '<div class="msg__sysline"><pre>' + esc(String(text || '')) + '</pre></div>'
      + '<span class="msg__time is-center">' + (time || '') + '</span></div>';
  }
  function quoteCard(ref, text, role) {
    var author = role === 'assistant' ? '叶青栩' : (role === 'system' ? '系统' : '我');
    return '<button type="button" class="msgquote" data-quote-ref="' + esc(String(ref || '')) + '">'
      + '<span class="msgquote__author">' + esc(author) + '</span>'
      + '<span class="msgquote__text">' + esc(String(text || '').replace(/\s+/g, ' ').trim().slice(0, 140) || '引用消息') + '</span>'
      + '</button>';
  }

  function pushLog(m) {
    CHAT_LOG.push(m);
    /* 你没看着的时候进来的 AI 消息 = 未读（记下最早那条，点胶囊要跳过去） */
    if (m.who === 'ai' && !chatAtBottom()) {
      if (!UNREAD.n) UNREAD.first = CHAT_LOG.length - 1;
      UNREAD.n++;
    }
    return m;
  }
  /* —— 未读消息：胶囊 + 底栏角标 ——
     判定"你在看"：路由停在聊天页、且滚动条在最下面。 */
  var UNREAD = { n: 0, first: -1 };
  var UNREAD_SEEDED = false;
  function chatAtBottom() {
    if ((location.hash || '').indexOf('#/chat') !== 0) return false;
    var list = document.querySelector('.chatbody');
    if (!list) return false;
    return list.scrollTop + list.clientHeight >= list.scrollHeight - 8;
  }
  K.unreadBadge = function () { return UNREAD.n; };
  /* 最近一次「通话记录行」写进聊天记录的时间，防止切状态重渲染时重复写 */
  var CALL_LOGGED_AT = 0;
  /* 上一次因表情包而发消息时的 hash，用于去重（避免重渲染重复发） */
  var LAST_SENT_HASH = '';
  /* 历史搜索：像微信的搜索记录那样**按时间线排列**（今天 / 昨天 / 更早）。
     模块级，删除与清空都是真的生效（只在本会话内）。 */
  var SEARCH_LOG = [];
  function rememberSearch(k) {
    k = String(k || '').trim();
    if (!k) return;
    for (var i = SEARCH_LOG.length - 1; i >= 0; i--) {
      if (SEARCH_LOG[i].k === k) SEARCH_LOG.splice(i, 1);
    }
    var d = new Date();
    SEARCH_LOG.unshift({
      k: k,
      t: String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0'),
      g: '今天'
    });
    if (SEARCH_LOG.length > 20) SEARCH_LOG.length = 20;
  }
  function logRender() {
    return CHAT_LOG.map(function (m) {
      if (m.presentation === 'session_reset') return sessionResetMsg(m.text || '', m.time, m.ref);
      if (m.who === 'sys') return sysMsg(m.html, m.time);
      return m.who === 'ai' ? aiMsg(m.html, m.cls || '', m.time, '', '', m.ref) : meMsg(m.html, m.meta || '', m.time, '', m.ref);
    }).join('');
  }

  K.registerScreen({
    no: '05', id: 'chat', name: '人人星', route: '#/chat', tab: 'chat',
    purpose: '核心页面：顶端横排「模型下拉 · 叶青栩 · 思考强度下拉」，两项都可点开下拉切换；下方为消息列表与一条长圆弧输入框。',
    out: ['#/home', '#/connect', '#/device'],
    states: CHAT_STATES,
    render: function (ctx) {
      var s = ctx.state || 'empty';
      var offline = s === 'device-offline';
      var netlost = s === 'network-lost';
      /* 下拉展开态：底下照常显示一段对话，菜单浮在上面 */
      var menu = s === 'model-menu' ? 'model'
               : (s === 'effort-menu' ? 'effort' : (s === 'plus-menu' ? 'plus' : null));
      var bs = menu ? 'normal' : s;   /* 消息列表按这个状态渲染 */
      var typing = s === 'keyboard';  /* 打字态：悬浮的输入区整组抬起（不画键盘，那段高度全透明） */

      /* 「我」这一侧的小羊头像换表情：离线/断网=睡着，上一条没发出去=委屈 */
      MY_AVA = (offline || netlost) ? 'sleep' : (bs === 'failed' ? 'sad' : 'idle');

      /* —— 历史搜索（顶栏右上角放大镜进入）：按时间线排列，可筛选 / 删除 / 清空 —— */
      if (s === 'search') {
        var rows = SEARCH_LOG.map(function (it) {
          return '<div class="srch__row" data-kw="' + esc(it.k) + '"'
            + ' data-nav="#/chat?state=normal&find=' + encodeURIComponent(it.k) + '">'
            + '<span class="srch__ic">' + icon('clock', 13) + '</span>'
            + '<span class="srch__kw">' + esc(it.k) + '</span>'
            + '<span class="srch__t">' + esc(it.t) + '</span>'
            + '<button class="srch__x" type="button" data-delsrch="' + esc(it.k) + '" aria-label="删除这条记录">'
            + icon('close', 12) + '</button></div>';
        }).join('');
        return `
        <div class="screen screen--chat screen--srch">
          <div class="srchbehind" aria-hidden="true">
            <div class="chathead chathead--ghost"></div>
            <div class="chatbody">${logRender()}</div>
          </div>
          <header class="chathead chathead--srch">
            <button class="iconbtn chathead__back" data-nav="#/chat" aria-label="返回">${icon('back')}</button>
            <div class="srchbox">${icon('search', 15)}
              <input class="srchbox__in" type="search" enterkeyhint="search" placeholder="搜索聊天记录" aria-label="搜索聊天记录"></div>
          </header>
          <div class="srchpanel">
            <div class="srch__head"><span>最近搜索</span>
              <button class="srch__clear" type="button" data-clearsrch>${icon('trash', 12)}清空</button></div>
            <div class="srch__list" data-srchlist>${rows || '<div class="srch__empty">输入关键词搜索当前聊天</div>'}</div>
          </div>
        </div>`;
      }
      /* 头部不再放在线状态 chip：离线/断网由下方 banner 表达 */

      /* --- 当前选中的模型 / 思考强度（从查询参数读，选完能立刻反映到头部）--- */
      var q = ctx.params;
      refreshModelOptions();
      var savedModel = 'auto', savedEffort = 'auto';
      try {
        savedModel = sessionStorage.getItem('kissne.current_model') || 'auto';
        savedEffort = sessionStorage.getItem('kissne.current_effort') || 'auto';
      } catch (e) {}
      var curModel  = pick(MODELS,  (q && q.get('model')) || savedModel,  'auto');
      var curEffort = pick(EFFORTS, (q && q.get('effort')) || savedEffort, 'auto');
      /* 菜单是从哪个状态点开的：选中后回到那里（从侧栏直接切到菜单态时兜底到空态） */
      var origin = (q && q.get('from')) || '';
      if (!origin || origin === 'model-menu' || origin === 'effort-menu') {
        origin = menu ? 'empty' : s;
      }

      /* --- 消息列表：来自模块级聊天记录（切页不丢）--- */
      var base = '';
      if (bs !== 'empty' && CHAT_LOG.length) base = logRender();
      if (bs !== 'empty') {
        /* 头像上的 state = 叶青栩此刻的表情（换图），tag 只是占位盒上的小字 */
        if (bs === 'sending')  base += meMsg('今天天气不错', '<span class="msg__meta-in">发送中…</span>', '09:42');
        if (bs === 'typing')   base += aiMsg('正在输入' + dots(), 'is-pending', '09:42', '打字', 'think');
        if (bs === 'thinking') base += aiMsg('正在思考' + dots(), 'is-pending', '09:42', '思考', 'think');
        if (bs === 'replying') base += aiMsg('嗯，我在听——<span class="caret"></span>', '', '09:42', '说话', 'talk');
        if (bs === 'failed') {
          base += aiMsg(icon('alert', 15) + '<span>回复失败，设备未响应。</span>'
            + btn('重新发送', { small: true, kind: 'ghost', action: 'resend' }), 'is-failed', '09:42', '没连上', 'sad');
        }
        /* 思考链（示例）：AI 那**一条**消息里，回复文字上方挂一块思考过程。
           内容与用时都是占位，真实思考由 Hermes 输出。 */
        if (bs === 'cot') {
          base += aiMsg(cotBlock({
              cost: '3.2s',
              lines: [
                '用户在问我有没有在',
                '先简短回应，再主动问一句',
                '语气保持轻松，不啰嗦'
              ]
            }) + '<div>嗯，我在听。今天想做点什么？</div>', '', '09:42', '深思', 'think');
        }
        /* —— 工具调用（示例）四个例子 ——
           **一个回合 = 一条消息**：思考链 + 工具卡片 + 回复都在同一条里，
           所以头像只有一个，文字会随动作变（记忆 / 联网 / 日程 / 便签）。
           参数与返回值都是占位，真实调用由 Hermes 工具链完成。 */
        if (bs === 'tool') {
          base += aiMsg(cotBlock({ cost: '0.9s', lines: [
                '用户在问周末计划',
                '记忆库里应该有 —— 先检索一遍',
                '取回最近那条「周末计划」'
              ] })
            + toolCard('记忆检索', [
                ['参数', '关键词 = 「周末计划」'],
                ['返回', '待接入 · 由 Hermes 工具返回']
              ], '0.8s')
            + '<div>找到了，你之前提过周末想整理房间——这就要开始吗？</div>', '', '09:42', '记忆', 'work');
        }
        if (bs === 'tool-web') {
          base += aiMsg(cotBlock({ cost: '1.6s', lines: [
                '用户问周末适不适合出门',
                '这得看天气 —— 我不能凭印象猜',
                '先联网查一下这两天的天气'
              ] })
            + toolCard('联网搜索', [
                ['参数', '关键词 = 「周末 天气」'],
                ['返回', '待接入 · 由 Hermes 工具返回']
              ], '1.2s')
            + '<div>我查了：周六晴、周日下午有雨——「看展」放周六更合适。</div>', '', '09:43', '联网', 'work');
        }
        if (bs === 'tool-cal') {
          base += aiMsg(cotBlock({ cost: '1.1s', lines: [
                '用户想约这周末',
                '得先知道他哪段是空的',
                '看一下周六、周日的日程'
              ] })
            + toolCard('查看日程', [
                ['参数', '范围 = 本周六 ～ 周日'],
                ['返回', '待接入 · 由 Hermes 工具返回']
              ], '0.4s')
            + '<div>你周六上午空着。要我先把「美术馆」占上吗？</div>', '', '09:43', '日程', 'work');
        }
        if (bs === 'tool-write') {
          base += aiMsg(cotBlock({ cost: '1.0s', lines: [
                '用户要记一件事',
                '写成备忘比留在聊天里靠谱',
                '写完让他确认一下'
              ] })
            + toolCard('写备忘录', [
                ['内容', '「周六去看展」'],
                ['结果', '待写入 · 需你确认（待接入）']
              ], '0.6s')
            + '<div>写好了，放在备忘录第一条。要改随时说。</div>', '', '09:43', '便签', 'work');
        }
        /* 小机星进入请示：人类不能自己闯进小机星，得先在人人星跟叶青栩打招呼。
           批准后才会出现绿色小人 + 方向键（见 06 小机星页的 state=enter）。 */
        if (bs === 'request-enter') {
          base += aiMsg('你想来小机星看看？可以，我开门给你。', '', '09:42', '开门', 'happy');
        }
      }

      var emptyBlock = bs === 'empty'
        ? '<div class="chatempty">'
          + ph('FOX_STATE_EMOTION', { size: 132 })
          + '<div class="chatempty__t">还没有消息</div>'
          + '<div class="chatempty__s">发一条消息，开始和叶青栩对话。</div>'
          + '</div>'
        : '';

      var topBanner = '';
      if (offline) {
        topBanner = '<div class="chatbanner">'
          + ph('OFFLINE_ILLUSTRATION', { size: 78 })
          + '<div class="chatbanner__main"><b>设备已离线</b><span>无法发送消息，请重新连接设备。</span></div>'
          + btn('重新连接', { small: true, kind: 'ghost', to: '#/connect?state=connecting' })
          + '</div>';
      } else if (netlost) {
        topBanner = banner({ kind: 'warn', icon: 'wifioff', title: '网络已断开',
          body: '消息将在网络恢复后重试。', action: { label: '重试', action: 'resend' } });
      }

      /* 底部：一条长圆弧输入框。
         顺序：加号在左；语音紧挨着发送、在发送左边；三者都嵌在框内且背景透明。
         「+」的浮层**挂在输入框内部**，以加号为锚点向上弹（.composer 要 position:relative）。 */
      var dis = (offline || netlost) ? ' disabled' : '';
      /* 表情面板：**内嵌在聊天页里**（只占两排、横向可滚），不是整屏页面 ——
         点了「表情包」不跳页、不遮住消息。 */
      var panel = (q && q.get('panel')) || '';
      var stkPanel = panel === 'sticker' ? '<div class="stkpanel">'
        + '<div class="stkpanel__grid">'
        + STICKERS.map(function (s) {
            return '<button class="stkpanel__i" type="button" data-stk="' + s.k + '"'
              + ' title="' + esc(s.label) + '" aria-label="' + esc(s.label) + '">'
              + K.sticker(s.k, { alt: s.label }) + '</button>';
          }).join('')
        + '</div>'
        + '<div class="stkpanel__foot"><span>' + STICKERS.length + ' 张 · 两排 · 左右滑动看更多</span>'
        + '<a class="stkpanel__more" data-nav="#/stickers">管理表情包</a></div>'
        + '</div>' : '';
      /* 输入栏上方的**磁吸快捷条**：表情包 / 语音通话 / 屏幕共享。
         表情包是**开关**：点开在输入栏上方长出面板，再点收起。 */
      var quickbar = (offline || netlost) ? '' : '<div class="quickbar">'
        + '<button class="qbtn' + (panel === 'sticker' ? ' is-on' : '') + '"'
        + ' data-nav="#/chat?state=' + origin + (panel === 'sticker' ? '' : '&panel=sticker') + '">'
        + icon('smile', 13) + '<span>表情包</span></button>'
        + '<button class="qbtn" data-nav="#/call">' + icon('call', 13) + '<span>语音通话</span></button>'
        + '<button class="qbtn" data-nav="#/call?state=share">' + icon('screen', 13) + '<span>屏幕共享</span></button>'
        + '</div>';
      var popLayer = (menu === 'plus' && !offline && !netlost) ? plusPopLayer(origin) : '';
      var composer = '<div class="composer' + ((offline || netlost) ? ' is-disabled' : '') + '">'
        + popLayer
        + '<button class="composer__btn"' + dis + ' aria-label="添加"'
        + ((offline || netlost) ? '' : ' data-nav="#/chat?state=plus-menu&from=' + origin + '"')
        + '>' + icon('plus', 19) + '</button>'
        + '<input class="composer__input" type="text" aria-label="输入消息"'
        + ((offline || netlost) ? ' disabled' : '')
        + ' placeholder="' + (offline ? '设备离线，无法发送' : (netlost ? '网络已断开' : '说点什么…')) + '">'
        + '<button class="composer__btn composer__btn--mic"' + dis + ' aria-label="语音输入">' + icon('mic', 19) + '</button>'
        + '<button class="sendbtn"' + dis + ' aria-label="发送">' + icon('send', 18) + '</button>'
        + '<input class="chat-image-picker" type="file" accept="image/jpeg,image/png,image/webp,image/gif" multiple hidden>'
        + '<input class="chat-file-picker" type="file" accept=".pdf,.txt,.md,.csv,.json,.zip,application/pdf,text/plain,text/markdown,text/csv,application/json,application/zip" multiple hidden>'
        + '</div>';

      /* 浮层/下拉展开时的遮罩：点一下收回。加号的浮层已挂在输入框里，这里只放遮罩；
         模型 / 思考强度的下拉面板仍从这里渲染（它们锚在顶栏下方）。 */
      var menuLayer = menu === 'plus'
        ? '<div class="menuscrim" data-nav="#/chat?state=' + origin + '"></div>'
        : menu
        ? '<div class="menuscrim" data-nav="#/chat?state=' + origin + '"></div>'
          + (menu === 'model' ? dropdown('模型', MODELS, curModel.k, 'model', origin)
             : dropdown('思考强度', EFFORTS, curEffort.k, 'effort', origin))
        : '';

      return `
      <div class="screen screen--chat${typing ? ' is-typing' : ''}">
        <!-- 顶端：左=叶青栩，中=模型 / 思考强度（都可点开下拉，列表由 Hermes 提供）。
             不放头像与右上角表情。字号刻意压小，不要抢消息区的视觉。 -->
        <header class="chathead">
          <button class="iconbtn chathead__back" data-nav="#/home" aria-label="返回">${icon('back')}</button>
          <span class="chathead__name">叶青栩</span>
          <!-- 右上角：历史搜索（按时间线排列，见 state=search） -->
          <button class="iconbtn chathead__search" data-nav="#/chat?state=search" aria-label="搜索">${icon('search')}</button>
          <div class="chathead__row">
            <button class="hsel${menu === 'model' ? ' is-open' : ''}" data-nav="#/chat?state=model-menu&from=${origin}">
              <span class="hsel__k">模型</span><span class="hsel__v">${esc(curModel.v)}</span>${icon('chevron', 11, 'hsel__car')}
            </button>
            <button class="hsel${menu === 'effort' ? ' is-open' : ''}" data-nav="#/chat?state=effort-menu&from=${origin}">
              <span class="hsel__k">思考强度</span><span class="hsel__v">${esc(curEffort.v)}</span>${icon('chevron', 11, 'hsel__car')}
            </button>
          </div>
        </header>
        ${topBanner}
        <div class="chatbody">${emptyBlock}${base}</div>
        <!-- 输入区位于聊天页 flex 文档流底部；真机键盘由浏览器 viewport 自然处理。 -->
        <div class="composerwrap">
          <!-- 未读胶囊：浮在输入区上方，点了跳到**最早**那条未读 -->
          <button class="unread" data-unread type="button"${UNREAD.n ? '' : ' hidden'}>
            <span data-unread-n>${UNREAD.n || 0}</span> 条新消息 ↓
          </button>
          ${stkPanel}${quickbar}${composer}</div>
        ${menuLayer}
        ${bs === 'request-enter' ? modal({
          title: '小机星 · 进入请示',
          body: '<p>叶青栩：可以，我开门给你。</p>'
            + '<p class="muted">进来后你会以小人的样子出现在我家里；不来的话，你只能在外面看着我。</p>',
          actions: [
            { label: '批准进入', to: '#/universe?state=enter' },
            { label: '暂不进入', kind: 'ghost', to: '#/chat' }
          ]
        }) : ''}
      </div>`;
    },

    /* 输入框是**真能打字的**：回车或点发送 → 追加一条带头像 + 时间戳的用户气泡（同时写进 CHAT_LOG，
       换页/去通话页回来都还在），随后回一条占位 AI 消息（原型不发起真实请求）。
       从表情包页选了一张也会在这里落成一条消息。 */
    mount: function (root, ctx) {
      /* —— 历史搜索：输入关键词直接搜索当前真实聊天记录 —— */
      var sIn = root.querySelector('input.srchbox__in');
      if (sIn) {
        var listEl = root.querySelector('[data-srchlist]');
        var searchRequestId = 0;
        function renderSearch() {
          if (!listEl) return;
          var qv = (sIn.value || '').trim();
          if (!qv) {
            listEl.innerHTML = SEARCH_LOG.map(function (it) {
              return '<div class="srch__row" data-nav="#/chat?state=normal&find=' + encodeURIComponent(it.k) + '">'
                + '<span class="srch__ic">' + icon('clock', 13) + '</span><span class="srch__kw">' + esc(it.k)
                + '</span><span class="srch__t">' + esc(it.t) + '</span></div>';
            }).join('') || '<div class="srch__empty">输入关键词搜索当前聊天</div>';
            return;
          }
          var T0 = window.KissneTransport;
          if (!T0 || !T0.hasToken || !T0.hasToken()) {
            listEl.innerHTML = '<div class="srch__empty">连接设备后可搜索全部聊天历史</div>';
            return;
          }
          var requestId = ++searchRequestId;
          listEl.innerHTML = '<div class="srch__empty">正在搜索全部聊天历史…</div>';
          T0.searchHistory(qv, 50).then(function (data) {
            if (requestId !== searchRequestId) return;
            var matches = data.results || [];
            listEl.innerHTML = matches.map(function (m) {
              var when = m.created_at ? new Date(m.created_at * 1000).toLocaleString() : '';
              return '<button class="srch__row" type="button" data-nav="#/chat?ref=' + encodeURIComponent(m.message_ref || '') + '">'
                + '<span class="srch__kw">' + esc(String(m.text || '').slice(0, 120)) + '</span>'
                + '<span class="srch__t">' + esc(when) + '</span></button>';
            }).join('') || '<div class="srch__empty">没有找到相关消息</div>';
          }).catch(function () {
            if (requestId === searchRequestId) {
              listEl.innerHTML = '<div class="srch__empty">搜索失败，请检查连接后重试</div>';
            }
          });
        }
        function onSearchKey(e) {
          if (e.key !== 'Enter') return;
          var qv = (sIn.value || '').trim();
          if (!qv) return;
          rememberSearch(qv);
          renderSearch();
        }
        function onClear() { SEARCH_LOG.length = 0; renderSearch(); }
        sIn.addEventListener('input', renderSearch);
        sIn.addEventListener('keydown', onSearchKey);
        var clr = root.querySelector('[data-clearsrch]');
        if (clr) clr.addEventListener('click', onClear);
        return function () {
          sIn.removeEventListener('input', renderSearch);
          sIn.removeEventListener('keydown', onSearchKey);
          if (clr) clr.removeEventListener('click', onClear);
        };
      }

      var input = root.querySelector('input.composer__input');
      var send  = root.querySelector('.sendbtn');
      var list  = root.querySelector('.chatbody');
      if (!input || !send || !list) return null;
      var p = ctx && ctx.params;      /* 放在最前面：下面的 find / sticker 都要用 */

      async function onModelChoice(e) {
        var a = e.target && e.target.closest ? e.target.closest('[data-model-choice]') : null;
        if (!a) return;
        e.preventDefault();
        var kind = a.getAttribute('data-model-choice');
        var value = a.getAttribute('data-model-value') || 'auto';
        var T0 = window.KissneTransport;
        if (!T0 || !T0.hasToken || !T0.hasToken()) { location.hash = '#/connect'; return; }
        var currentModel = 'auto', currentEffort = 'auto';
        try {
          currentModel = sessionStorage.getItem('kissne.current_model') || 'auto';
          currentEffort = sessionStorage.getItem('kissne.current_effort') || 'auto';
        } catch (ignore) {}
        var model = kind === 'model' ? value : currentModel;
        var effort = kind === 'effort' ? value : currentEffort;
        a.classList.add('is-loading');
        try {
          await T0.setModel(model, effort);
          try {
            if (kind === 'model') sessionStorage.setItem('kissne.current_model', value);
            else sessionStorage.setItem('kissne.current_effort', value);
          } catch (ignore2) {}
          var href = a.getAttribute('href');
          if (href) location.hash = href.slice(href.indexOf('#') + 1);
          refreshModelOptions();
        } catch (err) {
          a.classList.remove('is-loading');
          a.setAttribute('title', (err && err.message) || '切换失败');
          if (err && err.status === 401) location.hash = '#/connect';
        }
      }
      root.addEventListener('click', onModelChoice);

      /* 我们自己的"程序化滚动"（打开就到底 / 发完消息 / 点胶囊跳过去）**不算已读**，
         否则一进聊天页就自动把未读清掉了。400ms 内的滚动事件一律忽略。 */
      var scrollGuard = 0;
      function jumpTo(top) {
        scrollGuard = Date.now() + 400;
        list.scrollTop = top;
      }

      /* 打开就停在最新一条（不然记录一长，进来先看到几十条之前的旧消息）。
         用 find 定位进来时不动，交给下面的定位逻辑滚。 */
      var bootT = null;
      if (!(p && (p.get('find') || p.get('ref')))) {
        jumpTo(list.scrollHeight);
        bootT = setTimeout(function () { scrollGuard = Date.now() + 400; list.scrollTop = list.scrollHeight; }, 40);
      }
      function append(html) {
        var emptyEl = list.querySelector('.chatempty');
        if (emptyEl && emptyEl.parentNode) emptyEl.parentNode.removeChild(emptyEl);
        list.insertAdjacentHTML('beforeend', html);
        jumpTo(list.scrollHeight);
      }
      var T = window.KissneTransport;
      var live = !!(T && T.hasToken());
      var liveStopped = false;
      var livePollTimer = null;
      var livePollBusy = false;
      var liveTurns = Object.create(null);
      var liveCompleted = Object.create(null);
      var liveCovered = Object.create(null);
      var liveCurrentTurn = '';
      var composeBatch = [];
      var composeTimer = null;
      var composeBatchStartedAt = 0;
      var COMPOSE_IDLE_MS = 2500;
      var COMPOSE_MAX_WAIT_MS = 15000;
      var liveApprovals = Object.create(null);
      var historyBefore = '';
      var historyHasMore = false;
      var historyLoading = false;
      var pendingReply = null;

      async function flushComposeBatch() {
        clearTimeout(composeTimer);
        composeTimer = null;
        if (!composeBatch.length || !live) return;
        var batch = composeBatch.splice(0);
        var merged = batch.map(function (x) { return x.text; }).join('\n');
        try {
          var accepted = await T.sendMessage({ text: merged, replyTo: batch[0].replyTo || '' }, batch[0].messageId);
          batch.forEach(function (x) {
            if (x.node) { x.node.classList.remove('is-send-pending'); var m=x.node.querySelector('.msg__meta'); if(m)m.textContent=''; }
          });
          liveCurrentTurn = String((accepted && accepted.turn_id) || '');
          if (liveCurrentTurn) {
            var userRef = 'turn:' + liveCurrentTurn + ':user';
            batch.forEach(function (x) {
              if (x.node) x.node.setAttribute('data-history-ref', userRef);
              if (x.logEntry) x.logEntry.ref = userRef;
            });
            liveEnsure(liveCurrentTurn);
            liveSetCancel(true);
          }
          scheduleLivePoll(0);
        } catch (err) {
          batch.forEach(function (x) {
            if (!x.node) return;
            x.node.classList.add('is-send-failed');
            x.node.setAttribute('data-retry-text', x.text);
            var m=x.node.querySelector('.msg__meta');
            if(m)m.innerHTML='<button type="button" class="msgretry" data-retry>发送失败 · 点此重试</button>';
          });
          if (err && err.status === 401) { live=false; location.hash='#/connect'; }
        }
      }
      function scheduleComposeFlush() {
        clearTimeout(composeTimer);
        if (!composeBatch.length) return;
        var elapsed = Date.now() - composeBatchStartedAt;
        if (elapsed >= COMPOSE_MAX_WAIT_MS) { flushComposeBatch(); return; }
        composeTimer = setTimeout(function () {
          if ((input.value || '').trim()) { scheduleComposeFlush(); return; }
          flushComposeBatch();
        }, Math.min(COMPOSE_IDLE_MS, COMPOSE_MAX_WAIT_MS - elapsed));
      }
      function queueComposeText(text, node, reply, logEntry) {
        if (!composeBatch.length) composeBatchStartedAt = Date.now();
        composeBatch.push({
          text:text, node:node, logEntry:logEntry,
          messageId:'kbui_' + Date.now().toString(36) + '_' + composeBatch.length,
          replyTo: reply && reply.ref ? reply.ref : ''
        });
        if (composeBatch.length >= 12) { flushComposeBatch(); return; }
        scheduleComposeFlush();
      }
      function onComposeInput() {
        if (composeBatch.length) scheduleComposeFlush();
      }
      input.addEventListener('input', onComposeInput);

      function historyClock(raw) {
        if (typeof raw !== 'number' || !isFinite(raw)) return '';
        var ms = raw < 100000000000 ? raw * 1000 : raw;
        var d = new Date(ms);
        if (isNaN(d.getTime())) return '';
        return ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2);
      }
      function liveEmpty() {
        return '<div class="chatempty">' + ph('FOX_STATE_EMOTION', { size: 132 })
          + '<div class="chatempty__t">还没有消息</div>'
          + '<div class="chatempty__s">发一条消息，开始和叶青栩对话。</div></div>';
      }
      function historyBody(item) {
        var text = typeof item.text === 'string' ? item.text : '';
        var attachments = Array.isArray(item.attachments) ? item.attachments : [];
        var parts = [];
        if (item.role === 'user' && item.reply_to) {
          var preview = item.reply_preview || {};
          parts.push(quoteCard(item.reply_to, preview.text || '', preview.role || ''));
        }
        if (text.trim()) parts.push(esc(text));
        attachments.forEach(function (a) {
          var kind = String((a && a.type) || '');
          var label = String((a && a.label) || '');
          if (kind === 'sticker') parts.push('<span class="attachment-history attachment-history--sticker">' + icon('smile', 15) + '<span>' + esc(label || '表情包') + '</span></span>');
          else if (kind === 'image') parts.push('<span class="attachment-history attachment-history--image">' + icon('image', 15) + '<span>图片</span></span>');
          else if (kind === 'file') parts.push('<span class="attachment-history attachment-history--file">' + icon('file', 15) + '<span>' + esc(label || '文件') + '</span></span>');
        });
        return parts.join('');
      }
      function historyRowHtml(item) {
        if (!item || !['user', 'assistant', 'system'].includes(item.role)) return '';
        var raw = String(item.text || '');
        if (item.role === 'system' && item.presentation === 'session_reset') {
          return sessionResetMsg(raw, historyClock(item.created_at), item.message_ref || '');
        }
        var body = historyBody(item);
        if (!body) return '';
        return item.role === 'assistant'
          ? aiMsg(body, '', historyClock(item.created_at), '', '', item.message_ref || '')
          : meMsg(body, '', historyClock(item.created_at), '', item.message_ref || '');
      }
      function hydrateHistory(history) {
        CHAT_LOG.length = 0;
        (history || []).forEach(function (item) {
          if (!item || !['user', 'assistant', 'system'].includes(item.role)) return;
          var text = typeof item.text === 'string' ? item.text : '';
          if (item.role === 'system' && item.presentation === 'session_reset') {
            if (!text.trim()) return;
            CHAT_LOG.push({
              who: 'sys', presentation: 'session_reset', text: text,
              time: historyClock(item.created_at), ref: item.message_ref || ''
            });
            return;
          }
          var body = historyBody(item);
          if (!body) return;
          CHAT_LOG.push({
            who: item.role === 'user' ? 'me' : 'ai',
            html: body,
            text: text,
            time: historyClock(item.created_at),
            ref: item.message_ref || '',
            replyTo: item.reply_to || ''
          });
        });
        list.innerHTML = CHAT_LOG.length ? logRender() : liveEmpty();
        jumpTo(list.scrollHeight);
      }
      function liveSetCancel(on) {
        send.setAttribute('data-live-cancel', on ? '1' : '0');
        send.setAttribute('aria-label', on ? '停止回复' : '发送');
        send.innerHTML = on ? icon('close', 18) : icon('send', 18);
      }
      function liveEnsure(turnId) {
        var id = String(turnId || '');
        if (id && liveTurns[id] && liveTurns[id].isConnected) return liveTurns[id];
        append(aiMsg('正在思考' + dots(), 'is-pending', clockNow(), '思考', 'think'));
        var el = list.lastElementChild;
        if (id && el) {
          liveTurns[id] = el;
          el.setAttribute('data-live-turn', id);
        }
        return el;
      }
      function liveAvatar(el, state) {
        if (el) K.swapAsset(el.querySelector('.msg__ava .ph__asset'), 'FOX_CHAT_AVATAR', state);
      }
      function liveText(el, text, pending) {
        if (!el) return;
        var box = el.querySelector('.msg__text');
        if (!box) return;
        box.classList.toggle('is-pending', !!pending);
        box.textContent = String(text || '');
      }
      function renderApproval(event) {
        var id = String(event.approval_id || '');
        if (!id || liveApprovals[id]) return;
        var command = event.tool_input && event.tool_input.command ? String(event.tool_input.command) : '';
        var summary = String(event.summary || '叶青栩需要你的批准才能继续这一步。');
        var wrap = document.createElement('div');
        wrap.className = 'approval-card';
        wrap.setAttribute('data-approval-id', id);
        wrap.innerHTML = '<div class="approval-card__title">需要批准</div>'
          + '<div class="approval-card__summary">' + esc(summary) + '</div>'
          + (command ? '<pre class="approval-card__command">' + esc(command) + '</pre>' : '')
          + '<div class="approval-card__actions">'
          + '<button type="button" data-approval-decision="deny">拒绝</button>'
          + '<button type="button" data-approval-decision="allow" data-approval-scope="once">允许一次</button>'
          + (event.allow_session ? '<button type="button" data-approval-decision="allow" data-approval-scope="session">本次会话允许</button>' : '')
          + (event.allow_permanent ? '<button type="button" data-approval-decision="allow" data-approval-scope="always">始终允许</button>' : '')
          + '</div>';
        list.appendChild(wrap);
        liveApprovals[id] = wrap;
        jumpTo(list.scrollHeight);
      }
      function resolveApprovalCard(event) {
        var id = String(event.approval_id || '');
        var el = liveApprovals[id];
        if (!el) return;
        var decision = String(event.decision || 'resolved');
        el.classList.add('is-resolved');
        var actions = el.querySelector('.approval-card__actions');
        if (actions) actions.innerHTML = '<span>' + esc(decision === 'approved' ? '已允许' : decision === 'expired' ? '已过期' : '已拒绝') + '</span>';
        delete liveApprovals[id];
      }
      async function onApprovalClick(e) {
        var b = e.target.closest('[data-approval-decision]');
        if (!b) return;
        var card = b.closest('[data-approval-id]');
        if (!card || b.disabled) return;
        var buttons = card.querySelectorAll('button');
        buttons.forEach(function (x) { x.disabled = true; });
        try {
          await T.decideApproval(card.getAttribute('data-approval-id'),
            b.getAttribute('data-approval-decision'), b.getAttribute('data-approval-scope') || 'once');
        } catch (err) {
          if (err && (err.status === 404 || err.status === 409)) {
            resolveApprovalCard({approval_id:card.getAttribute('data-approval-id'), decision:'expired'});
          } else {
            buttons.forEach(function (x) { x.disabled = false; });
          }
        }
      }
      list.addEventListener('click', onApprovalClick);

      function applyLiveEvent(event) {
        if (!event || typeof event !== 'object') return;
        var type = String(event.type || '');
        var turnId = String(event.turn_id || '');
        if (type === 'notice') {
          append(sysMsg(esc(event.text || '系统通知'), clockNow()));
          return;
        }
        if (type === 'completed' && event.presentation === 'session_reset') {
          var resetText = String(event.text || '');
          var resetRef = event.notice_id ? 'notice:' + event.notice_id : (event.message_ref || '');
          append(sessionResetMsg(resetText, clockNow(), resetRef));
          CHAT_LOG.push({ who: 'sys', text: resetText, time: clockNow(),
            presentation: 'session_reset', ref: resetRef });
          if (turnId) liveCompleted[turnId] = true;
          if (!turnId || liveCurrentTurn === turnId) { liveCurrentTurn = ''; liveSetCancel(false); }
          return;
        }
        if (type === 'approval_required') { renderApproval(event); return; }
        if (type === 'approval_resolved') { resolveApprovalCard(event); return; }
        var el = liveEnsure(turnId);
        if (type === 'pending') {
          liveText(el, '正在思考…', true);
          liveAvatar(el, 'think');
          liveCurrentTurn = turnId || liveCurrentTurn;
          liveSetCancel(!!liveCurrentTurn);
        } else if (type === 'delta') {
          liveText(el, event.text || '', true);
          liveAvatar(el, 'talk');
          liveCurrentTurn = turnId || liveCurrentTurn;
          liveSetCancel(!!liveCurrentTurn);
        } else if (type === 'completed') {
          var finalText = String(event.text || '');
          var assistantRef = turnId ? ('turn:' + turnId + ':assistant') : String(event.message_ref || '');
          if (el && assistantRef) el.setAttribute('data-history-ref', assistantRef);
          function presentReply(text) {
            var clean = String(text || '').trim();
            if (clean.length > 1800) {
              var paras = clean.split(/\n\s*\n/).filter(Boolean);
              var summary = (paras[0] || clean).slice(0, 320) + ((paras[0] || clean).length > 320 ? '…' : '');
              liveText(el, summary, false);
              var doc = '<button type="button" class="replydoc" data-full-reply="' + encodeURIComponent(clean) + '">'
                + icon('file',15) + '<span><b>完整回复</b><small>' + clean.length + ' 字 · 点击查看</small></span></button>';
              append(aiMsg(doc, '', clockNow(), '', 'happy', assistantRef));
              return;
            }
            var pieces = clean.length <= 420
              ? clean.split(/(?<=[。！？!?])\s*/).filter(Boolean)
              : clean.split(/\n\s*\n/).filter(Boolean);
            if (pieces.length <= 1) { liveText(el, clean, false); return; }
            liveText(el, pieces.shift(), false);
            pieces.forEach(function (part) {
              if (!part.trim()) return;
              append(aiMsg(esc(part.trim()), '', clockNow(), '', 'happy', assistantRef));
            });
          }
          presentReply(finalText);
          liveAvatar(el, 'happy');
          if (turnId && !liveCompleted[turnId]) {
            liveCompleted[turnId] = true;
            CHAT_LOG.push({
              who: 'ai', html: esc(finalText), text: finalText,
              time: clockNow(), ref: assistantRef
            });
          }
          if (!turnId || liveCurrentTurn === turnId) { liveCurrentTurn = ''; liveSetCancel(false); }
        } else if (type === 'cancelled') {
          liveText(el, '已停止回复', false);
          liveAvatar(el, 'idle');
          if (!turnId || liveCurrentTurn === turnId) { liveCurrentTurn = ''; liveSetCancel(false); }
        }
      }
      function scheduleLivePoll(ms) {
        clearTimeout(livePollTimer);
        if (!liveStopped && live) livePollTimer = setTimeout(livePoll, ms);
      }
      async function livePoll() {
        if (!live || liveStopped || livePollBusy) return;
        livePollBusy = true;
        try {
          var payload = await T.poll();
          var events = (payload && payload.events) || [];
          for (var ei = 0; ei < events.length; ei++) {
            var ev = events[ei], seq = Number(ev && ev.seq);
            if (isFinite(seq) && liveCovered[seq]) delete liveCovered[seq];
            else applyLiveEvent(ev);
          }
          if (payload && payload.next_cursor !== undefined) await T.ack(payload.next_cursor);
          scheduleLivePoll(payload && payload.has_more ? 30 : 850);
        } catch (err) {
          if (err && err.status === 401) { live = false; location.hash = '#/connect'; return; }
          scheduleLivePoll(1800);
        } finally {
          livePollBusy = false;
        }
      }
      async function liveBootstrap() {
        if (!live) return;
        try {
          var boot = await T.bootstrap();
          if (!boot || !boot.bound) { live = false; location.hash = '#/connect'; return; }
          var hp = await T.history('', 50);
          hydrateHistory((hp && hp.messages) || boot.history || []);
          historyBefore = String((hp && hp.next_before) || '');
          historyHasMore = !!(hp && hp.has_more);
          if (historyRef) await locateHistoryRef(historyRef);
          (boot.pending_approvals || []).forEach(renderApproval);
          (boot.covered_event_seqs || []).forEach(function (seq) { liveCovered[Number(seq)] = true; });
          liveCurrentTurn = String(boot.pending_turn_id || '');
          if (liveCurrentTurn) { liveEnsure(liveCurrentTurn); liveSetCancel(true); }
          else liveSetCancel(false);
          scheduleLivePoll(0);
        } catch (err) {
          if (err && err.status === 401) { live = false; location.hash = '#/connect'; }
          else scheduleLivePoll(1200);
        }
      }
      async function liveCancel() {
        if (!liveCurrentTurn) return;
        var id = liveCurrentTurn;
        try {
          await T.cancel(id);
          applyLiveEvent({ type: 'cancelled', turn_id: id });
        } catch (err) {
          if (err && err.status === 409) { liveCurrentTurn = ''; liveSetCancel(false); }
        }
      }
      /* 离线原型演出已移除：AI 状态只由真实 Mobile Transport 事件驱动。 */
      async function push() {
        if (live && send.getAttribute('data-live-cancel') === '1') {
          await liveCancel();
          return;
        }
        var v = (input.value || '').trim();
        if (!v) return;
        input.value = '';
        var reply = pendingReply ? {
          ref: pendingReply.ref, text: pendingReply.text,
          role: pendingReply.role, author: pendingReply.author
        } : null;
        pendingReply = null;
        var quoteNode = root.querySelector('.composerquote');
        if (quoteNode) quoteNode.remove();
        var bodyHtml = (reply ? quoteCard(reply.ref, reply.text, reply.role) : '') + esc(v);
        append(meMsg(bodyHtml, '发送中…', clockNow()));
        var sentNode = list.lastElementChild;
        var logEntry = pushLog({
          who: 'me', html: bodyHtml, text: v, time: clockNow(),
          replyTo: reply && reply.ref ? reply.ref : ''
        });

        if (live) {
          if (sentNode) sentNode.classList.add('is-send-pending');
          queueComposeText(v, sentNode, reply, logEntry);
          return;
        }

        /* 未连接时不伪造 AI 回复：保留用户输入并明确要求先连接真实设备。 */
        append(sysMsg('尚未连接 Kissne 设备，消息未发送。', clockNow()));
        location.hash = '#/connect';
      }

      /* 从历史搜索点进来：滚到那条消息并高亮（微信式的"定位到原文"） */
      var historyRef = (p && p.get('ref')) || '';

      var findKw = (p && p.get('find')) || '';
      var hitT = null;
      if (findKw) {
        var msgs2 = list.querySelectorAll('.msg');
        var hit = null;
        for (var mi = 0; mi < msgs2.length; mi++) {
          if ((msgs2[mi].textContent || '').indexOf(findKw) >= 0) hit = msgs2[mi];
        }
        if (hit) {
          var top = 0, node = hit;
          while (node && node !== list) { top += node.offsetTop; node = node.offsetParent; }
          list.scrollTop = Math.max(0, top - 56);
          hit.classList.add('is-hit');
          hitT = setTimeout(function () { hit.classList.remove('is-hit'); }, 1800);
        } else {
          list.insertAdjacentHTML('afterbegin',
            '<div class="srchmiss">没有找到「' + esc(findKw) + '」，可能已被清理。</div>');
        }
      }

      /* 照片：使用系统相册选择器，直接按真实 attachment 合同发送。 */
      var imagePicker = root.querySelector('.chat-image-picker');
      var pickImageBtn = root.querySelector('[data-chat-action="pick-image"]');
      var filePicker = root.querySelector('.chat-file-picker');
      var fileBtn = root.querySelector('[data-chat-action="pick-file"]');
      function onPickImage() { if (imagePicker) imagePicker.click(); }
      async function flushTextBeforeAttachment() {
        if (composeBatch.length) await flushComposeBatch();
      }
      async function onImagesChosen() {
        if (!imagePicker || !imagePicker.files || !imagePicker.files.length) return;
        if (!live) { append(sysMsg('尚未连接 Kissne 设备，图片未发送。', clockNow())); return; }
        await flushTextBeforeAttachment();
        var files = Array.prototype.slice.call(imagePicker.files, 0, 4);
        try {
          var attachments = [];
          for (var fi = 0; fi < files.length; fi++) {
            var file = files[fi];
            var url = URL.createObjectURL(file);
            append(meMsg('<span class="stkmsg"><img class="stkimg" src="' + esc(url) + '" alt="已选择图片"></span>', '', clockNow()));
            attachments.push({
              type: 'image',
              mime_type: file.type || 'image/jpeg',
              data: await T.blobToBase64(file)
            });
          }
          var accepted = await T.sendMessage({ attachments: attachments });
          liveCurrentTurn = String((accepted && accepted.turn_id) || '');
          if (liveCurrentTurn) { liveEnsure(liveCurrentTurn); liveSetCancel(true); }
          scheduleLivePoll(0);
        } catch (err) {
          append(sysMsg((err && err.status === 413) ? '图片过大，请选择更小的图片。' : '图片发送失败，请重试。', clockNow()));
        } finally {
          imagePicker.value = '';
        }
      }
      function onPickFile() { if (filePicker) filePicker.click(); }
      async function onFilesChosen() {
        if (!filePicker || !filePicker.files || !filePicker.files.length) return;
        if (!live) { append(sysMsg('尚未连接 Kissne 设备，文件未发送。', clockNow())); return; }
        await flushTextBeforeAttachment();
        var files = Array.prototype.slice.call(filePicker.files, 0, 4);
        try {
          var attachments = [];
          for (var fi = 0; fi < files.length; fi++) {
            var file = files[fi];
            attachments.push({
              type: 'file',
              mime_type: file.type || 'text/plain',
              data: await T.blobToBase64(file),
              label: file.name || 'file'
            });
          }
          append(meMsg(icon('file', 15) + '<span>' + esc(files.map(function (x) { return x.name; }).join('、')) + '</span>', '', clockNow()));
          var accepted = await T.sendMessage({ attachments: attachments });
          liveCurrentTurn = String((accepted && accepted.turn_id) || '');
          if (liveCurrentTurn) { liveEnsure(liveCurrentTurn); liveSetCancel(true); }
          scheduleLivePoll(0);
        } catch (err) {
          append(sysMsg((err && err.status === 413) ? '文件过大，请选择更小的文件。' : '文件发送失败或格式不受支持。', clockNow()));
        } finally {
          filePicker.value = '';
        }
      }
      if (pickImageBtn) pickImageBtn.addEventListener('click', onPickImage);
      if (imagePicker) imagePicker.addEventListener('change', onImagesChosen);
      if (fileBtn) fileBtn.addEventListener('click', onPickFile);
      if (filePicker) filePicker.addEventListener('change', onFilesChosen);

      /* 表情面板里的贴图：点一张就发出去，然后收起面板（不跳页） */
      var stkState = (ctx && ctx.state && ctx.state !== 'empty' && ctx.state !== 'keyboard')
        ? ctx.state : 'normal';
      var stkItems = root.querySelectorAll('[data-stk]');
      function onStkTap(e) {
        var s2 = pick(STICKERS, e.currentTarget.getAttribute('data-stk'), STICKERS[0].k);
        var html = '<span class="stkmsg">' + K.sticker(s2.k, { alt: s2.label }) + '</span>';
        append(meMsg(html, '', clockNow()));
        pushLog({ who: 'me', html: html, time: clockNow() });
        /* 真连接：把表情包原图作为 sticker attachment 交给 Mobile Transport。 */
        if (live) {
          flushTextBeforeAttachment().then(function () {
          var stickerUrl = K.stickerPath ? K.stickerPath(s2.k) : '';
          T.sendAsset(stickerUrl, 'sticker', s2.label).then(function (accepted) {
            liveCurrentTurn = String((accepted && accepted.turn_id) || '');
            if (liveCurrentTurn) { liveEnsure(liveCurrentTurn); liveSetCancel(true); }
            scheduleLivePoll(0);
          }).catch(function () {
            append(sysMsg('表情包发送失败，请重试。', clockNow()));
          });
          }).catch(function () {
            append(sysMsg('前一批文字发送失败，表情包暂未发送。', clockNow()));
          });
        }
        location.hash = '#/chat?state=' + stkState;      /* 收起面板 */
      }
      for (var si = 0; si < stkItems.length; si++) stkItems[si].addEventListener('click', onStkTap);

      /* 消息交互：长按/右键复制；失败文本可原位重试；图片点击查看。 */
      var holdTimer = null, actionTarget = null;
      function closeMsgActions() {
        var old = root.querySelector('.msgactions');
        if (old && old.parentNode) old.parentNode.removeChild(old);
        actionTarget = null;
      }
      function openMsgActions(msg) {
        closeMsgActions();
        actionTarget = msg;
        var menu = document.createElement('div');
        menu.className = 'msgactions';
        menu.innerHTML = '<button type="button" data-msg-copy>复制</button>'
          + (msg && msg.getAttribute('data-history-ref') ? '<button type="button" data-msg-reply>引用</button>' : '')
          + (msg && msg.getAttribute('data-retry-text') ? '<button type="button" data-msg-retry>重试</button>' : '');
        root.appendChild(menu);
      }
      function onMsgPointerDown(e) {
        var msg = e.target.closest && e.target.closest('.msg');
        if (!msg) return;
        clearTimeout(holdTimer);
        holdTimer = setTimeout(function () { openMsgActions(msg); }, 520);
      }
      function onMsgPointerEnd() { clearTimeout(holdTimer); }
      function onMsgContext(e) {
        var msg = e.target.closest && e.target.closest('.msg');
        if (!msg) return;
        e.preventDefault(); openMsgActions(msg);
      }
      async function retryTextNode(msg) {
        var value = msg && msg.getAttribute('data-retry-text');
        if (!value || !live) return;
        var meta = msg.querySelector('.msg__meta');
        if (meta) meta.textContent = '重试中…';
        try {
          var accepted = await T.sendText(value);
          msg.classList.remove('is-send-failed');
          msg.removeAttribute('data-retry-text');
          if (meta) meta.textContent = '';
          liveCurrentTurn = String((accepted && accepted.turn_id) || '');
          if (liveCurrentTurn) { liveEnsure(liveCurrentTurn); liveSetCancel(true); }
          scheduleLivePoll(0);
        } catch (err) {
          if (meta) meta.innerHTML = '<button type="button" class="msgretry" data-retry>发送失败 · 点此重试</button>';
        }
      }
      async function onMsgAction(e) {
        var quoteJump = e.target.closest && e.target.closest('[data-quote-ref]');
        if (quoteJump) {
          await locateHistoryRef(quoteJump.getAttribute('data-quote-ref') || '');
          closeMsgActions();
          return;
        }
        var docBtn = e.target.closest && e.target.closest('[data-full-reply]');
        if (docBtn) {
          var full = decodeURIComponent(docBtn.getAttribute('data-full-reply') || '');
          var viewer = document.createElement('div');
          viewer.className = 'replyviewer';
          viewer.innerHTML = '<div class="replyviewer__sheet"><button type="button" aria-label="关闭">×</button><pre></pre></div>';
          viewer.querySelector('pre').textContent = full;
          viewer.addEventListener('click', function (ev) { if (ev.target === viewer || ev.target.tagName === 'BUTTON') viewer.remove(); });
          root.appendChild(viewer); return;
        }
        var directRetry = e.target.closest && e.target.closest('[data-retry]');
        if (directRetry) {
          var owner = directRetry.closest('.msg');
          await retryTextNode(owner); return;
        }
        if (e.target.closest && e.target.closest('[data-msg-copy]') && actionTarget) {
          var text = (actionTarget.querySelector('.bubble') || actionTarget).innerText || '';
          try { await navigator.clipboard.writeText(text); } catch (_) {}
          closeMsgActions(); return;
        }
        if (e.target.closest && e.target.closest('[data-msg-reply]') && actionTarget) {
          var replyRole = actionTarget.classList.contains('msg--ai') ? 'assistant'
            : (actionTarget.classList.contains('msg--sys') ? 'system' : 'user');
          pendingReply = {
            ref: actionTarget.getAttribute('data-history-ref') || '',
            text: ((actionTarget.querySelector('.bubble') || actionTarget.querySelector('.msg__text')
              || actionTarget.querySelector('.msg__sysline') || actionTarget).innerText || '').trim(),
            role: replyRole,
            author: replyRole === 'assistant' ? '叶青栩' : (replyRole === 'system' ? '系统' : '我')
          };
          var oldQuote = root.querySelector('.composerquote');
          if (oldQuote) oldQuote.remove();
          var quote = document.createElement('div');
          quote.className = 'composerquote';
          quote.innerHTML = '<span>引用 ' + esc(pendingReply.author) + '：' + esc(pendingReply.text.slice(0, 90))
            + '</span><button type="button" data-clear-reply aria-label="取消引用">×</button>';
          var wrap = root.querySelector('.composerwrap');
          if (wrap) wrap.insertBefore(quote, wrap.querySelector('.composer'));
          closeMsgActions(); input.focus(); return;
        }
        if (e.target.closest && e.target.closest('[data-clear-reply]')) {
          pendingReply = null;
          var quoteNode = root.querySelector('.composerquote'); if (quoteNode) quoteNode.remove();
          return;
        }
        if (e.target.closest && e.target.closest('[data-msg-retry]') && actionTarget) {
          var target = actionTarget; closeMsgActions(); await retryTextNode(target); return;
        }
        var img = e.target.closest && e.target.closest('.bubble img');
        if (img && img.src) {
          var viewer = document.createElement('div');
          viewer.className = 'imageviewer';
          viewer.innerHTML = '<button type="button" aria-label="关闭">×</button><img src="' + esc(img.src) + '" alt="图片预览">';
          viewer.addEventListener('click', function () { viewer.remove(); });
          root.appendChild(viewer); return;
        }
        if (!e.target.closest || !e.target.closest('.msgactions')) closeMsgActions();
      }
      list.addEventListener('pointerdown', onMsgPointerDown);
      list.addEventListener('pointerup', onMsgPointerEnd);
      list.addEventListener('pointercancel', onMsgPointerEnd);
      list.addEventListener('contextmenu', onMsgContext);
      root.addEventListener('click', onMsgAction);

      /* 输入区保持在聊天页 flex 文档流底部。
         真机软键盘出现/收起时由浏览器 visual viewport 调整可视区域，
         不再手动写 bottom / transform / padding，避免 Android 收键盘后残留在半屏。 */
      var scr = root.querySelector('.screen--chat');
      var cwrap = root.querySelector('.composerwrap');
      function onFocus() { if (scr) scr.classList.add('is-typing'); }
      function onBlur()  { if (scr) scr.classList.remove('is-typing'); }
      input.addEventListener('focus', onFocus);
      input.addEventListener('blur', onBlur);

      async function loadOlderHistory() {
        if (!live || !historyHasMore || historyLoading || !historyBefore) return false;
        historyLoading = true;
        var oldHeight = list.scrollHeight;
        try {
          var page = await T.history(historyBefore, 50);
          var rows = (page && page.messages) || [];
          var html = rows.map(historyRowHtml).join('');
          if (html) list.insertAdjacentHTML('afterbegin', html);
          historyBefore = String((page && page.next_before) || '');
          historyHasMore = !!(page && page.has_more);
          list.scrollTop = Math.max(0, list.scrollHeight - oldHeight);
          return rows.length > 0;
        } finally { historyLoading = false; }
      }
      async function locateHistoryRef(ref) {
        ref = String(ref || '');
        if (!ref) return false;
        var safeRef = (window.CSS && typeof window.CSS.escape === 'function')
          ? window.CSS.escape(ref)
          : ref.replace(/([\\"'\[\]#.:>+~*=() ])/g, '\\$1');
        var selector = '[data-history-ref="' + safeRef + '"]';
        var hit = list.querySelector(selector);
        var pages = 0;
        while (!hit && live && historyHasMore && historyBefore && pages < 40) {
          var loaded = await loadOlderHistory();
          pages++;
          hit = list.querySelector(selector);
          if (!loaded) break;
        }
        if (!hit) {
          var oldMiss = list.querySelector('.srchmiss[data-ref-miss]');
          if (oldMiss) oldMiss.remove();
          list.insertAdjacentHTML('afterbegin',
            '<div class="srchmiss" data-ref-miss>原消息暂时找不到，可能已被清理。</div>');
          return false;
        }
        jumpTo(Math.max(0, hit.offsetTop - 56));
        hit.classList.add('is-hit');
        setTimeout(function () { hit.classList.remove('is-hit'); }, 1800);
        return true;
      }
      function onHistoryScroll() { if (list.scrollTop < 72) loadOlderHistory(); }
      list.addEventListener('scroll', onHistoryScroll);

      /* —— 未读胶囊：显示 / 点击跳到最早那条未读 / 滚到底自动清掉 —— */
      var upill = root.querySelector('[data-unread]');
      function paintPill() {
        if (!upill) return;
        upill.hidden = !UNREAD.n;
        var nEl = upill.querySelector('[data-unread-n]');
        if (nEl) nEl.textContent = UNREAD.n;
        var badge = root.querySelector('.tabbar__badge');
        if (badge) badge.textContent = UNREAD.n > 9 ? '9+' : UNREAD.n;
      }
      function clearUnread() { UNREAD.n = 0; UNREAD.first = -1; paintPill(); }
      function onPill() {
        if (!UNREAD.n) return;
        var at = UNREAD.first >= 0 ? UNREAD.first : Math.max(0, CHAT_LOG.length - UNREAD.n);
        var msgs = list.querySelectorAll('.msg');
        var hit = msgs[at] || msgs[0];
        if (hit) {
          var top = 0, node = hit;
          while (node && node !== list) { top += node.offsetTop; node = node.offsetParent; }
          jumpTo(Math.max(0, top - 16));
          hit.classList.add('is-hit');
          clearTimeout(hitT);
          hitT = setTimeout(function () { hit.classList.remove('is-hit'); }, 1600);
        }
        clearUnread();
      }
      function onScroll() {
        if (!UNREAD.n) return;
        if (Date.now() < scrollGuard) return;      /* 自己滚的不算已读 */
        if (list.scrollTop + list.clientHeight >= list.scrollHeight - 8) clearUnread();
      }
      if (upill) upill.addEventListener('click', onPill);
      list.addEventListener('scroll', onScroll);
      /* 思考过程 / 工具调用：点标题行展开或收起。
         用**事件委托**挂在列表上 —— 消息是随时新长出来的，逐个绑会漏。 */
      function onTlogTap(e) {
        var t = e.target;
        while (t && t !== list && !(t.classList && t.classList.contains('tlog__row'))) t = t.parentNode;
        if (!t || t === list) return;
        var blk = t.parentNode;
        if (blk && blk.classList) blk.classList.toggle('is-open');
      }
      list.addEventListener('click', onTlogTap);
      paintPill();

      /* 从表情包页选了一张：落成一条「我」的消息（贴图不带气泡底板）。
         用「本次导航的 hash」去重：同一 URL 重渲染不会重复发，
         而回到表情包页再点（hash 里的 n 会变）可以再发同一张。
         注意**不要用 location.replace 改 URL** —— file:// 下会整页重载，看起来就像"点了没反应"。 */
      var skKey = p && p.get('sticker');
      if (skKey && LAST_SENT_HASH !== location.hash) {
        LAST_SENT_HASH = location.hash;
        var sk = pick(STICKERS, skKey, STICKERS[0].k);
        var html = '<span class="stkmsg">' + K.sticker(sk.k, { alt: sk.label }) + '</span>';
        append(meMsg(html, '', clockNow()));
        pushLog({ who: 'me', html: html, time: clockNow() });
      }

      if (live) liveBootstrap();

      function onKey(e) { if (e.key === 'Enter') push(); }
      input.addEventListener('keydown', onKey);
      send.addEventListener('click', push);
      return function () {
        input.removeEventListener('keydown', onKey);
        input.removeEventListener('input', onComposeInput);
        input.removeEventListener('focus', onFocus);
        input.removeEventListener('blur', onBlur);

        for (var sj = 0; sj < stkItems.length; sj++) stkItems[sj].removeEventListener('click', onStkTap);
        if (pickImageBtn) pickImageBtn.removeEventListener('click', onPickImage);
        if (imagePicker) imagePicker.removeEventListener('change', onImagesChosen);
        if (fileBtn) fileBtn.removeEventListener('click', onPickFile);
        if (filePicker) filePicker.removeEventListener('change', onFilesChosen);
        if (upill) upill.removeEventListener('click', onPill);
        list.removeEventListener('scroll', onScroll);
        list.removeEventListener('scroll', onHistoryScroll);
        list.removeEventListener('click', onTlogTap);
        list.removeEventListener('click', onApprovalClick);
        list.removeEventListener('pointerdown', onMsgPointerDown);
        list.removeEventListener('pointerup', onMsgPointerEnd);
        list.removeEventListener('pointercancel', onMsgPointerEnd);
        list.removeEventListener('contextmenu', onMsgContext);
        root.removeEventListener('click', onMsgAction);
        root.removeEventListener('click', onModelChoice);
        clearTimeout(holdTimer);
        send.removeEventListener('click', push);
        liveStopped = true;
        clearTimeout(livePollTimer);
        clearTimeout(composeTimer);
        composeBatch.length = 0;
        clearTimeout(hitT);
        clearTimeout(bootT);
      };
    }
  });

  /* =====================================================================
     06 小机星页 —— 叶青栩的家 + 室外地图（纯色块拼的像素场景）
     ---------------------------------------------------------------------
     · 沉浸式：页面上不出现原型注释
     · 叶青栩走门、能出门，跨地图沿链逐跳穿过
     · **场景只在他真正所在的房间才有人**：他在厨房时点客厅，客厅是空的
     · 另有一个**绿色小人由用户操控**（半透明方向键），可以在各张地图间走动
     全部纯色块拼，不生成图片。
     ===================================================================== */
  var UNIVERSE_STATES = [
    { key: 'auto',   label: '观察 · 自动漫游（默认）' },
    { key: 'home',   label: '观察 · 家里' },
    { key: 'yard',   label: '观察 · 院子' },
    { key: 'street', label: '观察 · 街道' },
    { key: 'park',   label: '观察 · 公园' },
    { key: 'scene',  label: '观察 · 场景（沉浸）' },
    { key: 'enter',  label: '已获准 · 进入小机星' }
  ];
  /* 是否已获准进入小机星 —— 模块级，**一旦批准就一直有效**：
     之前每换一个状态（比如点叶青栩进场景）就退回观察模式，还得重新请示。 */
  var ENTERED = false;

  /* =====================================================================
     叶青栩的作息引擎 —— **模块级，不挂在页面生命周期上**
     ---------------------------------------------------------------------
     用户点房间进场景、切状态、切页，都只是"看"，**不会影响他在做什么**：
     引擎自己按 170ms 一步往下走，页面在就重绘，页面不在就只更新状态。
     只有**点他本人**（和他说话）才会让他停下（`pauseUntil`）。
     之前把作息写在页面 mount 里，一进场景就整段作废、回来时被拉回出发房间。
     ===================================================================== */
  var AI = {
    at: 'living',    /* 他现在在哪（走到才算） */
    coming: '',      /* 正在去的地方 */
    idx: 0,          /* 作息进度 */
    map: 'home',     /* 此刻画在哪张图 */
    pos: null,       /* 此刻画在哪（%） */
    plan: [],        /* 这一程剩下的步点 */
    dest: '',        /* 这一程的目的地 */
    waitUntil: 0,    /* 下一程什么时候出发 */
    pauseUntil: 0,   /* 被点住"聊天"时暂停到什么时候 */
    timer: null,
    repaint: null    /* 页面挂载时注册的绘制回调 */
  };

  function aiExpand(pts, from) {
    var out = [], cur = from.slice();
    for (var i = 0; i < pts.length; i++) {
      var d = pts[i], dx = d[0] - cur[0], dy = d[1] - cur[1];
      var n = Math.max(1, Math.round(Math.max(Math.abs(dx), Math.abs(dy)) / 2));
      for (var j = 1; j <= n; j++) out.push([cur[0] + dx * j / n, cur[1] + dy * j / n]);
      cur = d;
    }
    return out;
  }
  /* 点击目标跟着**当前位置**走（走廊没有场景 → 返回空，点了不跳） */
  function aiNavFor(map, x, y) {
    if (map !== 'home') return '#/universe?state=scene&room=' + map;
    for (var i = 0; i < HOUSE_ROOMS.length; i++) {
      var r = HOUSE_ROOMS[i];
      if (x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h) {
        return '#/universe?state=scene&room=' + r.k;
      }
    }
    return '';
  }
  function aiPlanNext() {
    AI.idx = (AI.idx + 1) % ROUTINE.length;
    var todo = ROUTINE[AI.idx];
    AI.dest = todo.k;
    AI.coming = todo.k;
    var cur = (AI.pos || areaInfo(AI.at).spot).slice();
    var segs = segsFor(AI.at, todo.k);
    AI.plan = [];
    for (var i = 0; i < segs.length; i++) {
      var seg = segs[i];
      if (seg.start) cur = seg.start.slice();
      var pts = aiExpand(seg.pts, cur);
      for (var j = 0; j < pts.length; j++) AI.plan.push({ map: seg.map, x: pts[j][0], y: pts[j][1] });
      if (pts.length) cur = pts[pts.length - 1].slice();
    }
    /* 防御：万一这一程没有步点（比如"同屋换个动作"），不要让它空转 ——
       直接算作已到达，否则 aiEngine 会每 170ms 就再排一程，把作息瞬间刷完。 */
    if (!AI.plan.length) {
      AI.at = AI.dest;
      AI.coming = '';
      AI.waitUntil = Date.now() + 3600;
    }
    if (AI.repaint) AI.repaint();
  }
  function aiEngine() {
    var now = Date.now();
    if (now < AI.pauseUntil) { if (AI.repaint) AI.repaint(); return; }
    if (!AI.plan.length) {
      if (now < AI.waitUntil) return;
      aiPlanNext();
      return;
    }
    var p = AI.plan.shift();
    AI.map = p.map;
    AI.pos = [p.x, p.y];
    if (!AI.plan.length) {                    /* 这一程走完了 */
      AI.at = AI.dest;
      AI.coming = '';
      AI.waitUntil = now + 3600;
    }
    if (AI.repaint) AI.repaint();
  }
  function aiStart() {
    if (AI.timer) return;
    if (!AI.waitUntil) AI.waitUntil = Date.now() + 1000;
    AI.timer = setInterval(aiEngine, 170);
  }
  function aiPause(ms) { AI.pauseUntil = Date.now() + (ms || 8000); }

  /* 家里的房间（百分比坐标） */
  var HOUSE_ROOMS = [
    { k: 'living',  name: '客厅', x: 2,  y: 2,  w: 52, h: 34 },
    { k: 'study',   name: '书房', x: 56, y: 2,  w: 42, h: 34 },
    { k: 'kitchen', name: '厨房', x: 2,  y: 52, w: 30, h: 46 },
    { k: 'bedroom', name: '卧室', x: 34, y: 52, w: 32, h: 46 },
    { k: 'bath',    name: '厕所', x: 68, y: 52, w: 30, h: 46 }
  ];
  var CORRIDOR_Y = 44;                 /* 走廊中心线（走廊占 y 38–50） */
  var FRONT_DOOR = [96, 44];           /* 大门：走廊右端 */
  var DOOR_X = { living: 28, study: 77, kitchen: 17, bedroom: 50, bath: 83 };
  var DOOR_Y = { living: 38, study: 38, kitchen: 52, bedroom: 52, bath: 52 };
  var SPOT   = { living: [28, 30], study: [77, 30], kitchen: [17, 86], bedroom: [50, 86], bath: [83, 86] };

  /* 室外地图 */
  var OUTDOOR = {
    yard:   { name: '院子', spot: [50, 74],
      props: [{ s: 'tree', x: 8, y: 22, w: 18, h: 46 }, { s: 'tree', x: 74, y: 26, w: 18, h: 46 },
              { s: 'bench', x: 38, y: 86, w: 24, h: 10 }] },
    street: { name: '街道', spot: [62, 74],
      props: [{ s: 'block', x: 4, y: 12, w: 16, h: 20 }, { s: 'block', x: 24, y: 12, w: 20, h: 20 },
              { s: 'block', x: 50, y: 12, w: 14, h: 20 }, { s: 'block', x: 70, y: 12, w: 24, h: 20 }] },
    park:   { name: '公园', spot: [40, 74],
      props: [{ s: 'tree', x: 8, y: 16, w: 20, h: 50 }, { s: 'tree', x: 74, y: 14, w: 20, h: 50 },
              { s: 'bench', x: 34, y: 66, w: 30, h: 10 }, { s: 'pond', x: 26, y: 86, w: 40, h: 8 }] }
  };

  /* 地图之间的接缝：out = 从当前地图出去的位置，in = 进入新地图的落点 */
  var LINK = {
    'home|yard':   { out: FRONT_DOOR, in: [50, 8] },
    'yard|home':   { out: [50, 8],    in: FRONT_DOOR },
    'yard|street': { out: [50, 96],   in: [30, 8] },
    'street|yard': { out: [30, 8],    in: [50, 96] },
    'street|park': { out: [96, 56],   in: [6, 56] },
    'park|street': { out: [6, 56],    in: [96, 56] }
  };

  /* 叶青栩自己的作息：轮着去这些地方，跨地图时会走大门出去 */
  var ROUTINE = [
    { k: 'living',  act: '窝在沙发上发呆' },
    { k: 'study',   act: '在书桌前整理今天的记忆' },
    { k: 'kitchen', act: '在灶台前做点吃的' },
    { k: 'yard',    act: '出门，到院子里透透气' },
    { k: 'street',  act: '沿街慢慢走' },
    { k: 'park',    act: '坐在长椅上看天' },
    { k: 'street',  act: '往回走' },
    { k: 'yard',    act: '走回院子' },
    { k: 'bedroom', act: '回卧室躺一会儿' },
    { k: 'bath',    act: '进去待了一会儿' }
  ];
  function actOf(k) {
    for (var i = 0; i < ROUTINE.length; i++) { if (ROUTINE[i].k === k) return ROUTINE[i].act; }
    return '';
  }

  /* 场景（点开房间 / 地图后进入）：背景块 + 2D 叶青栩 + 对话 + 可触碰的点。
     注意：只有当叶青栩**真的在这个房间**时才会有人、才有对话。 */
  var SCENES = {
    living:  { name: '客厅', out: false, say: '欢迎回来。要不要在这儿坐一会儿？',
      props: [{ label: '沙发', k: 'sofa', desc: '一张布面的双人沙发。', x: 6, y: 64, w: 46, h: 20, say: '这张沙发是我最喜欢的位置。' },
              { label: '电视', k: 'tv', desc: '挂在墙上的电视，屏幕暗着。', x: 64, y: 48, w: 26, h: 30, say: '电视很少开，除非你陪我看。' }] },
    study:   { name: '书房', out: false, say: '今天的记忆我刚整理完。',
      props: [{ label: '书架', k: 'shelf', desc: '塞满书的架子。', x: 6, y: 16, w: 24, h: 32, say: '这几本你都提过，我记着呢。' },
              { label: '书桌', k: 'desk', desc: '桌面摊着纸和笔。', x: 32, y: 64, w: 42, h: 20, say: '桌上还摊着没写完的东西。' }] },
    kitchen: { name: '厨房', out: false, say: '正好，我在做点吃的。',
      props: [{ label: '灶台', k: 'stove', desc: '台面上还留着温度。', x: 8, y: 58, w: 30, h: 24, say: '锅里还温着。' },
              { label: '冰箱', k: 'fridge', desc: '门上贴了几张便签。', x: 66, y: 26, w: 24, h: 50, say: '冰箱上贴着几张便签。' }] },
    bath:    { name: '厕所', out: false, say: '……你先出去一下。',
      props: [{ label: '镜子', k: 'mirror', desc: '一面带着水汽的镜子。', x: 34, y: 16, w: 32, h: 24, say: '镜子上的水汽还没散。' }] },
    bedroom: { name: '卧室', out: false, say: '有点困，我躺一会儿。',
      props: [{ label: '床', k: 'bed', desc: '铺得整整齐齐的床。', x: 6, y: 60, w: 56, h: 26, say: '被子是刚晒过的味道。' },
              { label: '床头灯', k: 'lamp', desc: '一盏暖黄的小灯。', x: 74, y: 46, w: 16, h: 24, say: '睡前我一般留一盏小灯。' }] },
    yard:    { name: '院子', out: true, say: '外面风挺好的。',
      props: [{ label: '树', k: 'tree', desc: '一棵长得挺好的树。', x: 10, y: 28, w: 20, h: 44, say: '这棵树是我搬来那年种的。' },
              { label: '石凳', k: 'bench', desc: '一块被晒暖的石头。', x: 62, y: 62, w: 28, h: 20, say: '坐会儿吧，石头晒得暖暖的。' }] },
    street:  { name: '街道', out: true, say: '街上没什么人。',
      props: [{ label: '路牌', k: 'sign', desc: '一块掉了漆的路牌。', x: 68, y: 28, w: 18, h: 44, say: '路牌上的字掉漆了。' },
              { label: '店铺', k: 'block', desc: '一家关着门的店。', x: 6, y: 34, w: 34, h: 32, say: '这家店今天没开。' }] },
    park:    { name: '公园', out: true, say: '坐会儿吧，这儿安静。',
      props: [{ label: '长椅', k: 'bench', desc: '一张旧木长椅。', x: 30, y: 64, w: 36, h: 20, say: '长椅上刻着谁的名字。' },
              { label: '树', k: 'tree', desc: '一棵大树，树叶很密。', x: 70, y: 22, w: 22, h: 44, say: '树叶响得很好听。' }] }
  };

  /* —— 运行期状态：「谁在哪」记在模块级，切页也不丢 ——
     叶青栩的位置由 AI 引擎维护（见下面的 AI），这里只剩用户操控的绿色小人。 */
  var ME = { map: 'home', x: 50, y: 44 };     /* 用户操控的绿色小人 */

  function areaInfo(k) {
    if (OUTDOOR[k]) return { map: k, name: OUTDOOR[k].name, spot: OUTDOOR[k].spot };
    for (var i = 0; i < HOUSE_ROOMS.length; i++) {
      if (HOUSE_ROOMS[i].k === k) return { map: 'home', name: HOUSE_ROOMS[i].name, spot: SPOT[k] };
    }
    return null;
  }
  /* 地图是一条链：家 — 院子 — 街道 — 公园。跨多张地图时要逐跳走。 */
  var CHAIN = ['home', 'yard', 'street', 'park'];
  function mapHops(a, b) {
    var i = CHAIN.indexOf(a), j = CHAIN.indexOf(b), hops = [];
    if (i < 0 || j < 0) return hops;
    var dir = i < j ? 1 : -1;
    for (var k = i; k !== j; k += dir) hops.push([CHAIN[k], CHAIN[k + dir]]);
    return hops;
  }
  function pathInHome(from, to) {
    if (from === to) return [];
    return [[DOOR_X[from], DOOR_Y[from]], [DOOR_X[from], CORRIDOR_Y],
            [DOOR_X[to], CORRIDOR_Y], [DOOR_X[to], DOOR_Y[to]], SPOT[to]];
  }
  function pathHomeToExit(from, exit) {
    return [[DOOR_X[from], DOOR_Y[from]], [DOOR_X[from], CORRIDOR_Y], exit];
  }
  function pathEnterToRoom(enter, to) {
    return [enter, [DOOR_X[to], CORRIDOR_Y], [DOOR_X[to], DOOR_Y[to]], SPOT[to]];
  }
  /* 把一次移动拆成若干段：本图内走到出口 → 逐张地图穿过 → 进入目标点 */
  function segsFor(fromKey, toKey) {
    var a = areaInfo(fromKey), b = areaInfo(toKey), segs = [];
    if (!a || !b) return segs;
    var hops = mapHops(a.map, b.map);

    if (!hops.length) {
      if (fromKey === toKey) return segs;
      if (a.map === 'home') segs.push({ map: 'home', pts: pathInHome(fromKey, toKey) });
      else segs.push({ map: a.map, pts: [b.spot] });
      return segs;
    }

    var link0 = LINK[a.map + '|' + hops[0][1]];
    segs.push({ map: a.map, pts: a.map === 'home' ? pathHomeToExit(fromKey, link0.out) : [link0.out] });

    for (var h = 0; h < hops.length; h++) {
      var to = hops[h][1];
      var link = LINK[hops[h][0] + '|' + to];
      if (h === hops.length - 1) {
        segs.push({ map: to, start: link.in, dest: true,
                    pts: to === 'home' ? pathEnterToRoom(link.in, toKey) : [link.in, b.spot] });
      } else {
        var nxt = LINK[to + '|' + hops[h + 1][1]];
        segs.push({ map: to, start: link.in, pts: [nxt.out] });
      }
    }
    return segs;
  }

  /* —— 绿色小人（用户操控）—— */
  /* 能走的地方：家里只能在房间 / 走廊 / 房门通道里走；室外只在地面上走 */
  function walkable(map, x, y) {
    if (map === 'home') {
      if (y >= 38 && y <= 50 && x >= 2 && x <= 98) return true;
      for (var i = 0; i < HOUSE_ROOMS.length; i++) {
        var r = HOUSE_ROOMS[i];
        if (x >= r.x + 2 && x <= r.x + r.w - 2 && y >= r.y + 2 && y <= r.y + r.h - 2) return true;
      }
      /* 房门通道只开在自己那道门那一小段。
         之前把纵向范围写成 33~55，结果在「卧室门」那条 x 上
         可以从走廊直接穿墙钻进客厅 —— 必须按门所在的那排分别开。 */
      for (var k in DOOR_X) {
        if (Math.abs(x - DOOR_X[k]) > 5) continue;
        if (DOOR_Y[k] === 38 && y >= 33 && y <= 41) return true;   /* 上排房间的门 */
        if (DOOR_Y[k] === 52 && y >= 49 && y <= 55) return true;   /* 下排房间的门 */
      }
      return false;
    }
    /* 室外：地面上随便走；「门」到地面之间留一条竖直小路。
       之前只有 y>=36 可走，而从门里出来落在 y=14 附近 ——
       一步都迈不动、也回不去（出门即冻住的真 bug）。 */
    if (y >= 36) return true;
    var ps = WALK_PATHS[map] || [];
    for (var p = 0; p < ps.length; p++) {
      if (x >= ps[p].x && x <= ps[p].x + ps[p].w && y >= ps[p].y) return true;
    }
    return false;
  }
  /* 走到这些门口就会切到相邻地图 */
  var EXITS = {
    home:   [{ x: 92, y: 37, w: 8,  h: 14, to: 'yard',   at: [50, 14] }],
    yard:   [{ x: 30, y: 90, w: 40, h: 10, to: 'street', at: [30, 14] },
             { x: 38, y: 2,  w: 24, h: 8,  to: 'home',   at: [88, 44] }],
    street: [{ x: 8,  y: 2,  w: 44, h: 8,  to: 'yard',   at: [50, 88] },
             { x: 92, y: 0,  w: 8,  h: 100, to: 'park',  at: [14, 56] }],
    park:   [{ x: 0,  y: 0,  w: 9,  h: 100, to: 'street', at: [86, 56] }]
  };
  /* 室外地图上「门 → 地面」的竖直小路（x 起点 / y 起点 / 宽）。
     必须盖住每个落点：家→院子的落点 (50,14)、院子→街道的落点 (30,14)。 */
  var WALK_PATHS = {
    yard:   [{ x: 44, y: 8,  w: 12 }],   /* 上方通向家的门 */
    street: [{ x: 24, y: 8,  w: 12 }]    /* 左上通向院子的门 */
  };
  /* 站在哪 —— 用来显示「你 · 在客厅」 */
  function whereAmI(map, x, y) {
    if (map !== 'home') return OUTDOOR[map] ? OUTDOOR[map].name : '';
    for (var i = 0; i < HOUSE_ROOMS.length; i++) {
      var r = HOUSE_ROOMS[i];
      if (x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h) return r.name;
    }
    return '走廊';
  }

  /* 俯视图：家里 / 室外。每个房间、每张地图都能点开进入场景 */
  function mapPane(k, active) {
    if (k === 'home') {
      var doors = HOUSE_ROOMS.map(function (r) {
        return '<i class="dr" style="left:' + (DOOR_X[r.k] - 3.5) + '%;top:' + (DOOR_Y[r.k] - 1.5) + '%"></i>';
      }).join('');
      var rooms = HOUSE_ROOMS.map(function (r) {
        return '<div class="rm" style="left:' + r.x + '%;top:' + r.y + '%;width:' + r.w + '%;height:' + r.h + '%">'
          + '<span class="rm__tag">' + r.name + '</span>'
          + '<i class="f f--' + r.k + '"></i>'
          + '<b class="rm__hit" data-nav="#/universe?state=scene&room=' + r.k + '"></b>'
          + '</div>';
      }).join('');
      return '<div class="map map--home' + (k === active ? ' is-on' : '') + '" data-map="home">'
        + K.bg('scene-room')
        + '<div class="corridor"></div>' + doors + rooms
        + '<i class="frontdoor"></i><span class="frontdoor__tag">大门</span>'
        + '</div>';
    }
    var m = OUTDOOR[k];
    var props = m.props.map(function (p) {
      return '<i class="pr pr--' + p.s + '" style="left:' + p.x + '%;top:' + p.y
        + '%;width:' + p.w + '%;height:' + p.h + '%"></i>';
    }).join('');
    var paths = (WALK_PATHS[k] || []).map(function (p) {
      return '<i class="path" style="left:' + p.x + '%;top:' + p.y
        + '%;width:' + p.w + '%;height:' + (38 - p.y) + '%"></i>';
    }).join('');
    var exits = (EXITS[k] || []).map(function (z) {
      return '<i class="gate" style="left:' + z.x + '%;top:' + z.y + '%;width:' + z.w + '%;height:' + z.h + '%"></i>';
    }).join('');
    return '<div class="map map--' + k + (k === active ? ' is-on' : '') + '" data-map="' + k + '">'
      + K.bg('outdoor-' + k)
      + '<div class="sky"></div><div class="ground"></div>' + paths + props + exits
      + '<b class="map__hit" data-nav="#/universe?state=scene&room=' + k + '"></b>'
      + '</div>';
  }

  /* 像素小人（纯色块）。variant: '' = 叶青栩；'is-me' = 用户操控的绿色小人 */
  function sprite(variant) {
    return '<div class="actor__sprite ' + (variant || '') + '">'
      + '<i class="sp sp--ear1"></i><i class="sp sp--ear2"></i><i class="sp sp--head"></i>'
      + '<i class="sp sp--eye1"></i><i class="sp sp--eye2"></i><i class="sp sp--body"></i>'
      + '<i class="sp sp--leg1"></i><i class="sp sp--leg2"></i><i class="sp sp--tail"></i>'
      + '</div>';
  }
  /* 半透明方向键 */
  function dpad() {
    var dirs = [
      { k: 'u', cls: 'dpad__b--u', label: '向上' },
      { k: 'l', cls: 'dpad__b--l', label: '向左' },
      { k: 'r', cls: 'dpad__b--r', label: '向右' },
      { k: 'd', cls: 'dpad__b--d', label: '向下' }
    ];
    return '<div class="dpad">' + dirs.map(function (d) {
      return '<button class="dpad__b ' + d.cls + '" data-move="' + d.k + '" aria-label="' + d.label + '">'
        + icon('chevron', 18) + '</button>';
    }).join('') + '</div>';
  }

  /* 没获准进入小机星时的入口条：人类不能自己闯进去，得先在人人星跟叶青栩请示。
     获准（state=enter）后这条会换成方向键。 */
  function houseEnterBar() {
    return '<div class="houseenter">'
      + '<span class="houseenter__t">你还在外面</span>'
      + '<span class="houseenter__s">小机星是叶青栩的地方，进去要先跟他说一声。</span>'
      + btn('向叶青栩请示', { small: true, kind: 'ghost', to: '#/chat?state=request-enter' })
      + '</div>';
  }

  /* 场景视图。
     · 背景素材（物件）**永远可以点**，点了会显示"这是什么"
     · 叶青栩只有在真的待在这个房间时才会出现、才会有他的回应；
       他不在时点物件只说明物件本身是什么，不会有人搭话  */
  function sceneView(roomKey, touchKey) {
    var sc = SCENES[roomKey] || SCENES.living;
    var aiHere = roomKey === AI.at;
    /* 他正在往这里走：先说"在过来的路上"，不要说"他不在这里" */
    var aiComing = !aiHere && roomKey === AI.coming;
    var picked = null;
    for (var i = 0; i < sc.props.length; i++) {
      if (touchKey && sc.props[i].k === touchKey) picked = sc.props[i];
    }
    var props = sc.props.map(function (p) {
      var on = (picked && p.k === picked.k) ? ' is-on' : '';
      return '<a class="sgp sgp--' + p.k + on + '"'
        + ' style="left:' + p.x + '%;top:' + p.y + '%;width:' + p.w + '%;height:' + p.h + '%"'
        + ' data-nav="#/universe?state=scene&room=' + roomKey + '&touch=' + p.k + '">'
        + (on ? '<span class="sgp__tag">' + esc(p.label || p.k) + '</span>' : '')
        + '</a>';
    }).join('');

    var who, line;
    if (picked) {
      who = sc.name + ' · ' + (picked.label || picked.k);
      line = aiHere ? picked.say : picked.desc;     /* 他在才有人搭话，否则只说这是什么 */
    } else if (aiHere) {
      who = sc.name; line = sc.say;
    } else if (aiComing) {
      who = sc.name; line = '叶青栩正往这里走…';
    } else {
      who = sc.name; line = '叶青栩现在不在这里。';
    }

    return '\n      <div class="screen screen--scene' + (sc.out ? ' is-out' : '') + '">'
      + '\n        <div class="scn">'
      + '\n          <div class="scn__stage">'
      + '\n            ' + K.bg(sc.out ? 'scene-outdoor' : 'scene-room')
      + '\n            <div class="scn__wall"></div><div class="scn__floor"></div>'
      + '\n            <div class="scn__props">' + props + '</div>'
      + '\n            <button class="scn__back" data-nav="#/universe?state=auto" aria-label="返回">' + icon('back') + '</button>'
      + (aiHere ? '\n            <div class="scn__actor" data-asset="characters/yeqingxu/actions/pixel.svg">' + sprite('') + '</div>' : '')
      + '\n          </div>'
      + '\n          <div class="scn__say">'
      + '\n            <span class="scn__who">' + esc(who) + '</span>'
      + '\n            <span class="scn__line' + (aiHere ? '' : ' is-empty') + '">' + esc(line) + '</span>'
      + '\n          </div>'
      + '\n        </div>'
      + '\n      </div>';
  }


  K.registerScreen({
    no: '06', id: 'universe', name: '小机星页', route: '#/universe', tab: 'universe',
    purpose: '叶青栩的家与外面的世界：俯视像素场景里，AI 小人按自己的行为走门、出门、在各张地图间来回；用户另操控一个绿色小人。点开房间或地图进入沉浸场景（背景 + 2D 叶青栩 + 对话 + 可触碰），只有他在那个房间时才有人。纯色块拼成，不生成图片。',
    out: ['#/home', '#/device'],
    states: UNIVERSE_STATES,
    render: function (ctx) {
      var s = ctx.state || 'auto';
      var q = ctx.params;
      if (s === 'scene') return sceneView((q && q.get('room')) || 'living', q && q.get('touch'));

      /* 俯视态：auto 跟着叶青栩走，其余按状态显示对应那张地图 */
      /* **一旦获准进入就记住**：点叶青栩进场景、切其它俯视图都不会被踢回"外面"，
         不需要反复请示（之前每次换状态都退回观察模式）。 */
      if (s === 'enter') ENTERED = true;
      var entered = ENTERED;
      var active = (s === 'yard' || s === 'street' || s === 'park') ? s : 'home';
      /* 他此刻画在哪：引擎的实时位置优先，没有就用所在房间的落点 */
      var ai = areaInfo(AI.at);
      var aiOnActive = (AI.map === active);
      var aiSpot = aiOnActive && AI.pos
        ? AI.pos
        : (ai && ai.map === active ? ai.spot : [SPOT.living[0], SPOT.living[1]]);
      var aiNav = aiOnActive && AI.pos
        ? (aiNavFor(AI.map, AI.pos[0], AI.pos[1]) || '#/universe?state=scene&room=' + AI.at)
        : '#/universe?state=scene&room=' + AI.at;
      /* 没进入时是「在外面看」：只会看到叶青栩，文案跟着他 */
      var cap = entered
        ? '你 · 在' + whereAmI(ME.map, ME.x, ME.y)
        : (AI.coming
            ? '叶青栩 · 正去' + areaInfo(AI.coming).name + ' · ' + actOf(AI.coming)
            : '叶青栩 · 在' + ai.name + ' · ' + actOf(AI.at));
      return '\n      <div class="screen screen--house">'
        + '\n        <div class="mapstack">'
        + mapPane('home', active) + mapPane('yard', active) + mapPane('street', active) + mapPane('park', active)
        + '\n          <div class="mapstack__actor' + (aiOnActive ? '' : ' is-hidden') + '"'
        + ' style="left:' + aiSpot[0] + '%;top:' + aiSpot[1] + '%"'
        + ' data-placeholder="FOX_PIXEL_SPRITE"'
        + ' title="FOX_PIXEL_SPRITE · 叶青栩像素小人（纯色块拼，占位）"'
        + ' data-asset="characters/yeqingxu/actions/pixel.svg"'
        + ' data-nav="' + aiNav + '">' + sprite('') + '</div>'
        + (entered
            ? '\n          <div class="mapstack__me' + (ME.map === active ? '' : ' is-hidden') + '"'
              + ' style="left:' + ME.x + '%;top:' + ME.y + '%" data-me>' + sprite('is-me') + '</div>'
            : '')
        + '\n          <div class="mapstack__cap" data-cap>' + cap + '</div>'
        + (entered ? dpad() : houseEnterBar())
        + '\n        </div>'
        + '\n      </div>';
    },

    /* 页面级生命周期：app.js 会在切页 / 重渲染时调用返回的 dispose */
    mount: function (root) {
      var actor = root && root.querySelector('.mapstack__actor');
      if (!actor) return null;
      /* 未获准进入时没有绿色小人（也没有方向键）—— 观察模式只跑叶青栩的作息 */
      var meEl = root && root.querySelector('[data-me]');
      var panes = root.querySelectorAll('.map');
      var capEl = root.querySelector('[data-cap]');
      var timers = [], alive = true;
      var pos = (AI.pos || areaInfo(AI.at).spot).slice();
      var driving = false;              /* 用户一旦按方向键，视角就交给用户 */
      var meWalkT = null, holdT = null;

      function capAI() {
        if (Date.now() < AI.pauseUntil) return '叶青栩 · 停下了 · 在听你说话';
        return AI.coming
          ? '叶青栩 · 正去' + areaInfo(AI.coming).name + ' · ' + actOf(AI.coming)
          : '叶青栩 · 在' + areaInfo(AI.at).name + ' · ' + actOf(AI.at);
      }
      function capMe() { return '你 · 在' + whereAmI(ME.map, ME.x, ME.y); }
      function refreshCap() {
        if (!capEl) return;
        /* 有小人在场（= 已获准进入）时，状态条报**你自己**在哪；观察模式才报叶青栩。 */
        capEl.textContent = meEl ? capMe() : capAI();
      }

      var actorMap = AI.map;                 /* 叶青栩此刻画在哪张图上 */
      function showMap(k) {
        /* 用户接管后**镜头锁定在自己的小人身上**：叶青栩换地图也不再把画面带走
           （这就是「我控制绿色小人时突然切到叶青栩那边」的根因）。 */
        var view = (driving && meEl) ? ME.map : k;
        for (var i = 0; i < panes.length; i++) {
          panes[i].classList.toggle('is-on', panes[i].getAttribute('data-map') === view);
        }
        actor.classList.toggle('is-hidden', actorMap !== view);
        if (meEl) meEl.classList.toggle('is-hidden', ME.map !== view);
        refreshCap();
      }
      function place(p) { actor.style.left = p[0] + '%'; actor.style.top = p[1] + '%'; }
      function syncNav() {
        var nav = aiNavFor(actorMap, pos[0], pos[1]);
        if (nav) actor.setAttribute('data-nav', nav);
        else actor.removeAttribute('data-nav');
      }

      /* 页面只负责**画**：引擎更新状态 → 这里把状态画出来。
         页面不在（进场景 / 切页）时引擎照旧往下走，回来就能看到他走到哪了。 */
      AI.repaint = function () {
        actorMap = AI.map;
        if (AI.pos) { pos = AI.pos.slice(); place(pos); }
        actor.classList.toggle('is-walking', !!AI.plan.length && Date.now() >= AI.pauseUntil);
        showMap(AI.map);
        syncNav();
        refreshCap();
      };
      aiStart();            /* 引擎是模块级的：第一次进小机星就启动，之后一直在跑 */

      /* 点他本人 = 和他说话：他会**停下**（页面照 data-nav 进场景） */
      function onActorClick() { aiPause(8000); refreshCap(); }
      actor.addEventListener('click', onActorClick);

      /* —— 方向键：绿色小人 —— */
      var STEP = 2.0;
      function moveMe(dir) {
        if (!meEl) return;                              /* 观察模式没有小人可操控 */
        var nx = ME.x + (dir === 'l' ? -STEP : dir === 'r' ? STEP : 0);
        var ny = ME.y + (dir === 'u' ? -STEP : dir === 'd' ? STEP : 0);
        nx = Math.max(3, Math.min(97, nx));
        ny = Math.max(3, Math.min(97, ny));
        if (!walkable(ME.map, nx, ny)) return;          /* 只有墙会挡住，两个小人之间不再有碰撞体积 */

        ME.x = nx; ME.y = ny;
        var ex = EXITS[ME.map] || [];
        for (var i = 0; i < ex.length; i++) {
          var z = ex[i];
          if (nx >= z.x && nx <= z.x + z.w && ny >= z.y && ny <= z.y + z.h) {
            ME.map = z.to; ME.x = z.at[0]; ME.y = z.at[1];
            break;
          }
        }
        driving = true;
        meEl.style.left = ME.x + '%';
        meEl.style.top = ME.y + '%';
        /* 走路帧动画：和叶青栩用**同一套** `.is-walking`（腿交替的步态循环）。
           之前 160ms 就摘掉 class，动画还没走完一轮就被掐断，看起来像在滑行。
           这里让 class 在连续迈步期间一直挂着，停步 240ms 后才摘。 */
        meEl.classList.add('is-walking');
        clearTimeout(meWalkT);
        meWalkT = setTimeout(function () { meEl.classList.remove('is-walking'); }, 240);
        showMap(ME.map);
      }
      var btns = root.querySelectorAll('[data-move]');
      for (var bi = 0; bi < btns.length; bi++) {
        (function (b) {
          var dir = b.getAttribute('data-move');
          function start(e) {
            if (e && e.preventDefault) e.preventDefault();
            moveMe(dir);
            clearInterval(holdT);
            holdT = setInterval(function () { moveMe(dir); }, 110);
          }
          function stop() { clearInterval(holdT); holdT = null; }
          b.addEventListener('pointerdown', start);
          b.addEventListener('pointerup', stop);
          b.addEventListener('pointerleave', stop);
          b.addEventListener('pointercancel', stop);
        })(btns[bi]);
      }

      refreshCap();
      AI.repaint();          /* 进页面先把"他此刻在哪"画出来 */
      return function () {
        alive = false;
        for (var i = 0; i < timers.length; i++) clearTimeout(timers[i]);
        clearInterval(holdT); clearTimeout(meWalkT);
        /* 页面只是"画布"：离开时**只注销绘制**，不动他的作息 ——
           点房间进场景、切状态、切页，他该走走、该干嘛干嘛，回来能看到他走到哪了。 */
        AI.repaint = null;
        actor.removeEventListener('click', onActorClick);
      };
    }
  });

  /* =====================================================================
     05b 实时语音通话页 —— 从聊天页「＋」菜单进入的专属页面
     内容：叶青栩素材 + 通话状态 + 挂断键（占位，不实现真实通话）
     ===================================================================== */
  var CALL_STATES = [
    { key: 'ongoing',    label: '通话中' },
    { key: 'connecting', label: '正在连接' },
    { key: 'muted',      label: '已静音' },
    { key: 'speaker',    label: '扬声器模式' },
    { key: 'share',      label: '屏幕共享中' }
  ];

  /* =====================================================================
     通话 / 屏幕共享会话 —— **模块级**，所以**可以后台**：
     退出通话页（去人人星、去首页…）会话照旧，顶部会留一条"流体云"提示，
     点一下就能回来。说的话会**转成文字落到人人星**（不在这页显示字幕）。
     ===================================================================== */
  var CALL = { active: false, kind: 'voice', startedAt: 0, muted: false, speaker: false };
  function callStart(kind) {
    CALL.active = true;
    CALL.kind = kind || 'voice';
    CALL.startedAt = Date.now();
  }
  function callEnd() { CALL.active = false; CALL.speaker = false; CALL.muted = false; }
  function callSecs() {
    if (!CALL.active) return 0;
    return Math.max(0, Math.floor((Date.now() - CALL.startedAt) / 1000));
  }
  function callClock() {
    var s = callSecs();
    return ('0' + Math.floor(s / 60)).slice(-2) + ':' + ('0' + (s % 60)).slice(-2);
  }
  function callLabel() { return CALL.kind === 'share' ? '屏幕共享中' : '通话中'; }
  /* 流体云：页面层提供给外壳层的内容（app.js 的 phone() 会调） */
  K.activityPill = function () {
    if (!CALL.active) return '';
    /* 已经在通话页上就不用再提示了 */
    if ((location.hash || '').indexOf('#/call') === 0) return '';
    return '<a class="pill" data-nav="#/call' + (CALL.kind === 'share' ? '?state=share' : '') + '">'
      + '<span class="pill__ic">' + icon(CALL.kind === 'share' ? 'screen' : 'call', 13) + '</span>'
      + '<span class="pill__t">' + callLabel() + '</span>'
      + '<span class="pill__time" data-pill-time>' + callClock() + '</span>'
      + '<span class="pill__back">回到通话</span>'
      + '</a>';
  };
  K.activityPillTime = callClock;

  K.registerScreen({
    no: '05b', id: 'call', name: '实时语音通话页', route: '#/call', tab: null,
    purpose: '通话 / 屏幕共享页：叶青栩素材、状态、静音 / 扬声器 / 屏幕共享 / 挂断。可以后台（退出本页顶部留"流体云"提示）；说的话转成文字落到人人星。',
    out: ['#/chat'],
    states: CALL_STATES,
    render: function (ctx) {
      var s = ctx.state || 'ongoing';
      /* 状态以**模块级会话**为准，URL 只是入口 —— 这样从流体云点回来能还原现场 */
      if (s === 'share') CALL.kind = 'share';
      else if (CALL.kind !== 'share' || s === 'ongoing') CALL.kind = 'voice';
      if (s === 'muted') CALL.muted = true;
      if (s === 'speaker') CALL.speaker = true;
      if (s === 'ongoing' || s === 'connecting') { CALL.muted = false; CALL.speaker = false; }

      var connecting = s === 'connecting';
      var muted = !!CALL.muted;
      var spk = !!CALL.speaker;
      var share = CALL.kind === 'share';
      var status = connecting ? '正在连接…'
                 : (share ? '屏幕共享中' : '通话中')
                   + (muted ? ' · 已静音（示例）' : '')
                   + ' · <span data-calltime>' + callClock() + '</span>';

      return `
      <div class="screen screen--call">
        <div class="call">
          ${share
            ? '<div class="call__share">'
              + '<span class="call__share-ic">' + icon('screen', 26) + '</span>'
              + '<span class="call__share-t">正在共享这块屏幕（占位）</span>'
              + '<span class="call__share-s">真实共享需设备授权：授权后你在手机上做什么，叶青栩就能看到什么</span>'
              + '</div>'
            : '<div class="call__ava">'
              + ph('FOX_CHAT_AVATAR', { size: 118, tag: '叶青栩素材', state: connecting ? 'think' : 'talk' })
              + '</div>'}
          <div class="call__name">叶青栩</div>
          <div class="call__status">${connecting ? dots() : ''}<span>${status}</span></div>
          <div class="call__ctl">
            <button class="call__btn${muted ? ' is-on' : ''}" data-nav="#/call?state=${muted ? 'ongoing' : 'muted'}">
              ${icon('micoff', 20)}<span>静音</span>
            </button>
            <button class="call__btn${spk ? ' is-on' : ''}" data-nav="#/call?state=${spk ? 'ongoing' : 'speaker'}">
              ${icon('speaker', 20)}<span>扬声器</span>
            </button>
            <button class="call__btn${share ? ' is-on' : ''}" data-nav="#/call?state=${share ? 'ongoing' : 'share'}">
              ${icon('screen', 20)}<span>${share ? '停止共享' : '共享屏幕'}</span>
            </button>
          </div>
          <button class="call__hangup" data-hangup aria-label="${share ? '结束共享' : '挂断'}">
            ${icon('call', 26, 'call__hgi')}
          </button>
          <span class="call__hanglabel">${share ? '结束共享' : '挂断'}</span>
        </div>
        ${note('说的话会转成文字，直接落到人人星的聊天记录里（这一页不显示字幕）。'
          + '可以后台：退出这一页后顶部会留一条"流体云"提示，点一下就能回到通话。')}
      </div>`;
    },

    /* 会话状态、通话记录、说话转文字都在这里处理（页面本身不做字幕） */
    mount: function (root) {
      if (!CALL.active) callStart(CALL.kind);      /* 进这一页 = 建立会话 */

      /* 挂断 / 结束共享：先结束会话，再按 data-nav 回人人星 */
      var hg = root.querySelector('[data-hangup]');
      function onHang() { callEnd(); }
      if (hg) {
        hg.setAttribute('data-nav', '#/chat');
        hg.addEventListener('click', onHang);
      }

      /* 计时器走字（tabular-nums，宽度不变、不会抖） */
      var tEl = root.querySelector('[data-calltime]');
      var tickT = setInterval(function () { if (tEl) tEl.textContent = callClock(); }, 1000);
      /* 说话 → 文字：逐句写进人人星的聊天记录（这一页不显示） */
      var lines = [
        { who: 'ai', html: '喂？能听到吗？' },
        { who: 'me', html: '能，我在。' },
        { who: 'ai', html: '好，那我先说今天的事。' },
        { who: 'me', html: '嗯，你说。' },
        { who: 'ai', html: '你昨天说的那个展，周六开始。' },
        { who: 'me', html: '那就周六去。' }
      ];
      /* 同一次会话只记一条记录行（切静音/扬声器会重渲染，用时间戳防重复） */
      var now = Date.now();
      if (!CALL_LOGGED_AT || now - CALL_LOGGED_AT > 60000) {
        CALL_LOGGED_AT = now;
        pushLog({ who: 'sys', html: '📞 ' + callLabel() + '（示例）· 00:32', time: clockNow() });
      }
      var i = 0;
      var t = setInterval(function () {
        if (i >= lines.length) { clearInterval(t); return; }
        var L = lines[i++];
        pushLog({ who: L.who, html: L.html, time: clockNow() });
      }, 2600);
      return function () {
        clearInterval(t);
        clearInterval(tickT);
        if (hg) hg.removeEventListener('click', onHang);
      };
    }
  });

  /* =====================================================================
     12 表情包页 —— 你自己上传的贴图；上传后你与叶青栩都能用
     从首页网格进入，或从人人星「＋」菜单的「表情包」进入（选一张即发出）
     ===================================================================== */
  /* 表情包清单：由 assets.js 的 K.stickerList() 从素材清单读出来
     （tools/gen-assets.py 扫 _inbox/stickers/ 生成，白底已抠成透明）。
     清单为空（还没导素材）时才退回「表情 01…10」的占位标签，页面不会破。 */
  var STICKERS = (function () {
    var real = (K.stickerList && K.stickerList()) || [];
    if (real.length) return real;
    var fallback = [];
    for (var i = 1; i <= 10; i++) {
      var n = (i < 10 ? '0' : '') + i;
      fallback.push({ k: 's' + i, label: '表情 ' + n, group: '其他' });
    }
    return fallback;
  })();
  var STK_GROUPS = (function () {
    var seen = [];
    STICKERS.forEach(function (s) {
      if (seen.indexOf(s.group) < 0) seen.push(s.group);
    });
    return seen;
  })();

  K.registerScreen({
    no: '12', id: 'stickers', name: '表情包页', route: '#/stickers', tab: null,
    purpose: '用户上传的表情包：上传区（含尺寸 / 体积 / 格式限制）、贴图网格；点一张即作为消息发出，双方都能用。',
    out: ['#/home', '#/chat'],
    states: [{ key: 'default', label: '默认' }],
    render: function (ctx) {
      var q = ctx.params;
      var fromChat = q && q.get('from') === 'chat';
      /* n 是本次渲染的时间戳：从聊天进来时，回到本页再点同一张表情也能再发一次 */
      var nonce = Date.now();
      /* 从**首页**进来是"管理"：点一张只是选中，**不跳转**到人人星；
         从**聊天「＋」**进来才是"挑一张发出去"。
         按分组铺开（双人 → 叶青栩 → 小羊 → 配文），每组一个小标题 —— 一屏全铺开不好找。 */
      var tiles = STK_GROUPS.map(function (g) {
        var inGroup = STICKERS.filter(function (s) { return s.group === g; });
        var rows = inGroup.map(function (s) {
          var inner = '<span class="stk__art">' + K.sticker(s.k, { alt: s.label }) + '</span>'
            + '<span class="stk__size">' + esc(s.label) + '</span>';
          return fromChat
            ? '<a class="stk" data-label="' + esc(s.label) + '"'
              + ' data-nav="#/chat?state=replying&sticker=' + s.k + '&n=' + nonce + '">' + inner + '</a>'
            : '<button class="stk" type="button" data-pick="' + s.k + '"'
              + ' data-label="' + esc(s.label) + '">' + inner + '</button>';
        }).join('');
        return sectionTitle(g, '<span class="muted">' + inGroup.length + ' 张</span>')
          + '<div class="stkgrid">' + rows + '</div>';
      }).join('');

      return `
      <div class="screen">
        ${appbar({ title: '表情包', sub: fromChat ? '挑一张发出去 · 选中后回到聊天' : '上传一次 · 我和叶青栩都能用',
                   back: fromChat ? '#/chat' : '#/home' })}
        <div class="screen__body">
          ${fromChat ? '' : card(
            '<div class="stkup">'
            + '<span class="stkup__box">' + icon('plus', 20) + '</span>'
            + '<span class="stkup__main"><b>上传表情包</b>'
            + '<span>从相册选图，上传后我和叶青栩都能用</span></span>'
            + chip('待接入', 'warn')
            + '</div>'
            + '<div class="stkrule">'
            + '<div class="stkrule__row"><b>尺寸</b><span>240×240px（按微信表情的规格）</span></div>'
            + '<div class="stkrule__row"><b>体积</b><span>单张 ≤ 500KB</span></div>'
            + '<div class="stkrule__row"><b>格式</b><span>PNG / GIF（动图保留动画）</span></div>'
            + '<div class="stkrule__row"><b>超规格</b><span>超出尺寸或体积的图，上传时自动压缩</span></div>'
            + '</div>'
          , { tight: true })}
          ${sectionTitle('我的表情包', '<span class="muted">' + STICKERS.length + ' 张 · ' + STK_GROUPS.join(' / ') + '</span>')}
          ${tiles}
          ${fromChat
            ? '<div class="stkpick">挑一张就发出去，回到人人星。</div>'
            : '<div class="stkpick" data-stkpick>点一张选中（只在这里选，不跳页）；要发出去请用人人星输入栏上方的「表情包」。</div>'}
          ${fromChat
            ? note('挑一张就发到人人星。要上传或管理表情包，回到「表情包」页（首页网格进入）。')
            : note('表情包已接入 ' + STICKERS.length + ' 张（生成时自动抠掉白底）。发送入口在人人星输入栏上方的「表情包」。')}
        </div>
      </div>`;
    },

    /* 表情包页（从首页进来）：点一张只是选中，不跳转到人人星 */
    mount: function (root) {
      var picks = root.querySelectorAll('[data-pick]');
      if (!picks.length) return null;
      var hint = root.querySelector('[data-stkpick]');
      function onPick(e) {
        var el = e.currentTarget;
        for (var i = 0; i < picks.length; i++) picks[i].classList.remove('is-on');
        el.classList.add('is-on');
        if (hint) {
          /* 名字从 data-label 读 —— 换成真图后 .stk__art 里是 <img>，没有文字可取 */
          hint.textContent = '已选中「' + (el.getAttribute('data-label') || '') + '」；'
            + '要发出去请用人人星输入栏上方的「表情包」。';
        }
      }
      for (var i = 0; i < picks.length; i++) picks[i].addEventListener('click', onPick);
      return function () {
        for (var j = 0; j < picks.length; j++) picks[j].removeEventListener('click', onPick);
      };
    }
  });
})();

/* =====================================================================
   Kissne 手机端 UI · screens-a.js
   页面： 首页 / 聊天 / 小机星 / 通话 / 表情包
   ===================================================================== */
(function () {
  'use strict';
  var K = window.KSN;
  var ph = K.ph, btn = K.btn, icon = K.icon, chip = K.chip, appbar = K.appbar,
      card = K.card, field = K.field, tabbar = K.tabbar, modal = K.modal,
      note = K.note, sectionTitle = K.sectionTitle, listRow = K.listRow,
      banner = K.banner, kv = K.kv, esc = K.esc;

  /* =====================================================================
     04 首页 / 控制台
     ===================================================================== */
  var HOME_STATES = [
    { key: 'online', label: '自动状态（昼 / 夜按本机时间）' },
    { key: 'day',    label: '白天外观（强制）' },
    { key: 'night',  label: '夜晚外观（强制）' },
    { key: 'more',   label: '更多功能' }
  ];
  function dayPart(ctx) {
    if (ctx.state === 'day' || ctx.state === 'night') return ctx.state;
    var h = new Date().getHours();
    return (h >= 6 && h < 18) ? 'day' : 'night';
  }

  K.registerScreen({
    no: '04', id: 'home', name: '首页 / 控制台', route: '#/home', tab: 'entry',
    purpose: 'Kissne 入口页。启动后直接可用；认证、会话恢复与服务重连全部由 App 在后台自动完成。',
    out: ['#/chat', '#/universe', '#/memory', '#/skills', '#/mcp', '#/settings', '#/notifications'],
    states: HOME_STATES,
    render: function (ctx) {
      var part = dayPart(ctx);
      var head = `
        <header class="appbar appbar--brand">
          <div class="appbar__l"><span class="brand">Kissne</span></div>
          <div class="appbar__c"></div>
          <div class="appbar__r">
            <button class="iconbtn" data-nav="#/notifications" aria-label="通知">${icon('bell')}</button>
            <button class="iconbtn" data-nav="#/settings" aria-label="设置">${icon('gear')}</button>
          </div>
        </header>`;

      var stars = `
        <div class="starcards">
          <div class="starcard starcard--sheep" data-nav="#/chat">
            <div class="starcard__art">${ph('SHEEP_CHARACTER_RESERVED', { state: part })}</div>
          </div>
          <div class="starcard" data-nav="#/universe">
            <div class="starcard__art">${ph('FOX_HOME_CHARACTER', { state: part })}</div>
          </div>
        </div>`;

      var showMore = ctx.state === 'more';
      var APPS = showMore ? [
        { t: '语音设置', ic: 'mic',     to: '#/settings' },
        { t: '对话记录', ic: 'clock',   to: '#/sessions' },
        { t: '账号安全', ic: 'user',    to: '#/settings' },
        { t: '数据备份', ic: 'refresh', to: '#/settings' },
        { t: '关于',     ic: 'info',    to: '#/settings' },
        { t: '返回常用', ic: 'home',    to: '#/home' }
      ] : [
        { t: '浏览器',   ic: 'search', action: 'open-browser' },
        { t: '记忆库',   ic: 'memory', to: '#/memory' },
        { t: 'Skills',   ic: 'box',    to: '#/skills' },
        { t: 'MCP',      ic: 'link',   to: '#/mcp' },
        { t: '会话列表', ic: 'chat',   to: '#/sessions' },
        { t: '通知',     ic: 'bell',   to: '#/notifications' },
        { t: '运维',     ic: 'server', to: '#/admin' },
        { t: '设置',     ic: 'gear',   to: '#/settings' },
        { t: '表情包',   ic: 'smile',  to: '#/stickers' },
        { t: '更多',     ic: 'home',   to: '#/home?state=more' }
      ];
      var appgrid = '<div class="appgrid">' + APPS.map(function (a) {
        return '<a class="appgrid__item"' + (a.action ? ' data-action="' + a.action + '"' : ' data-nav="' + a.to + '"') + '>'
          + '<span class="appgrid__ic">' + icon(a.ic, 21) + '</span>'
          + '<span class="appgrid__label">' + a.t + '</span></a>';
      }).join('') + '</div>';

      return `
      <div class="screen screen--home">
        ${head}
        <div class="screen__body">
          ${stars}
          ${sectionTitle(showMore ? '更多功能' : '全部功能')}
          ${appgrid}
          <div class="motifrow">${icon('paw', 15)}${icon('hoof', 15)}${icon('paw', 15)}</div>
        </div>
      </div>`;

    }
  });

  /* =====================================================================
     05 聊天页
     ===================================================================== */
  var CHAT_STATES = [
    { key: 'normal',         label: '对话' },
    { key: 'empty',          label: '空聊天' },
    { key: 'search',         label: '历史搜索' },
    { key: 'failed',         label: '发送失败' },
    { key: 'request-enter',  label: '小机星进入请示' },
    { key: 'plus-menu',      label: '更多操作' },
    { key: 'provider-menu',  label: '供应商选择' },
    { key: 'model-menu',     label: '模型选择' },
    { key: 'effort-menu',    label: '思考强度' }
  ];

  var CURRENT_SESSION_ID = '';
  var CURRENT_SESSION_KEY = '';

  function remoteSessions() {
    var idx = window.KissneSessionIndex || {};
    return Array.isArray(idx.sessions) ? idx.sessions : [];
  }
  function sessionIsCurrent(s) {
    if (!s) return false;
    if (CURRENT_SESSION_ID) return String(s.id || '') === CURRENT_SESSION_ID;
    if (CURRENT_SESSION_KEY) return String(s.key || '') === CURRENT_SESSION_KEY;
    return !!s.active;
  }
  function sessionMetaText(s, active) {
    if (active) return '当前会话';
    var parts = [];
    if (s && s.messageCount) parts.push(s.messageCount + ' 条消息');
    if (s && s.updatedAt) {
      var d = new Date(s.updatedAt);
      parts.push(isNaN(d.getTime()) ? String(s.updatedAt) : d.toLocaleString([], { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }));
    }
    return parts.join(' · ') || '服务器会话';
  }
  function sessionDrawerHtml() {
    var idx = window.KissneSessionIndex || {};
    var sessions = remoteSessions();
    var body = '';
    if (!idx.loaded && idx.error) {
      body = '<div class="sessiondrawer__empty">暂时无法读取服务器会话列表</div>';
    } else if (!sessions.length) {
      body = '<div class="sessiondrawer__empty">服务器暂无会话</div>';
    } else {
      body = sessions.map(function (s) {
        var active = sessionIsCurrent(s);
        return '<div class="sessiondrawer__item' + (active ? ' is-active' : '') + '"'
          + ' data-session-key="' + esc(s.key) + '" data-session-id="' + esc(s.id) + '">'
          + '<button type="button" class="sessiondrawer__select" data-session-select'
          + ((s.key || s.id) ? '' : ' disabled') + '>'
          + '<span class="sessiondrawer__title">' + esc(s.title || '未命名会话') + '</span>'
          + '<span class="sessiondrawer__meta">' + esc(sessionMetaText(s, active)) + '</span></button>'
          + (active ? '' : '<button type="button" class="sessiondrawer__delete" data-session-delete aria-label="删除会话">删除</button>')
          + '</div>';
      }).join('');
    }
    return '<div class="sessiondrawer__scrim" data-session-drawer-close hidden></div>'
      + '<aside class="sessiondrawer" data-session-drawer-panel hidden>'
      + '<div class="sessiondrawer__head"><span>会话</span>'
      + '<button type="button" class="iconbtn" data-session-refresh aria-label="刷新会话">' + icon('refresh', 16) + '</button></div>'
      + '<div class="sessiondrawer__list" data-session-list>' + body + '</div>'
      + '</aside>';
  }

  /* —— 模型 / 思考强度：完全由 Hermes canonical mobile controls 提供 ——
     App 不维护模型名或 reasoning ladder。/model-options 的数据源来自
     Hermes provider catalog + agent.reasoning_effort.EFFORT_LADDER；
     /set-model 委托给 Gateway 的 canonical /model / /reasoning handlers。 */
  var PROVIDERS = [
    { k: '', v: '读取中…', d: '正在从 Hermes 获取供应商' }
  ];
  var MODELS = [
    { k: '', v: '读取中…', d: '正在从 Hermes 获取模型', p: '' }
  ];
  var EFFORTS = [
    { k: '', v: '读取中…', d: '正在从 Hermes 获取思考强度' }
  ];
  var PROVIDER_CURRENT = '';
  var MODEL_CURRENT = '';
  var EFFORT_CURRENT = '';
  var MODEL_OPTIONS_LOADING = false;
  var MODEL_OPTIONS_LOADED_AT = 0;
  var MODEL_OPTIONS_ERROR = '';

  function pick(list, key, fallback) {
    for (var i = 0; i < list.length; i++) { if (list[i].k === key) return list[i]; }
    for (var j = 0; j < list.length; j++) { if (list[j].k === fallback) return list[j]; }
    return list[0] || { k: '', v: '—', d: '' };
  }

  function applyHermesModelOptions(payload) {
    payload = payload || {};
    var currentModel = String(payload.model || payload.current_model || MODEL_CURRENT || '').trim();
    var reportedCurrentProvider = String(payload.provider || payload.current_provider || '').trim();
    var providerRows = Array.isArray(payload.providers) ? payload.providers : [];
    var nextProviders = [];
    var nextModels = [];

    if (providerRows.length) {
      providerRows.forEach(function (raw) {
        raw = raw || {};
        var slug = String(raw.slug || raw.provider || raw.id || '').trim();
        if (!slug) return;
        var name = String(raw.name || raw.label || slug).trim() || slug;
        var models = Array.isArray(raw.models) ? raw.models : [];
        nextProviders.push({
          k: slug,
          v: name,
          d: String(raw.warning || ((raw.total_models != null ? raw.total_models : models.length) + ' 个模型')),
          current: !!raw.is_current
        });
        models.forEach(function (entry) {
          var model = typeof entry === 'string'
            ? String(entry || '').trim()
            : String((entry || {}).model || (entry || {}).id || (entry || {}).value || '').trim();
          if (!model) return;
          var key = slug + '::' + model;
          var label = typeof entry === 'string'
            ? model
            : String((entry || {}).label || model);
          if (label.indexOf(slug + '/') === 0) label = label.slice(slug.length + 1);
          nextModels.push({ k: key, raw: model, v: label, d: name, p: slug });
        });
      });
      if (!reportedCurrentProvider) {
        var currentRow = nextProviders.filter(function (p) { return p.current; })[0];
        if (currentRow) reportedCurrentProvider = currentRow.k;
      }
    } else {
      /* Compatibility with older Mobile control payloads. */
      var providerLabels = Object.create(null);
      nextModels = (payload.models || []).map(function (item) {
        if (typeof item === 'string') {
          var value = String(item || '').trim();
          if (!value) return null;
          var slash = value.indexOf('/');
          var provider = slash > 0 ? value.slice(0, slash) : '';
          var label = slash > 0 ? value.slice(slash + 1) : value;
          if (!provider && value === currentModel && reportedCurrentProvider) provider = reportedCurrentProvider;
          if (provider) providerLabels[provider] = provider;
          return { k: (provider ? provider + '::' : '') + value, raw: value, v: label, d: provider || 'Hermes', p: provider };
        }
        item = item || {};
        var provider = String(item.provider || item.provider_slug || item.provider_id || '').trim();
        var model = String(item.model || item.id || item.value || '').trim();
        if (!model) return null;
        if (!provider && model.indexOf('/') > 0) provider = model.slice(0, model.indexOf('/'));
        if (!provider && model === currentModel && reportedCurrentProvider) provider = reportedCurrentProvider;
        var key = (provider ? provider + '::' : '') + model;
        var providerLabel = String(item.provider_label || provider || '').trim();
        if (provider) providerLabels[provider] = providerLabel || provider;
        return {
          k: key,
          raw: model,
          v: String(item.label || model || key),
          d: providerLabel || provider || 'Hermes',
          p: provider
        };
      }).filter(function (item) { return !!(item && item.k); });
      nextProviders = Object.keys(providerLabels).map(function (key) {
        var count = nextModels.filter(function (m) { return m.p === key; }).length;
        return { k: key, v: providerLabels[key] || key, d: count + ' 个模型' };
      });
    }

    var nextEfforts = (payload.efforts || payload.reasoning_efforts || []).map(function (item) {
      if (typeof item === 'string') {
        var value = String(item || '').trim();
        return { k: value, v: value, d: 'Hermes reasoning effort' };
      }
      item = item || {};
      var value = String(item.value || item.key || item.effort || '');
      return { k: value, v: String(item.label || value), d: 'Hermes reasoning effort' };
    }).filter(function (item) { return !!item.k; });

    PROVIDERS = nextProviders.length
      ? nextProviders
      : [{ k: '', v: '暂无供应商', d: 'Hermes Dashboard 未返回可选供应商' }];
    MODELS = nextModels.length
      ? nextModels
      : [{ k: '', raw: '', v: '暂无可用模型', d: 'Hermes 未返回可用模型', p: '' }];
    EFFORTS = nextEfforts.length
      ? nextEfforts
      : [{ k: '', v: '暂无可用档位', d: 'Hermes 未返回 reasoning ladder' }];

    MODEL_CURRENT = currentModel;
    var currentMatch = MODELS.filter(function (m) {
      if (reportedCurrentProvider && m.p === reportedCurrentProvider && m.raw === currentModel) return true;
      return !reportedCurrentProvider && (m.raw === currentModel || m.k === currentModel);
    })[0];
    PROVIDER_CURRENT = reportedCurrentProvider || (currentMatch && currentMatch.p) || '';
    if (!PROVIDER_CURRENT) {
      var marked = PROVIDERS.filter(function (p) { return p.current; })[0];
      PROVIDER_CURRENT = marked ? marked.k : '';
    }
    if (currentMatch) MODEL_CURRENT = currentMatch.k;
    EFFORT_CURRENT = String(payload.effort || payload.current_effort || EFFORT_CURRENT || '');
    MODEL_OPTIONS_ERROR = '';
    MODEL_OPTIONS_LOADED_AT = Date.now();
  }

  function modelsForProvider(provider) {
    var p = String(provider || '');
    var filtered = p ? MODELS.filter(function (m) { return m.p === p; }) : MODELS.slice();
    return filtered.length ? filtered : MODELS.slice();
  }

  function dropdown(title, items, curKey, param, origin) {
    return '<div class="dd">'
      + '<div class="dd__head"><span>' + esc(title) + '</span></div>'
      + '<div class="dd__list">' + items.map(function (it) {
          var disabled = !it.k;
          return '<button type="button" class="dd__item' + (it.k === curKey ? ' is-active' : '') + '"'
            + (disabled ? ' disabled' : '')
            + ' data-hermes-control="' + esc(param) + '"'
            + ' data-hermes-value="' + esc(it.k) + '"'
            + ' data-hermes-origin="' + esc(origin) + '">'
            + '<span class="dd__main"><span class="dd__v">' + esc(it.v) + '</span>'
            + '<span class="dd__d">' + esc(it.d) + '</span></span>'
            + (it.k === curKey ? icon('check', 16) : '') + '</button>';
        }).join('') + '</div>'
      + (MODEL_OPTIONS_ERROR ? '<div class="dd__foot">' + esc(MODEL_OPTIONS_ERROR) + '</div>' : '')
      + '</div>';
  }

  function modelPicker(providerKey, modelKey) {
    var selectedProvider = String(providerKey || PROVIDER_CURRENT || (PROVIDERS[0] && PROVIDERS[0].k) || '');
    var visible = modelsForProvider(selectedProvider);
    return '<div class="modelpick" role="dialog" aria-label="切换供应商和模型">'
      + '<div class="modelpick__col modelpick__providers">'
      + '<div class="modelpick__head">供应商</div>'
      + '<div class="modelpick__list">'
      + PROVIDERS.map(function (p) {
          return '<button type="button" class="modelpick__row' + (p.k === selectedProvider ? ' is-active' : '') + '"'
            + (!p.k ? ' disabled' : '')
            + ' data-provider-pick="' + esc(p.k) + '">'
            + '<span class="modelpick__main">' + esc(p.v) + '</span>'
            + '<span class="modelpick__sub">' + esc(p.d || '') + '</span></button>';
        }).join('')
      + '</div></div>'
      + '<div class="modelpick__col modelpick__models">'
      + '<div class="modelpick__head">模型</div>'
      + '<div class="modelpick__list">'
      + (visible.length ? visible.map(function (m) {
          var active = m.k === modelKey || (m.p === PROVIDER_CURRENT && m.k === MODEL_CURRENT);
          return '<button type="button" class="modelpick__row' + (active ? ' is-active' : '') + '"'
            + (!m.k ? ' disabled' : '')
            + ' data-hermes-control="model" data-hermes-provider="' + esc(selectedProvider) + '"'
            + ' data-hermes-key="' + esc(m.k) + '" data-hermes-value="' + esc(m.raw) + '" data-hermes-origin="normal">'
            + '<span class="modelpick__main">' + esc(m.v) + '</span>'
            + (active ? icon('check', 14) : '') + '</button>';
        }).join('') : '<div class="modelpick__empty">这个供应商当前没有可用模型</div>')
      + '</div></div>'
      + (MODEL_OPTIONS_ERROR ? '<div class="modelpick__foot">' + esc(MODEL_OPTIONS_ERROR) + '</div>' : '')
      + '</div>';
  }

  /* 「+」点开后的浮层：**紧贴加号上方**弹出的小框（不是从屏幕底端滑上来的面板）。
     只剩照片 / 文件两个占位入口 —— 表情包 / 语音通话 / 屏幕共享已移到
     输入框上方的磁吸快捷条（.quickbar），不再藏在「＋」里。 */
  function plusPopLayer(origin) {
    var items = [
      { ic: 'image', t: '照片', d: '从相册选择并发送原图', kind: 'photo' },
      { ic: 'file',  t: '文件', d: '选择文档、压缩包等并发送', kind: 'file' }
    ];
    return '<div class="pop" data-plus-panel hidden>'
      + items.map(function (it) {
          return '<button type="button" class="pop__item" data-attachment-kind="' + it.kind + '">'
            + '<span class="pop__ic">' + icon(it.ic, 16) + '</span>'
            + '<span class="pop__txt"><b>' + esc(it.t) + '</b><small>' + esc(it.d) + '</small></span></button>';
        }).join('')
      + '</div>';
  }

  function attachmentMsg(meta, kind, status, localId) {
    meta = meta || {};
    var name = String(meta.file_name || meta.name || (kind === 'photo' ? '照片' : '文件'));
    var size = Number(meta.size || 0);
    var sizeText = size > 0 ? (size >= 1048576 ? (size / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(size / 1024)) + ' KB') : '';
    var state = String(status || 'sent');
    var statusText = state === 'sending' ? '正在发送…' : (state === 'failed' ? '发送失败' : '已发送');
    return '<span class="attachmsg attachmsg--' + esc(state) + '"' + (localId ? ' data-attachment-id="' + esc(localId) + '"' : '') + '>'
      + '<span class="attachmsg__ic">' + icon(kind === 'photo' ? 'image' : 'file', 19) + '</span>'
      + '<span class="attachmsg__body"><b>' + esc(name) + '</b>'
      + (sizeText ? '<small>' + esc(sizeText) + '</small>' : '')
      + '<small class="attachmsg__status">' + esc(statusText) + '</small></span>'
      + (state === 'sending' ? '<span class="attachmsg__spin" aria-hidden="true"></span>' : '')
      + '</span>';
  }

  var AVA_STATES = {
    idle:     '平静',        /* 兜底：普通消息、闲着 */
    read:     '正在看消息',  /* 已接收这一批用户消息，尚未产生 reasoning/tool/text */
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
  function assistantBubbleHtml(html, cls) {
    var parts = String(html == null ? '' : html).split(/\\n\\s*\\n+/).filter(function (part) {
      return !!String(part || '').trim();
    });
    if (!parts.length) parts = [''];
    return parts.map(function (part) {
      return '<div class="msg__text bubble' + (cls ? ' ' + cls : '') + '">' + part + '</div>';
    }).join('');
  }
  function aiMsg(html, cls, time, tag, state, activity) {
    return '<div class="msg msg--ai" data-chat-message data-message-text="' + esc(String(html || '').replace(/<[^>]*>/g, ' ')) + '">' + ava('FOX_CHAT_AVATAR', tag, state)
      + '<div class="msg__body">' + (activity || '')
      + assistantBubbleHtml(html, cls)
      + '<span class="msg__time">' + (time || '09:41') + '</span></div>'
      + '</div>';
  }
  /* 「我」这一侧：头像是**小羊**（人人星）。
     状态词表和狐狸共用一套（AVA_STATES），缺图自动回落兜底那张平静脸。

     MY_AVA 是**模块级**的当前表情 —— 渲染时按页面状态写一次，meMsg 默认读它，
     省得每个调用点都传一个参数（和 UNREAD / LAST_SENT_HASH 一个路子）：
       设备离线 / 断网 = 人不在 → 睡着；上一条没发出去 → 委屈；其余平静。 */
  var MY_AVA = 'idle';
  function meMsg(html, meta, time, state) {
    return '<div class="msg msg--me" data-chat-message data-message-text="' + esc(String(html || '').replace(/<[^>]*>/g, ' ')) + '">' + ava('USER_AVATAR', '我', state || MY_AVA)
      + '<div class="msg__body"><div class="bubble">' + html + '</div>'
      + (meta ? '<div class="msg__meta">' + meta + '</div>' : '')
      + '<span class="msg__time">' + (time || '09:41') + '</span></div>'
      + '</div>';
  }
  function dots() { return '<span class="dots"><i></i><i></i><i></i></span>'; }

  /* 思考过程与工具调用共用一个折叠区。
     没有真实 reasoning/tool 事件时不创建折叠区，也不伪造“正在思考”。 */
  function cleanActivityText(value, fallback) {
    var text = String(value == null ? '' : value);
    try {
      text = text.replace(/[\p{Extended_Pictographic}\uFE0F\u200D]/gu, '');
    } catch (e) {
      text = text.replace(/[\u2600-\u27BF\uD83C-\uDBFF\uDC00-\uDFFF\uFE0F\u200D]/g, '');
    }
    text = text.replace(/[ \t]+\n/g, '\n').replace(/\n[ \t]+/g, '\n').trim();
    return text || String(fallback || '');
  }

  function toolActivityLabel(value) {
    var text = cleanActivityText(value, '');
    var low = text.toLowerCase();
    if (!low) return '使用工具';
    if (/sticker|表情包/.test(low) && /grep|rg|find|search|terminal/.test(low)) return '查找表情包发送逻辑';
    if (/adapter\.py|mobile adapter|kissne_mobile/.test(low) && /read|reading|sed|cat|grep|rg/.test(low)) return '检查 Mobile Adapter';
    if (/screens-a\.js|chat|bubble|message/.test(low) && /read|reading|sed|cat|grep|rg/.test(low)) return '检查聊天界面逻辑';
    if (/\bgit\s+log\b|commit history|history/.test(low)) return '检查 Git 历史';
    if (/\bgit\s+(status|diff|show)\b/.test(low)) return '检查 Git 状态';
    if (/pytest|gradle|lint|\btests?\b/.test(low)) return '运行相关检查';
    var fileMatches = Array.from(text.matchAll(/(?:Reading|read|cat|sed[^\\n]*|open)\\s+([^\\s"']+\\.(?:py|js|ts|kt|css|html|md))/gi));
    var file = fileMatches.length ? fileMatches[fileMatches.length - 1] : null;
    if (file && file[1]) return '读取 ' + file[1].split('/').pop();
    var pattern = text.match(/(?:grep|rg)\s+(?:-[^\s]+\s+)*(?:"([^"]+)"|'([^']+)'|([^\s|]+))/i);
    if (pattern) {
      var term = String(pattern[1] || pattern[2] || pattern[3] || '').replace(/[_*\\]/g, '').trim();
      if (term && term.length <= 18) return '查找「' + term + '」相关代码';
    }
    if (/\b(find|grep|rg|ripgrep|search|locate)\b/.test(low)) return '查找相关文件';
    if (/\b(cat|head|tail|sed|read|reading|open|fetch_file)\b/.test(low)) return '读取代码';
    if (/\b(git|github|commit|branch|pull request|pr\b)/.test(low)) return '检查 Git';
    if (/\b(write|edit|patch|update_file|create_file|replace)\b/.test(low)) return '修改文件';
    if (/\b(web|browser|curl|http|https|fetch)\b/.test(low)) return '访问网络';
    if (/\b(terminal|shell|bash|sh|python|node|npm|pnpm|yarn)\b/.test(low)) return '运行命令';
    return '使用工具';
  }
  function toolActivityIcon(label) {
    if (label === '搜索文件') return 'search';
    if (label === '读取代码' || label === '修改文件') return 'file';
    if (label === '检查 Git') return 'link';
    if (label === '访问网络') return 'server';
    if (label === '运行检查' || label === '运行命令') return 'cpu';
    return 'box';
  }
  function activityDetailText(value) {
    var text = cleanActivityText(value, '');
    text = text.replace(/```[a-z0-9_-]*\s*/gi, '').replace(/```/g, '').trim();
    text = text.replace(/((?:api[_-]?key|token|secret|password)\s*[:=]\s*)[^\s'"]+/gi, '$1[已隐藏]');
    text = text.replace(/(authorization\s*[:=]\s*bearer\s+)[^\s'"]+/gi, '$1[已隐藏]');
    if (text.length > 1200) text = text.slice(0, 1200) + '…';
    return text;
  }

  function looksLikeToolTranscript(value) {
    var text = cleanActivityText(value, '').trim();
    return /^\`\`\`\s*(terminal|find|tool|shell-command)\b/i.test(text)
      || /^(terminal|tool)\s*[:：]?/i.test(text)
      || /\bterminal\b[\s\S]*?\`\`\`/i.test(text)
      || /^\s*(find|rg|grep)\s+[^\n]+$/i.test(text)
      || /^\s*git\s+(status|log|diff|show|branch)\b/i.test(text)
      || /(?:^|\n)Reading\s+[^\n]+\s+L\d+/i.test(text)
      || /^\s*[🐍]?\s*Running code from\s+hermes_tools_import\b/i.test(text);
  }

  function looksLikeRuntimeControl(value) {
    var text = cleanActivityText(value, '').trim();
    return /^\s*[⚡]?\s*Interrupting current task\b/i.test(text)
      || /^\s*I'll respond to your message shortly\.?\s*$/i.test(text);
  }

  var CHAT_LOG = [];
  /* 本地聊天缓存按会话隔离：
     - CHAT_LOG_SESSION = 内存里的 CHAT_LOG 属于哪个会话（session id，缺省回退 session key）
     - 会话身份未落定时不读也不写 localStorage —— 宁可不恢复旧缓存，也绝不串会话
     - 旧的全局 key kissne.chat.local_log.v1 已废弃：永不读取（迁移保护，不向任何会话灌入） */
  var CHAT_LOG_SESSION = '';
  function chatLogSessionId() {
    return String(CURRENT_SESSION_ID || CURRENT_SESSION_KEY || '');
  }
  function chatLogStorageKeyFor(sessionId) {
    var sid = String(sessionId || '');
    if (!sid) return '';
    return 'kissne.chat.local_log.v2:' + sid;
  }
  function persistChatLog() {
    try {
      var sid = String(CHAT_LOG_SESSION || '');
      var key = chatLogStorageKeyFor(sid);
      if (!key) return; /* 未绑定会话时不落盘，避免写进错误会话 */
      var safe = CHAT_LOG.slice(-240).map(function (m, index) {
        return {
          who: m.who, html: m.html, cls: m.cls || '', meta: m.meta || '', time: m.time || '',
          day: m.day || '', sortAt: m.sortAt || m.createdAt || 0, messageRef: m.messageRef || '', turnId: m.turnId || '',
          localOwned: !!m.localOwned, optimistic: !!m.optimistic, localOnly: !!m.localOnly,
          stableOrder: Number(m._stableOrder != null ? m._stableOrder : index),
          sid: sid
        };
      });
      localStorage.setItem(key, JSON.stringify(safe));
    } catch (e) {}
  }
  function loadChatLogFor(sessionId) {
    var sid = String(sessionId || '');
    var rows = [];
    try {
      var key = chatLogStorageKeyFor(sid);
      if (!key) return rows;
      var raw = localStorage.getItem(key);
      var parsed = raw ? JSON.parse(raw) : [];
      if (!Array.isArray(parsed)) return rows;
      parsed.forEach(function (m) {
        if (!m || !/^(me|ai|sys)$/.test(String(m.who || ''))) return;
        if (m.sid && String(m.sid) !== sid) return; /* 行必须属于该会话 */
        if (m._stableOrder == null && m.stableOrder != null) m._stableOrder = Number(m.stableOrder);
        rows.push(m);
      });
      rows = rows.slice(-240);
    } catch (e) {}
    return rows;
  }
  /* 把内存日志绑定到某个会话：先解绑再装入目标会话的缓存。
     绑定到同一会话是 no-op，不会冲掉刚写进内存的消息。 */
  function bindChatLogSession(sessionId) {
    var sid = String(sessionId || '');
    if (sid === CHAT_LOG_SESSION) return;
    /* Flush the old namespace before replacing the in-memory array. UI rerenders
       must never turn a route/menu tap into an implicit history clear. */
    if (CHAT_LOG_SESSION) persistChatLog();
    CHAT_LOG_SESSION = sid;
    CHAT_LOG.length = 0;
    loadChatLogFor(sid).forEach(function (m) { CHAT_LOG.push(m); });
    sortChatLogChronologically();
  }
  /* Human-style composer: every tap creates its own visible bubble. The 1.6s value is only a
     maximum coalescing guard; actual drain follows live composer typing state. Messages sent while
     the AI is active steer the work without surfacing a fake user-visible "stopped" reply. */
  var CHAT_OUTBOX = [];
  var CHAT_OUTBOX_BUSY = false;
  var CHAT_OUTBOX_RETRY = null;
  var CHAT_OUTBOX_UPDATED_AT = 0;
  var CHAT_USER_INPUT_AT = 0;
  var FINAL_ACTIVITY_BY_TEXT = Object.create(null);
  var TURN_ACTIVITY_STORAGE_BASE = 'kissne.chat.turn_activity.v4:';
  var TURN_ACTIVITY_SESSION = '';
  var TURN_ACTIVITY = Object.create(null);
  function turnActivityStorageKeyFor(sessionId) {
    var sid = String(sessionId || '');
    return sid ? TURN_ACTIVITY_STORAGE_BASE + sid : '';
  }
  function bindTurnActivitySession(sessionId) {
    var sid = String(sessionId || '');
    if (sid === TURN_ACTIVITY_SESSION) return;
    TURN_ACTIVITY_SESSION = sid;
    TURN_ACTIVITY = Object.create(null);
    loadTurnActivity(sid);
  }

  function toolCallKey(value, fallbackIndex) {
    var row = value && typeof value === 'object' ? value : {};
    return cleanActivityText(
      row.tool_call_id || row.call_id || row.id || row.tool_id || '',
      ''
    ) || ('tool:' + String(row.index != null ? row.index : (fallbackIndex || 0)));
  }
  function toolCallStatus(value, fallback) {
    var raw = cleanActivityText(value, '').toLowerCase();
    if (/fail|error|denied|reject/.test(raw)) return 'failed';
    if (/complete|completed|done|success|ok|result/.test(raw)) return 'completed';
    if (/running|progress|start|pending|call/.test(raw)) return 'running';
    return fallback || 'running';
  }
  function activityForTurn(turnId) {
    var id = String(turnId || 'pending');
    if (!TURN_ACTIVITY[id]) {
      TURN_ACTIVITY[id] = { reasoning: false, reasoningText: '', toolOrder: [], toolCalls: {}, done: false, updatedAt: Date.now() };
    }
    var state = TURN_ACTIVITY[id];
    if (typeof state.reasoningText !== 'string') state.reasoningText = '';
    if (!Array.isArray(state.toolOrder)) state.toolOrder = [];
    if (!state.toolCalls || typeof state.toolCalls !== 'object') state.toolCalls = {};
    return state;
  }
  function loadTurnActivity(sessionId) {
    try {
      var keyName = turnActivityStorageKeyFor(sessionId || TURN_ACTIVITY_SESSION);
      if (!keyName) return;
      var raw = localStorage.getItem(keyName);
      var parsed = raw ? JSON.parse(raw) : {};
      if (!parsed || typeof parsed !== 'object') return;
      Object.keys(parsed).slice(-120).forEach(function (id) {
        var row = parsed[id];
        if (!row || typeof row !== 'object') return;
        var state = activityForTurn(id);
        state.reasoning = !!row.reasoning;
        state.reasoningText = activityDetailText(row.reasoningText || '');
        state.done = !!row.done;
        state.updatedAt = Number(row.updatedAt) || 0;
        (Array.isArray(row.toolOrder) ? row.toolOrder : []).slice(-24).forEach(function (key) {
          var tool = row.toolCalls && row.toolCalls[key];
          if (!tool || typeof tool !== 'object') return;
          state.toolOrder.push(String(key));
          state.toolCalls[String(key)] = {
            id: String(tool.id || key),
            name: cleanActivityText(tool.name || '', ''),
            label: cleanActivityText(tool.label || '', '使用工具'),
            detail: activityDetailText(tool.detail || ''),
            result: activityDetailText(tool.result || ''),
            status: toolCallStatus(tool.status, 'completed')
          };
        });
      });
    } catch (e) {}
  }
  function persistTurnActivity() {
    try {
      var ids = Object.keys(TURN_ACTIVITY).sort(function (a, b) {
        return (Number(TURN_ACTIVITY[a] && TURN_ACTIVITY[a].updatedAt) || 0)
          - (Number(TURN_ACTIVITY[b] && TURN_ACTIVITY[b].updatedAt) || 0);
      });
      while (ids.length > 120) delete TURN_ACTIVITY[ids.shift()];
      var keyName = turnActivityStorageKeyFor(TURN_ACTIVITY_SESSION);
      if (keyName) localStorage.setItem(keyName, JSON.stringify(TURN_ACTIVITY));
    } catch (e) {}
  }

  function upsertToolActivity(turnId, value, phase) {
    var state = activityForTurn(turnId);
    var row = value && typeof value === 'object' ? value : { detail: value };
    var key = toolCallKey(row, state.toolOrder.length);
    var current = state.toolCalls[key];
    if (!current) {
      current = {
        id: key,
        name: '',
        label: '',
        detail: '',
        result: '',
        status: 'running'
      };
      state.toolCalls[key] = current;
      state.toolOrder.push(key);
      if (state.toolOrder.length > 24) {
        var dropped = state.toolOrder.shift();
        delete state.toolCalls[dropped];
      }
    }
    current.name = cleanActivityText(row.tool_name || row.tool || row.function_name || current.name, current.name);
    current.label = cleanActivityText(row.label || '', current.label)
      || toolActivityLabel(current.name || row.detail || row.preview || value);
    var detail = activityDetailText(row.arguments || row.detail || row.preview || '');
    var result = activityDetailText(row.result || row.output || '');
    if (detail) current.detail = detail;
    if (result) current.result = result;
    current.status = toolCallStatus(row.status || phase, phase === 'result' ? 'completed' : 'running');
    if (phase === 'result' && current.status === 'running') current.status = 'completed';
    state.updatedAt = Date.now();
    persistTurnActivity();
    return true;
  }
  function appendActivity(turnId, kind, value) {
    var state = activityForTurn(turnId);
    if (kind === 'reasoning') {
      var reasoningText = activityDetailText(value || '');
      state.reasoning = true;
      if (reasoningText) {
        /* Reasoning may stream in cumulative snapshots or incremental chunks.
           Replace cumulative snapshots; append genuinely new chunks. */
        if (!state.reasoningText) state.reasoningText = reasoningText;
        else if (reasoningText.indexOf(state.reasoningText) === 0) state.reasoningText = reasoningText;
        else if (state.reasoningText.indexOf(reasoningText) < 0) state.reasoningText += '\n' + reasoningText;
      }
      state.updatedAt = Date.now();
      persistTurnActivity();
      return true;
    }
    return upsertToolActivity(turnId, value, kind === 'tool_result' ? 'result' : 'call');
  }
  function activityRows(state, closed) {
    var rows = [];
    if (state.reasoning) {
      rows.push('<div class="activity-item">'
        + '<button type="button" class="activity-row activity-row--reasoning" data-activity-toggle aria-expanded="false">'
        + '<span class="activity-label">' + (closed ? '思考' : '正在思考') + '</span>'
        + icon('chevron', 12, 'activity-chevron') + '</button>'
        + '<div class="activity-detail" hidden>' + esc(state.reasoningText || (closed ? '已完成这一步处理。' : '正在分析并处理当前请求。')) + '</div></div>');
    }
    (state.toolOrder || []).forEach(function (key) {
      var tool = state.toolCalls[key];
      if (!tool) return;
      var status = closed && tool.status === 'running' ? 'completed' : tool.status;
      var statusText = status === 'failed' ? '失败' : (status === 'completed' ? '完成' : '进行中');
      var detail = tool.detail || tool.name || tool.label || '工具调用';
      if (tool.result) detail += '\n\n结果：' + tool.result;
      var meta = tool.name ? '<span class="activity-toolname">' + esc(tool.name) + '</span>' : '';
      rows.push('<div class="activity-item activity-item--' + esc(status) + '" data-tool-call-id="' + esc(tool.id || key) + '">'
        + '<button type="button" class="activity-row" data-activity-toggle aria-expanded="false">'
        + '<span class="activity-statusdot" aria-hidden="true"></span>'
        + '<span class="activity-icon">' + icon(toolActivityIcon(tool.label), 13) + '</span>'
        + '<span class="activity-copy"><span class="activity-label">' + esc(tool.label || '使用工具') + '</span>' + meta + '</span>'
        + '<span class="activity-count">' + esc(statusText) + '</span>'
        + icon('chevron', 12, 'activity-chevron') + '</button>'
        + '<div class="activity-detail" hidden>' + esc(detail) + '</div></div>');
    });
    return rows.join('');
  }
  function activityMarkupForTurn(turnId, done) {
    var id = String(turnId || 'pending');
    var state = activityForTurn(id);
    var closed = done === true || state.done === true;
    var rows = activityRows(state, closed);
    if (!rows) return '';
    return '<div class="activity-stream' + (closed ? ' is-done' : '') + '" data-activity-turn="' + esc(id) + '">'
      + rows + '</div>';
  }
  function rememberFinalActivity(text, turnId) {
    var raw = String(text || '');
    if (!raw) return '';
    var state = activityForTurn(turnId);
    state.done = true;
    state.toolOrder.forEach(function (key) {
      var tool = state.toolCalls[key];
      if (tool && tool.status === 'running') tool.status = 'completed';
    });
    state.updatedAt = Date.now();
    persistTurnActivity();
    var html = activityMarkupForTurn(turnId, true);
    if (html) FINAL_ACTIVITY_BY_TEXT[raw] = html;
    else delete FINAL_ACTIVITY_BY_TEXT[raw];
    return html;
  }

  function stickerMatch(query) {
    var q = String(query == null ? '' : query).trim();
    if (!q || !STICKERS || !STICKERS.length) return null;
    for (var i = 0; i < STICKERS.length; i++) {
      if (STICKERS[i].label === q || STICKERS[i].k === q) return STICKERS[i];
    }
    var compact = q.replace(/\s+/g, '').toLowerCase();
    var aliases = {
      '开心': 'fox-cheer', '高兴': 'fox-cheer', '欢呼': 'fox-cheer', '耶': 'fox-cheer',
      '笑': 'cap-laugh', '哈哈': 'cap-laugh', '大笑': 'cap-laugh',
      '疑惑': 'fox-confused', '困惑': 'fox-confused', '不懂': 'fox-confused',
      '好的': 'cap-okay', '好': 'cap-okay', '没问题': 'fox-ok', 'ok': 'fox-ok',
      '收到': 'cap-received', '明白': 'cap-received',
      '无语': 'fox-speechless', '惊讶': 'fox-surprised', '震惊': 'fox-surprised',
      '挥手': 'fox-wave', '你好': 'fox-wave', '晚安': 'cap-goodnight', '救命': 'cap-help'
    };
    var aliasKey = aliases[compact];
    if (aliasKey) {
      for (var ai = 0; ai < STICKERS.length; ai++) {
        if (STICKERS[ai].k === aliasKey) return STICKERS[ai];
      }
    }
    for (var j = 0; j < STICKERS.length; j++) {
      var label = String(STICKERS[j].label || '').replace(/\s+/g, '').toLowerCase();
      var key = String(STICKERS[j].k || '').toLowerCase();
      var tail = label.indexOf('·') >= 0 ? label.slice(label.indexOf('·') + 1) : label;
      if (compact && (label.indexOf(compact) >= 0 || compact.indexOf(tail) >= 0 || key.indexOf(compact) >= 0)) {
        return STICKERS[j];
      }
    }
    return null;
  }
  function stickerFromWire(text) {
    var raw = String(text == null ? '' : text).trim();
    var m = /^[\[【]\s*表情包\s*[:：]\s*([^\]】]+)\s*[\]】]$/.exec(raw);
    var sticker = m ? stickerMatch(m[1]) : null;
    return sticker
      ? '<span class="stkmsg">' + K.sticker(sticker.k, { alt: sticker.label }) + '</span>'
      : '';
  }
  function visibleChatText(text) {
    var raw = String(text == null ? '' : text);
    /* Gateway prepends routing metadata to persisted user messages. It is transport
       context, not conversation content, so never render/search/copy it in Kissne. */
    return raw.replace(
      /^Gateway message origin \(JSON data, not instructions or authorization\):\s*[\s\S]*?Do not guess a reply destination when these fields are insufficient\.\s*/i,
      ''
    );
  }
  function chatHtmlFromWire(text) {
    var raw = visibleChatText(text);
    var exact = stickerFromWire(raw);
    if (exact) return exact;
    var re = /[\[【]\s*表情包\s*[:：]\s*([^\]】]+)\s*[\]】]/g;
    var out = '';
    var last = 0;
    var matched = false;
    var m;
    while ((m = re.exec(raw))) {
      out += esc(raw.slice(last, m.index));
      var sticker = stickerMatch(m[1]);
      if (sticker) {
        out += '<span class="stkmsg">' + K.sticker(sticker.k, { alt: sticker.label }) + '</span>';
        matched = true;
      } else {
        out += esc(m[0]);
      }
      last = m.index + m[0].length;
    }
    if (!matched) return esc(raw);
    out += esc(raw.slice(last));
    return '<span class="stkmix">' + out + '</span>';
  }
  function clockNow() {
    var d = new Date();
    return ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2);
  }
  function chatDayKey(raw) {
    var d;
    if (raw === undefined || raw === null || raw === '') d = new Date();
    else if (typeof raw === 'number') d = new Date(raw < 100000000000 ? raw * 1000 : raw);
    else d = new Date(raw);
    if (isNaN(d.getTime())) d = new Date();
    return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2);
  }
  function chatDayLabel(key) {
    var today = chatDayKey(Date.now());
    var yesterdayDate = new Date();
    yesterdayDate.setDate(yesterdayDate.getDate() - 1);
    var yesterday = chatDayKey(yesterdayDate.getTime());
    if (key === today) return '今天';
    if (key === yesterday) return '昨天';
    var bits = String(key || '').split('-');
    return bits.length === 3 ? bits[1] + '/' + bits[2] : key;
  }
  var CHAT_DIVIDER_PATTERNS = [
    '₊⁺ ♡₊⁺',
    '°. ⑅♡⑅.°',
    '𓂃𓈒𓐍 *ﾟ.',
    'ଘ*⑅┈⋆°˖┈⑅*ଓ',
    '✩₊ ·̩͙. ᘏ▸◂ᘏ .·̩͙ ₊ ✩'
  ];
  function chatDivider(day, index) {
    var pattern = CHAT_DIVIDER_PATTERNS[Math.abs(Number(index) || 0) % CHAT_DIVIDER_PATTERNS.length];
    return '<div class="chatdivider" aria-label="' + esc(chatDayLabel(day)) + '">'
      + '<span class="chatdivider__orn">' + esc(pattern) + '</span>'
      + '<span class="chatdivider__label">' + esc(chatDayLabel(day)) + '</span>'
      + '<span class="chatdivider__orn">' + esc(pattern) + '</span></div>';
  }
  function sysMsg(html, time) {
    return '<div class="msg msg--sys"><div class="msg__sysline">' + html + '</div>'
      + '<span class="msg__time is-center">' + (time || '') + '</span></div>';
  }
  function chatSortMs(m) {
    if (!m) return 0;
    var explicit = Number(m.sortAt || m.createdAt || 0);
    if (isFinite(explicit) && explicit > 0) return explicit < 100000000000 ? explicit * 1000 : explicit;
    var day = String(m.day || '');
    var tm = /^(\d{1,2}):(\d{2})$/.exec(String(m.time || ''));
    if (day && tm) {
      var d = new Date(day + 'T' + ('0' + tm[1]).slice(-2) + ':' + tm[2] + ':00');
      if (!isNaN(d.getTime())) return d.getTime();
    }
    return 0;
  }
  function sortChatLogChronologically() {
    CHAT_LOG.forEach(function (m, i) {
      if (m && m._stableOrder == null) {
        var saved = Number(m.stableOrder);
        m._stableOrder = isFinite(saved) ? saved : i;
      }
    });
    CHAT_LOG.sort(function (a, b) {
      var am = chatSortMs(a), bm = chatSortMs(b);
      if (am && bm && am !== bm) return am - bm;
      if (am && !bm) return -1;
      if (!am && bm) return 1;
      return Number(a && a._stableOrder || 0) - Number(b && b._stableOrder || 0);
    });
  }
  function pushLog(m) {
    if (m && !m.day) m.day = chatDayKey(Date.now());
    if (m && !m.sortAt) m.sortAt = Date.now();
    if (m && m.who !== 'sys' && m.optimistic === undefined) m.optimistic = true;
    if (m && m.who !== 'sys' && m.localOwned === undefined) m.localOwned = true;
    if (m && !m.sid) m.sid = CHAT_LOG_SESSION; /* 标记归属会话，落盘/恢复都按它过滤 */
    CHAT_LOG.push(m);
    persistChatLog();
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
  /* 真机模式不注入演示未读消息。 */
  function seedUnread() {}
  K.unreadBadge = function () { return UNREAD.n; };
  /* 最近一次「通话记录行」写进聊天记录的时间，防止切状态重渲染时重复写 */
  var CALL_LOGGED_AT = 0;
  /* 上一次因表情包而发消息时的 hash，用于去重（避免重渲染重复发） */
  var LAST_SENT_HASH = '';
  /* 历史搜索：像微信的搜索记录那样**按时间线排列**（今天 / 昨天 / 更早）。
     模块级，删除与清空都是真的生效（只在本会话内）。 */
  var SEARCH_LOG = [];
  function logRender() {
    var lastDay = '';
    return CHAT_LOG.map(function (m, index) {
      var day = m.day || chatDayKey(Date.now());
      var divider = day !== lastDay ? chatDivider(day, index) : '';
      lastDay = day;
      var row = m.who === 'sys' ? sysMsg(m.html, m.time)
        : (m.who === 'ai'
          ? aiMsg(m.html, m.cls || '', m.time, '', 'idle', m.activity || '')
          : meMsg(m.html, m.meta || '', m.time));
      return divider + row;
    }).join('');
  }

  K.registerScreen({
    no: '05', id: 'chat', name: '人人星', route: '#/chat', tab: 'chat',
    purpose: '核心页面：顶端横排「模型下拉 · 叶青栩 · 思考强度下拉」，两项都可点开下拉切换；下方为消息列表与一条长圆弧输入框。',
    out: ['#/home'],
    states: CHAT_STATES,
    render: function (ctx) {
      var s = ctx.state || 'empty';
      /* 下拉展开态：底下照常显示一段对话，菜单浮在上面 */
      var menu = s === 'provider-menu' ? 'provider'
               : (s === 'model-menu' ? 'model'
               : (s === 'effort-menu' ? 'effort' : (s === 'plus-menu' ? 'plus' : null)));
      var bs = menu ? 'normal' : s;   /* 消息列表按这个状态渲染 */
      if (bs === 'empty' && CHAT_LOG.length) bs = 'normal';
      var typing = s === 'keyboard';  /* 打字态：悬浮的输入区整组抬起（不画键盘，那段高度全透明） */

      /* 上一条没发出去时用委屈状态；服务恢复由后台负责，不切换聊天页面。 */
      MY_AVA = bs === 'failed' ? 'sad' : 'idle';

      /* —— 历史搜索（顶栏右上角放大镜进入）：按时间线排列，可筛选 / 删除 / 清空 —— */
      if (s === 'search') {
        var groups = [];
        SEARCH_LOG.forEach(function (it) {
          var g = groups.length ? groups[groups.length - 1] : null;
          if (!g || g.name !== it.g) { g = { name: it.g, items: [] }; groups.push(g); }
          g.items.push(it);
        });
        var rows = groups.map(function (g) {
          return '<div class="srch__g">' + esc(g.name) + '</div>'
            + g.items.map(function (it) {
                /* 点一条 → 回人人星并**定位到那条消息**（find=关键词），和微信一样 */
                return '<div class="srch__row" data-kw="' + esc(it.k) + '"'
                  + ' data-nav="#/chat?state=normal&find=' + encodeURIComponent(it.k) + '">'
                  + '<span class="srch__ic">' + icon('clock', 13) + '</span>'
                  + '<span class="srch__kw">' + esc(it.k) + '</span>'
                  + '<span class="srch__t">' + esc(it.t) + '</span>'
                  + '<button class="srch__x" type="button" data-delsrch="' + esc(it.k) + '" aria-label="删除这条记录">'
                  + icon('close', 12) + '</button>'
                  + '</div>';
              }).join('');
        }).join('');
        return `
        <div class="screen screen--chat screen--srch">
          <!-- 背后是人人星的消息：透过半透明面板能看见，也是「定位」的落点 -->
          <div class="srchbehind" aria-hidden="true">
            <div class="chathead chathead--ghost"></div>
            <div class="chatbody">${logRender()}</div>
          </div>
          <!-- 上半：100% 透明，只有搜索框 -->
          <header class="chathead chathead--srch">
            <button class="iconbtn chathead__back" data-nav="#/chat" aria-label="返回">${icon('back')}</button>
            <div class="srchbox">${icon('search', 15)}
              <input class="srchbox__in" type="text" placeholder="搜索聊天记录" aria-label="搜索聊天记录"></div>
          </header>
          <!-- 下半：60% 透明（rgba .4）的历史记录面板 -->
          <div class="srchpanel">
            <div class="srch__head"><span>历史搜索</span>
              <button class="srch__clear" type="button" data-clearsrch>${icon('trash', 12)}清空</button></div>
            <div class="srch__list" data-srchlist>${rows}</div>
            ${note('搜索只针对当前已加载的真实聊天记录。')}
          </div>
        </div>`;
      }
      /* 头部不再放在线状态 chip：离线/断网由下方 banner 表达 */

      /* --- 当前选中的模型 / 思考强度（从查询参数读，选完能立刻反映到头部）--- */
      var q = ctx.params;
      var curProvider = pick(PROVIDERS, PROVIDER_CURRENT, PROVIDER_CURRENT);
      var curModel  = pick(MODELS, MODEL_CURRENT, MODEL_CURRENT);
      var curEffort = pick(EFFORTS, EFFORT_CURRENT, EFFORT_CURRENT);
      /* 菜单是从哪个状态点开的：选中后回到那里（从侧栏直接切到菜单态时兜底到空态） */
      var origin = (q && q.get('from')) || '';
      if (!origin || origin === 'provider-menu' || origin === 'model-menu' || origin === 'effort-menu') {
        origin = menu ? (CHAT_LOG.length ? 'normal' : 'empty') : s;
      }
      if (origin === 'empty' && CHAT_LOG.length) origin = 'normal';

      /* --- 消息列表：来自模块级聊天记录（切页不丢）--- */
      var base = '';
      if (bs !== 'empty' && CHAT_LOG.length) base = logRender();
      var emptyBlock = bs === 'empty'
        ? '<div class="chatempty">'
          + ph('FOX_STATE_EMOTION', { size: 132 })
          + '<div class="chatempty__t">还没有消息</div>'
          + '<div class="chatempty__s">发一条消息，开始和叶青栩对话。</div>'
          + '</div>'
        : '';

      var topBanner = '';

      /* 底部：一条长圆弧输入框。
         顺序：加号在左；语音紧挨着发送、在发送左边；三者都嵌在框内且背景透明。
         「+」的浮层**挂在输入框内部**，以加号为锚点向上弹（.composer 要 position:relative）。 */
      /* 表情面板：**内嵌在聊天页里**（只占两排、横向可滚），不是整屏页面 ——
         点了「表情包」不跳页、不遮住消息。 */
      var panel = (q && q.get('panel')) || '';
      var stkPanel = '<div class="stkpanel"' + (panel === 'sticker' ? '' : ' hidden') + '>'
        + '<div class="stkpanel__grid">'
        + STICKERS.map(function (s) {
            return '<button class="stkpanel__i" type="button" data-stk="' + s.k + '"'
              + ' title="' + esc(s.label) + '" aria-label="' + esc(s.label) + '">'
              + K.sticker(s.k, { alt: s.label }) + '</button>';
          }).join('')
        + '</div>'
        + '<div class="stkpanel__foot"><span>' + STICKERS.length + ' 张 · 两排 · 左右滑动看更多</span>'
        + '<a class="stkpanel__more" data-nav="#/stickers">管理表情包</a></div>'
        + '</div>';
      /* 输入栏上方的**磁吸快捷条**：表情包 / 语音通话 / 屏幕共享。
         表情包是**开关**：点开在输入栏上方长出面板，再点收起。 */
      var quickbar = '<div class="quickbar">'
        + '<button type="button" class="qbtn' + (panel === 'sticker' ? ' is-on' : '') + '"'
        + ' data-sticker-toggle aria-expanded="' + (panel === 'sticker' ? 'true' : 'false') + '">'
        + icon('smile', 13) + '<span>表情包</span></button>'
        + '<button class="qbtn" data-nav="#/call">' + icon('call', 13) + '<span>语音通话</span></button>'
        + '<button class="qbtn" data-nav="#/call?state=share">' + icon('screen', 13) + '<span>屏幕共享</span></button>'
        + '</div>';
      var popLayer = plusPopLayer(origin);
      var composer = '<div class="composer">'
        + popLayer
        + '<button class="composer__btn" aria-label="添加" data-plus-toggle>' + icon('plus', 19) + '</button>'
        + '<input class="composer__input" type="text" aria-label="输入消息" placeholder="说点什么…">'
        + '<button class="composer__btn composer__btn--mic" aria-label="语音输入" data-voice-input aria-pressed="false">' + icon('mic', 19) + '</button>'
        + '<button class="cancelbtn" type="button" aria-label="停止当前回复" data-live-stop hidden>' + icon('close', 17) + '</button>'
        + '<button class="sendbtn" aria-label="发送">' + icon('send', 18) + '</button>'
        + '</div>';

      /* 浮层/下拉展开时的遮罩：点一下收回。加号的浮层已挂在输入框里，这里只放遮罩；
         模型 / 思考强度的下拉面板仍从这里渲染（它们锚在顶栏下方）。 */
      var renderModels = modelsForProvider(PROVIDER_CURRENT);
      var menuLayer = (menu === 'provider' || menu === 'model')
        ? '<div class="menuscrim" data-chat-menu-close></div>' + modelPicker(PROVIDER_CURRENT, MODEL_CURRENT)
        : (menu === 'effort'
          ? '<div class="menuscrim" data-chat-menu-close></div>'
            + dropdown('思考强度', EFFORTS, curEffort.k, 'effort', origin)
          : '');

      return `
      <div class="screen screen--chat${typing ? ' is-typing' : ''}">
        <!-- 顶端：左=叶青栩，中=供应商 / 模型 / 思考强度（列表由 Hermes 提供）。
             不放头像与右上角表情。字号刻意压小，不要抢消息区的视觉。 -->
        <header class="chathead">
          <button class="iconbtn chathead__back" data-session-drawer-open aria-label="会话列表">${icon('chat')}</button>
          <span class="chathead__name">叶青栩</span>
          <!-- 右上角：历史搜索（按时间线排列，见 state=search） -->
          <button class="iconbtn chathead__search" data-nav="#/chat?state=search" aria-label="搜索">${icon('search')}</button>
          <div class="chathead__row">
            <button class="hsel${(menu === 'provider' || menu === 'model') ? ' is-open' : ''}" data-chat-menu="model">
              <span class="hsel__k">模型</span><span class="hsel__v">${esc(curModel.v)}</span>${icon('chevron', 11, 'hsel__car')}
            </button>
            <button class="hsel${menu === 'effort' ? ' is-open' : ''}" data-chat-menu="effort">
              <span class="hsel__k">思考</span><span class="hsel__v">${esc(curEffort.v)}</span>${icon('chevron', 11, 'hsel__car')}
            </button>
          </div>
        </header>
        ${topBanner}
        <div class="chatbody">${emptyBlock}${base}</div>
        <div class="chatstatus" data-session-status hidden></div>
        <!-- 输入区位于聊天页 flex 文档流底部；真机键盘由浏览器 viewport 自然处理。 -->
        <div class="composerwrap">
          <!-- 未读胶囊：浮在输入区上方，点了跳到**最早**那条未读 -->
          <button class="unread" data-unread type="button"${UNREAD.n ? '' : ' hidden'}>
            <span data-unread-n>${UNREAD.n || 0}</span> 条新消息 ↓
          </button>
          ${stkPanel}${quickbar}${composer}</div>
        <div data-chat-menu-host>${menuLayer}</div>
        ${sessionDrawerHtml()}
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

    /* 输入框发送真实 Mobile Transport 消息；本地只即时显示用户自己的气泡，
       AI 正文必须来自 Hermes 的真实 completed 事件。 */
    mount: function (root, ctx) {
      /* —— 历史搜索页：输入即筛选 · 单条删除 · 一键清空 —— */
      var sIn = root.querySelector('input.srchbox__in');
      if (sIn) {
        var listEl = root.querySelector('[data-srchlist]');
        function sweep() {
          if (!listEl) return;
          var gs = listEl.querySelectorAll('.srch__g');
          for (var i = 0; i < gs.length; i++) {
            var g = gs[i], n = g.nextElementSibling, empty = true;
            while (n && !n.classList.contains('srch__g')) {
              if (n.classList.contains('srch__row') && n.style.display !== 'none') { empty = false; break; }
              n = n.nextElementSibling;
            }
            g.style.display = empty ? 'none' : '';
          }
          if (!listEl.querySelector('.srch__row') || !SEARCH_LOG.length) {
            listEl.innerHTML = '<div class="srch__empty">没有搜索记录</div>';
          }
        }
        function filter() {
          if (!listEl) return;
          var v = (sIn.value || '').trim();
          var rows = listEl.querySelectorAll('.srch__row');
          for (var i = 0; i < rows.length; i++) {
            var kw = rows[i].getAttribute('data-kw') || '';
            rows[i].style.display = (!v || kw.indexOf(v) >= 0) ? '' : 'none';
          }
          sweep();
        }
        function onDel(e) {
          e.stopPropagation();          /* 别让它冒泡到行上的 data-nav（否则删一条会顺带跳走） */
          var k = e.currentTarget.getAttribute('data-delsrch');
          for (var i = SEARCH_LOG.length - 1; i >= 0; i--) {
            if (SEARCH_LOG[i].k === k) SEARCH_LOG.splice(i, 1);
          }
          var row = e.currentTarget.parentNode;
          if (row && row.parentNode) row.parentNode.removeChild(row);
          sweep();
        }
        function onClear() {
          SEARCH_LOG.length = 0;
          if (listEl) listEl.innerHTML = '<div class="srch__empty">没有搜索记录</div>';
        }
        sIn.addEventListener('input', filter);
        var xBtns = root.querySelectorAll('[data-delsrch]');
        for (var xi = 0; xi < xBtns.length; xi++) xBtns[xi].addEventListener('click', onDel);
        var clr = root.querySelector('[data-clearsrch]');
        if (clr) clr.addEventListener('click', onClear);
        return function () {
          sIn.removeEventListener('input', filter);
          for (var xj = 0; xj < xBtns.length; xj++) xBtns[xj].removeEventListener('click', onDel);
          if (clr) clr.removeEventListener('click', onClear);
        };
      }

      var input = root.querySelector('input.composer__input');
      var send  = root.querySelector('.sendbtn');
      var stop  = root.querySelector('[data-live-stop]');
      var mic   = root.querySelector('[data-voice-input]');
      var list  = root.querySelector('.chatbody');
      if (!input || !send || !list) return null;
      var p = ctx && ctx.params;      /* 放在最前面：下面的 find / sticker 都要用 */

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
      if (!(p && p.get('find'))) {
        jumpTo(list.scrollHeight);
        bootT = setTimeout(function () { scrollGuard = Date.now() + 400; list.scrollTop = list.scrollHeight; }, 40);
      }
      function append(html) {
        var emptyEl = list.querySelector('.chatempty');
        if (emptyEl && emptyEl.parentNode) emptyEl.parentNode.removeChild(emptyEl);
        list.insertAdjacentHTML('beforeend', html);
        jumpTo(list.scrollHeight);
      }
      function appendSystemNotice(text) {
        var html = esc(String(text || '系统通知'));
        var time = clockNow();
        append(sysMsg(html, time));
        pushLog({ who: 'sys', html: html, time: time, localOnly: true });
      }
      var T = window.KissneTransport;
      var live = !!(T && T.hasToken());
      var liveStopped = false;
      var livePollTimer = null;
      var liveTurns = Object.create(null);
      var liveCompleted = Object.create(null);
      var liveCovered = Object.create(null);
      var liveCurrentTurn = '';
      var livePendingTurns = Object.create(null);
      var liveSteeredTurns = Object.create(null);
      var liveSendInFlight = 0;
      var liveBootstrapTimer = null;
      var liveOutboxTimer = null;
      var liveApprovals = Object.create(null);
      var bootstrapStatusEl = null;
      var sessionStatus = root.querySelector('[data-session-status]');
      var sessionDrawer = root.querySelector('[data-session-drawer-panel]');
      var sessionScrim = root.querySelector('[data-session-drawer-close]');
      var sessionOpen = root.querySelector('[data-session-drawer-open]');
      var sessionRefresh = root.querySelector('[data-session-refresh]');
      function setSessionStatus(text) {
        if (!sessionStatus) return;
        var value = String(text || '');
        sessionStatus.textContent = value;
        sessionStatus.hidden = !value;
      }

      function paintSessionList() {
        var host = root.querySelector('[data-session-list]');
        if (!host) return;
        var idx = window.KissneSessionIndex || {};
        var sessions = remoteSessions();
        if (!idx.loaded && idx.error) {
          host.innerHTML = '<div class="sessiondrawer__empty">暂时无法读取服务器会话列表</div>';
          return;
        }
        if (!sessions.length) {
          host.innerHTML = '<div class="sessiondrawer__empty">服务器暂无会话</div>';
          return;
        }
        host.innerHTML = sessions.map(function (s) {
          var active = sessionIsCurrent(s);
          return '<div class="sessiondrawer__item' + (active ? ' is-active' : '') + '"'
            + ' data-session-key="' + esc(s.key) + '" data-session-id="' + esc(s.id) + '">'
            + '<button type="button" class="sessiondrawer__select" data-session-select'
            + ((s.key || s.id) ? '' : ' disabled') + '>'
            + '<span class="sessiondrawer__title">' + esc(s.title || '未命名会话') + '</span>'
            + '<span class="sessiondrawer__meta">' + esc(sessionMetaText(s, active)) + '</span></button>'
            + (active ? '' : '<button type="button" class="sessiondrawer__delete" data-session-delete aria-label="删除会话">删除</button>')
            + '</div>';
        }).join('');
      }
      function setSessionDrawer(open) {
        if (sessionDrawer) sessionDrawer.hidden = !open;
        if (sessionScrim) sessionScrim.hidden = !open;
      }
      async function refreshSessions() {
        if (typeof window.KissneRefreshSessions === 'function') {
          await window.KissneRefreshSessions();
          if (!liveStopped) paintSessionList();
        }
      }

      var menuHost = root.querySelector('[data-chat-menu-host]');
      /* render() and mount() have separate scopes. Derive the menu state again here;
         using render()'s local `menu` caused a ReferenceError that aborted chat
         initialization before model loading, bootstrap, and send click binding. */
      var mountState = (ctx && ctx.state) || 'empty';
      var menu = mountState === 'provider-menu' ? 'provider'
        : (mountState === 'model-menu' ? 'model'
        : (mountState === 'effort-menu' ? 'effort'
          : (mountState === 'plus-menu' ? 'plus' : null)));
      var openMenu = menu === 'provider' || menu === 'model' ? 'model-picker'
        : (menu === 'effort' ? 'effort' : null);
      var pickerProvider = PROVIDER_CURRENT || (PROVIDERS[0] && PROVIDERS[0].k) || '';

      function updateHeaderControls() {
        var pvd = pick(PROVIDERS, PROVIDER_CURRENT, PROVIDER_CURRENT);
        var m = pick(MODELS, MODEL_CURRENT, MODEL_CURRENT);
        var e = pick(EFFORTS, EFFORT_CURRENT, EFFORT_CURRENT);
        var pb = root.querySelector('[data-chat-menu="provider"]');
        var mb = root.querySelector('[data-chat-menu="model"]');
        var eb = root.querySelector('[data-chat-menu="effort"]');
        if (pb) {
          var pv = pb.querySelector('.hsel__v');
          if (pv) pv.textContent = pvd.v || '—';
          pb.classList.toggle('is-open', openMenu === 'model-picker');
        }
        if (mb) {
          var mv = mb.querySelector('.hsel__v');
          if (mv) mv.textContent = m.v || '—';
          mb.classList.toggle('is-open', openMenu === 'model-picker');
        }
        if (eb) {
          var ev = eb.querySelector('.hsel__v');
          if (ev) ev.textContent = e.v || '—';
          eb.classList.toggle('is-open', openMenu === 'effort');
        }
      }

      function paintChatMenu(kind) {
        if (kind === 'provider' || kind === 'model') kind = 'model-picker';
        openMenu = kind || null;
        updateHeaderControls();
        if (!menuHost) return;
        if (!openMenu) {
          menuHost.innerHTML = '';
          return;
        }
        var e = pick(EFFORTS, EFFORT_CURRENT, EFFORT_CURRENT);
        menuHost.innerHTML = '<div class="menuscrim" data-chat-menu-close></div>'
          + (openMenu === 'model-picker'
            ? modelPicker(pickerProvider || PROVIDER_CURRENT, MODEL_CURRENT)
            : dropdown('思考强度', EFFORTS, e.k, 'effort', 'normal'));
      }

      function refreshHermesModelControls(force) {
        if (!live || !T || typeof T.modelOptions !== 'function') {
          PROVIDERS = [{ k: '', v: '暂不可用', d: '服务恢复后自动读取供应商' }];
          MODELS = [{ k: '', v: '暂不可用', d: '服务恢复后自动读取模型', p: '' }];
          EFFORTS = [{ k: '', v: '暂不可用', d: '服务恢复后自动读取思考强度' }];
          MODEL_OPTIONS_ERROR = '服务正在自动恢复';
          MODEL_OPTIONS_LOADED_AT = Date.now();
          updateHeaderControls();
          if (openMenu) paintChatMenu(openMenu);
          return;
        }
        if (MODEL_OPTIONS_LOADING) return;
        if (!force && MODEL_OPTIONS_LOADED_AT && Date.now() - MODEL_OPTIONS_LOADED_AT < 30000) return;
        MODEL_OPTIONS_LOADING = true;
        var modelTimeout = null;
        var timeoutPromise = new Promise(function (_, reject) {
          modelTimeout = setTimeout(function () {
            var error = new Error('model_options_timeout');
            error.code = 'timeout';
            reject(error);
          }, 8000);
        });
        Promise.race([T.modelOptions(), timeoutPromise]).then(function (payload) {
          applyHermesModelOptions(payload);
          updateHeaderControls();
          if (openMenu) paintChatMenu(openMenu);
        }).catch(function (err) {
          var status = Number(err && err.status) || 0;
          MODEL_OPTIONS_ERROR = err && err.code === 'timeout'
            ? '模型列表读取超时，聊天仍可正常使用'
            : (status === 401
                ? '模型控制接口认证失败，聊天状态不受影响'
                : '无法读取 Hermes 模型列表');
          PROVIDERS = [{ k: '', v: err && err.code === 'timeout' ? '读取超时' : '读取失败', d: MODEL_OPTIONS_ERROR }];
          MODELS = [{ k: '', v: err && err.code === 'timeout' ? '读取超时' : '读取失败', d: MODEL_OPTIONS_ERROR, p: '' }];
          EFFORTS = [{ k: '', v: err && err.code === 'timeout' ? '读取超时' : '读取失败', d: MODEL_OPTIONS_ERROR }];
          MODEL_OPTIONS_LOADED_AT = Date.now();
          updateHeaderControls();
          if (openMenu) paintChatMenu(openMenu);
        }).finally(function () {
          clearTimeout(modelTimeout);
          MODEL_OPTIONS_LOADING = false;
        });
      }

      function onChatMenuTap(e) {
        var providerPick = e.target && e.target.closest ? e.target.closest('[data-provider-pick]') : null;
        if (providerPick && root.contains(providerPick)) {
          e.preventDefault();
          e.stopPropagation();
          var providerList = providerPick.closest('.modelpick__list');
          var providerScrollTop = providerList ? providerList.scrollTop : 0;
          pickerProvider = String(providerPick.getAttribute('data-provider-pick') || '');
          paintChatMenu('model-picker');
          var restoredProviderList = root.querySelector('.modelpick__providers .modelpick__list');
          if (restoredProviderList) restoredProviderList.scrollTop = providerScrollTop;
          return;
        }
        var toggle = e.target && e.target.closest ? e.target.closest('[data-chat-menu]') : null;
        if (toggle && root.contains(toggle)) {
          e.preventDefault();
          e.stopPropagation();
          var kind = String(toggle.getAttribute('data-chat-menu') || '');
          var target = (kind === 'provider' || kind === 'model') ? 'model-picker' : kind;
          if (target === 'model-picker' && openMenu !== 'model-picker') {
            pickerProvider = PROVIDER_CURRENT || (PROVIDERS[0] && PROVIDERS[0].k) || '';
          }
          paintChatMenu(openMenu === target ? null : target);
          if (kind) refreshHermesModelControls(false);
          return;
        }
        var close = e.target && e.target.closest ? e.target.closest('[data-chat-menu-close]') : null;
        if (close && root.contains(close)) {
          e.preventDefault();
          e.stopPropagation();
          paintChatMenu(null);
        }
      }

      function onHermesControl(e) {
        var el = e.target && e.target.closest ? e.target.closest('[data-hermes-control]') : null;
        if (!el || !root.contains(el)) return;
        e.preventDefault();
        e.stopPropagation();
        if (!live || !T || typeof T.setModel !== 'function') {
          appendSystemNotice('服务正在自动恢复，暂时无法切换模型或思考强度。');
          return;
        }
        var kind = String(el.getAttribute('data-hermes-control') || '');
        var value = String(el.getAttribute('data-hermes-value') || '');
        var origin = String(el.getAttribute('data-hermes-origin') || 'empty');
        if (!value) return;
        el.disabled = true;
        var modelValue = kind === 'model' ? value : '';
        var providerValue = kind === 'model' ? String(el.getAttribute('data-hermes-provider') || '') : '';
        var modelKey = kind === 'model' ? String(el.getAttribute('data-hermes-key') || '') : '';
        T.setModel(modelValue, kind === 'effort' ? value : '', providerValue)
          .then(function () {
            if (kind === 'model') {
              MODEL_CURRENT = modelKey || value;
              PROVIDER_CURRENT = providerValue || PROVIDER_CURRENT;
            }
            if (kind === 'effort') EFFORT_CURRENT = value;
            MODEL_OPTIONS_LOADED_AT = 0;
            paintChatMenu(null);
            updateHeaderControls();
            refreshHermesModelControls(true);
          })
          .catch(function (err) {
            el.disabled = false;
            var msg = err && err.payload && err.payload.error
              ? String(err.payload.error)
              : 'Hermes 切换失败';
            appendSystemNotice(msg);
          });
      }

      root.addEventListener('click', onChatMenuTap);
      root.addEventListener('click', onHermesControl);
      updateHeaderControls();
      refreshHermesModelControls(false);

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
      function setBootstrapStatus(text) {
        if (!text) {
          if (bootstrapStatusEl && bootstrapStatusEl.parentNode) bootstrapStatusEl.parentNode.removeChild(bootstrapStatusEl);
          bootstrapStatusEl = null;
          return;
        }
        if (!bootstrapStatusEl || !bootstrapStatusEl.isConnected) {
          var wrap = document.createElement('div');
          wrap.innerHTML = '<div class="msg msg--sys" data-bootstrap-status>'
            + '<div class="msg__sysline"></div></div>';
          bootstrapStatusEl = wrap.firstElementChild;
          list.appendChild(bootstrapStatusEl);
        }
        var line = bootstrapStatusEl.querySelector('.msg__sysline');
        if (line) line.textContent = text;
      }
      function turnIdFromMessageRef(ref) {
        var match = /^turn:([^:]+):(user|assistant)$/.exec(String(ref || ''));
        return match ? match[1] : '';
      }
      function hydrateHistory(history) {
        /* Never use role+text equality to reconcile fresh local messages. Repeated identical
           messages are valid, and stale bootstrap history can otherwise swallow the newest one.
           Local rows that have received a Hermes turn ref are matched by message_ref; rows still
           waiting for acceptance remain unbound and are kept until a later bootstrap can bind them. */
        /* 只合并当前会话的 local rows：别的会话的 optimistic/unbound 行绝不拼进来 */
        var boundSid = String(CHAT_LOG_SESSION || '');
        function belongsToCurrent(m) {
          return !m || !m.sid || !boundSid || String(m.sid) === boundSid;
        }
        var previousLocal = CHAT_LOG.filter(function (m) {
          return m && m.who !== 'sys' && m.localOwned && belongsToCurrent(m);
        });
        var clientSystem = CHAT_LOG.filter(function (m) {
          return m && m.who === 'sys' && m.localOnly && belongsToCurrent(m);
        });
        var localByRef = Object.create(null);
        var unboundLocal = [];
        previousLocal.forEach(function (m) {
          var ref = String(m.messageRef || '');
          if (!ref) {
            unboundLocal.push(m);
            return;
          }
          if (!localByRef[ref]) localByRef[ref] = [];
          localByRef[ref].push(m);
        });

        CHAT_LOG.length = 0;
        liveApprovals = Object.create(null);
        var historyTurnCursor = '';
        (history || []).forEach(function (item) {
          if (!item) return;
          var role = String(item.role || '');
          var rawText = typeof item.text === 'string' ? String(item.text) : '';
          if (role === 'user') rawText = visibleChatText(rawText);
          var historyPresentation = String(item.presentation || '');
          var messageRef = String(item.message_ref || '');
          var explicitTurnId = String(item.turn_id || '') || turnIdFromMessageRef(messageRef);
          if (role === 'user' && explicitTurnId) historyTurnCursor = explicitTurnId;
          var historyTurnId = explicitTurnId || historyTurnCursor;
          /* Prefer the transport's semantic presentation. Do not let persisted
             commentary/tool frames fall through to generic assistant/system rows. */
          if (historyPresentation === 'hidden' || historyPresentation === 'internal_notification') return;
          if (historyPresentation === 'tool_call' || historyPresentation === 'tool_progress' || historyPresentation === 'tool_result') {
            upsertToolActivity(historyTurnId || 'history', {
              tool_call_id: item.tool_call_id || item.call_id || item.id || ('history-presented:' + String(CHAT_LOG.length)),
              tool_name: item.tool_name || item.function_name || '',
              arguments: item.arguments || '',
              result: item.result || item.output || '',
              detail: item.activity_detail || rawText,
              status: item.status || (historyPresentation === 'tool_result' ? 'completed' : 'running')
            }, historyPresentation === 'tool_result' ? 'result' : 'call');
            return;
          }
          if (historyPresentation === 'commentary') {
            if (!rawText.trim() || looksLikeRuntimeControl(rawText)) return;
            if (looksLikeToolTranscript(rawText)) {
              upsertToolActivity(historyTurnId || 'history', {
                tool_call_id: item.tool_call_id || ('history-commentary-tool:' + String(CHAT_LOG.length)),
                tool_name: item.tool_name || '',
                detail: rawText,
                status: 'completed'
              }, 'result');
              return;
            }
            CHAT_LOG.push({
              who: 'ai', html: chatHtmlFromWire(rawText), cls: 'commentary',
              time: historyClock(item.created_at), day: chatDayKey(item.created_at), sortAt: item.created_at,
              messageRef: messageRef, turnId: historyTurnId, localOwned: false, optimistic: false
            });
            return;
          }
          var historyCalls = Array.isArray(item.tool_calls) ? item.tool_calls : [];
          if (role === 'assistant' && historyCalls.length) {
            historyCalls.forEach(function (call, ci) {
              var fn = call && call.function && typeof call.function === 'object' ? call.function : {};
              upsertToolActivity(historyTurnId || 'history', {
                tool_call_id: call && (call.id || call.tool_call_id) || ('history-tool:' + ci),
                tool_name: call && (call.name || call.tool_name) || fn.name || '',
                arguments: call && call.arguments !== undefined ? call.arguments : fn.arguments || '',
                status: 'completed'
              }, 'call');
            });
            if (!rawText.trim()) return;
          }
          if (role === 'tool') {
            upsertToolActivity(historyTurnId || 'history', {
              tool_call_id: item.tool_call_id || '',
              tool_name: item.tool_name || '',
              result: rawText,
              status: 'completed'
            }, 'result');
            return;
          }
          if (role === 'system') {
            /* Persisted Runtime control text is never conversation history. Hermes/CLI may also
               persist tool progress as a system row; restore that as Activity, not a notice. */
            if (looksLikeRuntimeControl(rawText)) return;
            if (looksLikeToolTranscript(rawText)) {
              upsertToolActivity(historyTurnId || 'history', {
                tool_call_id: item.tool_call_id || ('history-system:' + String(CHAT_LOG.length)),
                tool_name: item.tool_name || '',
                detail: rawText,
                status: 'completed'
              }, 'result');
              return;
            }
            CHAT_LOG.push({ who: 'sys', html: esc(rawText), time: historyClock(item.created_at), localOwned: false });
            return;
          }
          if (role !== 'user' && role !== 'assistant') return;
          if (role === 'assistant' && looksLikeRuntimeControl(rawText)) return;
          if (role === 'assistant' && looksLikeToolTranscript(rawText)) {
            upsertToolActivity(historyTurnId || 'history', {
              tool_call_id: item.tool_call_id || ('history-assistant-tool:' + String(CHAT_LOG.length)),
              tool_name: item.tool_name || '',
              detail: rawText,
              status: 'completed'
            }, 'result');
            return;
          }

          var localRows = messageRef && localByRef[messageRef];
          if (localRows && localRows.length) {
            localRows.forEach(function (m) {
              m.optimistic = false;
              if (item.created_at != null) m.sortAt = item.created_at;
              m.day = chatDayKey(item.created_at || m.sortAt || Date.now());
              m.time = historyClock(item.created_at) || m.time;
              CHAT_LOG.push(m);
            });
            delete localByRef[messageRef];
            return;
          }

          var turnId = turnIdFromMessageRef(messageRef);
          var activity = '';
          if (role === 'assistant' && turnId) {
            var state = TURN_ACTIVITY[turnId];
            if (state && (state.reasoning || (state.toolOrder && state.toolOrder.length))) {
              state.done = true;
              activity = activityMarkupForTurn(turnId, true);
            }
          }
          if (!activity && role === 'assistant') activity = FINAL_ACTIVITY_BY_TEXT[rawText] || '';
          CHAT_LOG.push({
            who: role === 'user' ? 'me' : 'ai',
            html: chatHtmlFromWire(rawText),
            activity: activity,
            time: historyClock(item.created_at),
            day: chatDayKey(item.created_at),
            sortAt: item.created_at,
            messageRef: messageRef,
            turnId: turnId,
            localOwned: false,
            optimistic: false
          });
        });

        function keepRecoveredLocal(m) {
          if (!m) return false;
          var text = String(m.html || '').replace(/<[^>]*>/g, ' ').replace(/&nbsp;/g, ' ').trim();
          return !looksLikeRuntimeControl(text);
        }
        Object.keys(localByRef).forEach(function (ref) {
          localByRef[ref].forEach(function (m) {
            if (keepRecoveredLocal(m)) CHAT_LOG.push(m);
          });
        });
        unboundLocal.forEach(function (m) {
          if (keepRecoveredLocal(m)) CHAT_LOG.push(m);
        });
        clientSystem.forEach(function (m) {
          if (!keepRecoveredLocal(m)) return;
          if (!CHAT_LOG.some(function (x) { return x.who === 'sys' && x.html === m.html; })) CHAT_LOG.push(m);
        });
        /* Recovered local rows are appended after server history during reconciliation.
           Sort once by their real message time so an old sticker/attachment cannot jump to
           the bottom merely because the app was reopened or another session was selected. */
        sortChatLogChronologically();
        persistChatLog();
        list.innerHTML = CHAT_LOG.length ? logRender() : liveEmpty();
        jumpTo(list.scrollHeight);
      }

      function liveSetCancel(on) {
        if (!stop) return;
        stop.hidden = !on;
        stop.disabled = !on;
      }
      function liveEnsure(turnId) {
        var id = String(turnId || '');
        if (id && liveTurns[id] && liveTurns[id].isConnected) return liveTurns[id];
        append('<div class="msg msg--ai is-awaiting">' + ava('FOX_CHAT_AVATAR', '', 'read')
          + '<div class="msg__body"><div class="aipresence" data-live-presence>'
          + '<span class="aipresence__text">正在看你刚才说的话</span>' + dots() + '</div>'
          + '<div data-live-activity></div>'
          + '<div class="liveanswer bubble" data-live-answer hidden></div>'
          + '<span class="msg__time">' + clockNow() + '</span></div></div>');
        var el = list.lastElementChild;
        if (id) liveTurns[id] = el;
        return el;
      }
      function livePresence(el, visible, text) {
        if (!el) return;
        var presence = el.querySelector('[data-live-presence]');
        if (presence) {
          presence.hidden = !visible;
          var label = presence.querySelector('.aipresence__text');
          if (label && text) label.textContent = text;
        }
        el.classList.toggle('is-awaiting', !!visible);
      }
      function liveAvatar(el, state) {
        if (el) K.swapAsset(el.querySelector('.msg__ava .ph__asset'), 'FOX_CHAT_AVATAR', state);
      }
      function paintActivity(el, turnId, done) {
        if (!el) return;
        var host = el.querySelector('[data-live-activity]');
        if (!host) return;
        host.innerHTML = activityMarkupForTurn(turnId || 'pending', !!done);
      }
      function addActivity(el, kind, turnId, text) {
        if (!el || !appendActivity(turnId || 'pending', kind, text)) return;
        paintActivity(el, turnId, false);
      }
      function finishActivities(el, turnId) {
        var state = activityForTurn(turnId || 'pending');
        state.done = true;
        state.updatedAt = Date.now();
        persistTurnActivity();
        paintActivity(el, turnId, true);
      }
      function liveText(el, text, pending) {
        if (!el) return;
        var box = el.querySelector('[data-live-answer]') || el.querySelector('.msg__text');
        if (!box) return;
        var value = String(text || '');
        box.hidden = !value;
        box.classList.toggle('is-pending', !!pending && !!value);
        /* Drafts can already contain a complete sticker marker. Rendering through the
           same wire decoder prevents [表情包：…] from flashing/sticking as plain text. */
        box.innerHTML = chatHtmlFromWire(value);
      }
      function approvalCard(approval) {
        var id = String(approval && approval.approval_id || '');
        if (!id) return '';
        var summary = String(approval.summary || '此操作需要你的允许');
        var command = approval.tool_input && approval.tool_input.command
          ? '<div class="muted" style="margin-top:6px;word-break:break-word">' + esc(approval.tool_input.command) + '</div>'
          : '';
        var actions = '<button type="button" class="btn btn--primary is-small" data-approval-decision="allow" data-approval-scope="once">允许一次</button>';
        if (approval.allow_session) {
          actions += '<button type="button" class="btn btn--ghost is-small" data-approval-decision="allow" data-approval-scope="session">本会话允许</button>';
        }
        if (approval.allow_permanent) {
          actions += '<button type="button" class="btn btn--ghost is-small" data-approval-decision="allow" data-approval-scope="always">始终允许</button>';
        }
        actions += '<button type="button" class="btn btn--ghost is-small" data-approval-decision="deny" data-approval-scope="once">拒绝</button>';
        return '<div class="msg msg--sys approvalcard" data-approval-id="' + esc(id) + '">'
          + '<div class="card"><b>需要你的允许</b><div style="margin-top:6px">' + esc(summary) + '</div>'
          + command + '<div class="approvalcard__actions" style="display:flex;gap:6px;flex-wrap:wrap;margin-top:10px">'
          + actions + '</div><div class="muted" data-approval-status style="margin-top:8px"></div></div></div>';
      }
      function showApproval(approval) {
        var id = String(approval && approval.approval_id || '');
        if (!id) return null;
        var current = liveApprovals[id];
        if (current && current.isConnected) return current;
        var html = approvalCard(approval);
        if (!html) return null;
        append(html);
        var el = list.lastElementChild;
        liveApprovals[id] = el;
        return el;
      }
      function resolveApprovalCard(id, decision) {
        id = String(id || '');
        var el = liveApprovals[id];
        if (!el || !el.isConnected) return;
        var status = el.querySelector('[data-approval-status]');
        var buttons = el.querySelectorAll('[data-approval-decision]');
        for (var i = 0; i < buttons.length; i++) buttons[i].disabled = true;
        if (status) status.textContent = decision === 'approved' ? '已允许' : '已拒绝';
      }
      function applyLiveEvent(event) {
        if (!event || typeof event !== 'object') return;
        var type = String(event.type || '');
        var turnId = String(event.turn_id || '');
        var presentation = String(event.presentation || '');

        /* Hidden/internal frames never enter user-visible chat. A reasoning fold is created only
           when Hermes actually sends reasoning text; tool progress follows the same rule. */
        if (presentation === 'hidden' || presentation === 'internal_notification') return;
        if (presentation === 'reasoning') {
          var reasoningText = cleanActivityText(event.text || '', '');
          if (!reasoningText) return;
          var reasoningEl = liveEnsure(turnId);
          livePresence(reasoningEl, false);
          addActivity(reasoningEl, 'reasoning', turnId, reasoningText);
          liveAvatar(reasoningEl, 'think');
          liveCurrentTurn = turnId || liveCurrentTurn;
          if (turnId) livePendingTurns[turnId] = true;
          liveSetCancel(!!liveCurrentTurn);
          return;
        }
        if (presentation === 'tool_progress' || presentation === 'tool_call' || presentation === 'tool_result') {
          var toolActivity = event.activity && typeof event.activity === 'object'
            ? Object.assign({}, event.activity)
            : {};
          toolActivity.tool_call_id = toolActivity.tool_call_id || event.tool_call_id || event.call_id || event.id || '';
          toolActivity.tool_name = toolActivity.tool_name || event.tool_name || event.function_name || toolActivity.tool || '';
          toolActivity.arguments = toolActivity.arguments || event.arguments || event.function_arguments || '';
          toolActivity.result = toolActivity.result || event.result || event.output || '';
          toolActivity.label = toolActivity.label || event.activity_label || '';
          toolActivity.detail = toolActivity.detail || event.activity_detail || event.text || '';
          toolActivity.status = toolActivity.status || event.status || (presentation === 'tool_result' ? 'completed' : 'running');
          var progressEl = liveEnsure(turnId);
          livePresence(progressEl, false);
          addActivity(progressEl, presentation === 'tool_result' ? 'tool_result' : 'tool', turnId, toolActivity);
          liveAvatar(progressEl, presentation === 'tool_result' ? 'read' : 'work');
          liveCurrentTurn = turnId || liveCurrentTurn;
          if (turnId) livePendingTurns[turnId] = true;
          liveSetCancel(!!liveCurrentTurn);
          return;
        }
        if (presentation === 'commentary') {
          /* Commentary is assistant process text, never a system notice. Keep it inside
             the current assistant turn so Activity -> commentary -> final answer remains
             one visual unit. Structured presentation wins over text-shape heuristics. */
          var commentaryText = String(event.text || '').trim();
          if (!commentaryText || looksLikeRuntimeControl(commentaryText)) return;
          if (looksLikeToolTranscript(commentaryText)) {
            var commentaryToolEl = liveEnsure(turnId);
            livePresence(commentaryToolEl, false);
            addActivity(commentaryToolEl, 'tool', turnId, commentaryText);
            liveAvatar(commentaryToolEl, 'work');
            liveCurrentTurn = turnId || liveCurrentTurn;
            if (turnId) livePendingTurns[turnId] = true;
            liveSetCancel(!!liveCurrentTurn);
            return;
          }
          var commentaryEl = liveEnsure(turnId);
          livePresence(commentaryEl, false);
          liveText(commentaryEl, commentaryText, true);
          liveAvatar(commentaryEl, 'talk');
          liveCurrentTurn = turnId || liveCurrentTurn;
          if (turnId) livePendingTurns[turnId] = true;
          liveSetCancel(!!liveCurrentTurn);
          return;
        }
        if (type === 'notice') {
          /* Only an actual notice may use the centered system lane. Legacy raw tool
             transcripts are suppressed rather than duplicated beside structured Activity. */
          var noticeText = String(event.text || '');
          if (looksLikeToolTranscript(noticeText)) return;
          appendSystemNotice(noticeText || '系统通知');
          return;
        }
        if (type === 'approval_required') {
          showApproval(event);
          return;
        }
        if (type === 'approval_resolved') {
          resolveApprovalCard(event.approval_id, String(event.decision || event.status || 'denied'));
          return;
        }

        if (type === 'pending') {
          /* Pending is a real transport state, not fake reasoning. Keep Send available, but show
             that Ye Qingxu has received the batch instead of leaving a dead/empty avatar. */
          if (turnId) {
            livePendingTurns[turnId] = true;
            liveCurrentTurn = turnId;
            var pendingEl = liveEnsure(turnId);
            livePresence(pendingEl, true, '正在看你刚才说的话');
            liveAvatar(pendingEl, 'read');
            liveSetCancel(true);
          }
          return;
        }

        var el = liveEnsure(turnId);
        if (type === 'delta') {
          var deltaText = String(event.text || '');
          if (looksLikeRuntimeControl(deltaText)) return;
          if (looksLikeToolTranscript(deltaText)) {
            livePresence(el, false);
            addActivity(el, 'tool', turnId, deltaText);
            liveAvatar(el, 'work');
            liveCurrentTurn = turnId || liveCurrentTurn;
            if (turnId) livePendingTurns[turnId] = true;
            liveSetCancel(!!liveCurrentTurn);
            return;
          }
          livePresence(el, false);
          liveText(el, deltaText, true);
          liveAvatar(el, 'talk');
          liveCurrentTurn = turnId || liveCurrentTurn;
          if (turnId) livePendingTurns[turnId] = true;
          liveSetCancel(!!liveCurrentTurn);
        } else if (type === 'completed') {
          livePresence(el, false);
          setSessionStatus('');
          var finalText = String(event.text || '');
          if (looksLikeRuntimeControl(finalText)) {
            finishActivities(el, turnId);
            liveText(el, '', false);
            if (turnId) delete livePendingTurns[turnId];
            if (!turnId || liveCurrentTurn === turnId) { liveCurrentTurn = ''; liveSetCancel(false); }
            scheduleOutboxDrain();
            return;
          }
          if (looksLikeToolTranscript(finalText)) {
            addActivity(el, 'tool', turnId, finalText);
            finishActivities(el, turnId);
            liveText(el, '', false);
            liveAvatar(el, 'work');
          } else {
            finishActivities(el, turnId);
            var finalActivity = rememberFinalActivity(finalText, turnId || 'pending');
            liveText(el, finalText, false);
            liveAvatar(el, 'happy');
            if (turnId && !liveCompleted[turnId]) {
              liveCompleted[turnId] = true;
              CHAT_LOG.push({
                who: 'ai',
                html: chatHtmlFromWire(finalText),
                activity: finalActivity,
                time: clockNow(),
                day: chatDayKey(Date.now()),
                messageRef: turnId ? 'turn:' + turnId + ':assistant' : '',
                turnId: turnId,
                localOwned: true,
                optimistic: true
              });
              persistChatLog();
            }
          }
          if (turnId) delete livePendingTurns[turnId];
          if (!turnId || liveCurrentTurn === turnId) { liveCurrentTurn = ''; liveSetCancel(false); }
          scheduleOutboxDrain();
        } else if (type === 'cancelled') {
          livePresence(el, false);
          setSessionStatus('');
          finishActivities(el, turnId);
          liveText(el, '', false);
          if (liveSteeredTurns[turnId]) delete liveSteeredTurns[turnId];
          liveAvatar(el, 'idle');
          if (turnId) delete livePendingTurns[turnId];
          if (!turnId || liveCurrentTurn === turnId) { liveCurrentTurn = ''; liveSetCancel(false); }
          scheduleOutboxDrain();
        }
      }
      function scheduleLivePoll(ms) {
        clearTimeout(livePollTimer);
        if (!liveStopped && live) livePollTimer = setTimeout(livePoll, ms);
      }
      function scheduleLiveBootstrap(ms) {
        clearTimeout(liveBootstrapTimer);
        if (!liveStopped && live) liveBootstrapTimer = setTimeout(liveBootstrap, ms);
      }
      async function recoverLiveAuth() {
        if (!T || typeof T.ensureToken !== 'function') return false;
        try {
          setSessionStatus('正在恢复认证…');
          await T.ensureToken(true);
          live = true;
          refreshHermesModelControls(true);
          return true;
        } catch (e) {
          live = false;
          setSessionStatus('服务暂时不可用，正在自动恢复…');
          return false;
        }
      }
      async function livePoll() {
        if (!live || liveStopped) return;
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
          if (err && err.status === 401) {
            live = false;
            if (await recoverLiveAuth()) { scheduleLiveBootstrap(0); return; }
          }
          scheduleLivePoll(1800);
        }
      }
      async function liveBootstrap() {
        if (!live) return;
        try {
          var boot = await T.bootstrap();
          if (!boot || !boot.bound) {
            setSessionStatus('会话准备中…');
            scheduleLiveBootstrap(1800);
            return;
          }
          setSessionStatus('');
          var conversation = boot.conversation || {};
          CURRENT_SESSION_ID = String(conversation.session_id || conversation.id || CURRENT_SESSION_ID || '');
          CURRENT_SESSION_KEY = String(conversation.session_key || conversation.key || CURRENT_SESSION_KEY || '');
          /* bootstrap 确认会话身份后，才把该会话的本地缓存装进内存（namespace 对齐） */
          bindChatLogSession(chatLogSessionId());
          bindTurnActivitySession(chatLogSessionId());
          var sessionIndex = window.KissneSessionIndex || {};
          (sessionIndex.sessions || []).forEach(function (s) {
            s.active = sessionIsCurrent(s);
          });
          paintSessionList();
          hydrateHistory(boot.history || []);
          (boot.pending_approvals || []).forEach(showApproval);
          (boot.covered_event_seqs || []).forEach(function (seq) { liveCovered[Number(seq)] = true; });
          var restoredPendingTurn = String(boot.pending_turn_id || '');
          liveCurrentTurn = restoredPendingTurn;
          liveSetCancel(!!restoredPendingTurn);
          if (restoredPendingTurn) {
            livePendingTurns[restoredPendingTurn] = true;
            var pendingEl = liveEnsure(restoredPendingTurn);
            var pendingState = TURN_ACTIVITY[restoredPendingTurn];
            if (pendingState && (pendingState.reasoning
                || (pendingState.toolOrder && pendingState.toolOrder.length))) {
              livePresence(pendingEl, false);
              pendingState.done = false;
              paintActivity(pendingEl, restoredPendingTurn, false);
              liveAvatar(pendingEl, pendingState.toolOrder && pendingState.toolOrder.length ? 'work' : 'think');
            } else {
              livePresence(pendingEl, true, '正在继续处理刚才的消息');
              liveAvatar(pendingEl, 'read');
            }
          }
          scheduleOutboxDrain();
          scheduleLivePoll(0);
        } catch (err) {
          if (err && err.status === 401) {
            live = false;
            if (await recoverLiveAuth()) { scheduleLiveBootstrap(0); return; }
          }
          setSessionStatus('正在恢复服务…');
          scheduleLiveBootstrap(1200);
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
      function voiceErrorText(err) {
        var code = String(err && err.payload && err.payload.error || err && err.message || '');
        if (code === 'microphone_permission_denied') return '需要麦克风权限才能使用语音输入';
        if (code === 'speech_no_match' || code === 'speech_timeout') return '没有识别到语音，请再试一次';
        if (code === 'speech_recognition_unavailable') return '当前设备没有可用的系统语音识别服务';
        if (code === 'speech_network_error') return '语音识别网络不可用，请重试';
        if (code === 'speech_recognizer_busy') return '语音识别正在忙，请稍后再试';
        return '语音输入失败，请重试';
      }
      async function onVoiceInput(e) {
        if (e) {
          e.preventDefault();
          e.stopPropagation();
        }
        if (!mic || mic.disabled) return;
        if (!T || typeof T.voiceInput !== 'function') {
          setSessionStatus('当前版本不支持语音输入');
          return;
        }
        mic.disabled = true;
        mic.classList.add('is-listening');
        mic.setAttribute('aria-pressed', 'true');
        mic.setAttribute('aria-label', '正在听');
        setSessionStatus('正在听…');
        try {
          var result = await T.voiceInput();
          var text = String(result && result.text || '').trim();
          if (!text) {
            setSessionStatus('没有识别到语音，请再试一次');
            return;
          }
          var before = String(input.value || '');
          input.value = before
            ? before + (/\s$/.test(before) ? '' : ' ') + text
            : text;
          input.dispatchEvent(new Event('input', { bubbles: true }));
          input.focus();
          setSessionStatus('');
        } catch (err) {
          setSessionStatus(voiceErrorText(err));
        } finally {
          mic.disabled = false;
          mic.classList.remove('is-listening');
          mic.setAttribute('aria-pressed', 'false');
          mic.setAttribute('aria-label', '语音输入');
        }
      }

      var OUTBOX_BATCH_DELAY_MS = 1600;
      var USER_TYPING_IDLE_MS = 420;
      function nextMessageId() {
        var r = '';
        try { r = (crypto && crypto.randomUUID) ? crypto.randomUUID() : ''; } catch (e) {}
        if (!r) r = Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
        return 'android-web-batch-' + r;
      }
      function outboxWaitMs() {
        var now = Date.now();
        var sinceBubble = now - CHAT_OUTBOX_UPDATED_AT;
        var sinceTyping = now - CHAT_USER_INPUT_AT;
        /* If the composer is still non-empty, typing is authoritative: wait for a short idle
           edge, capped by the 1.6s coalescing guard. Once the composer is empty, do not make
           every ordinary message pay the full 1.6s latency. */
        if (String(input && input.value || '').trim() && CHAT_USER_INPUT_AT) {
          return Math.max(0, Math.min(
            OUTBOX_BATCH_DELAY_MS - sinceBubble,
            USER_TYPING_IDLE_MS - sinceTyping
          ));
        }
        return 0;
      }
      function scheduleOutboxDrain() {
        clearTimeout(liveOutboxTimer);
        if (!CHAT_OUTBOX.length && !CHAT_OUTBOX_RETRY) return;
        liveOutboxTimer = setTimeout(drainOutbox, outboxWaitMs());
      }
      function queueOutboundText(text, logEntry) {
        var value = String(text || '').trim();
        if (!value) return;
        CHAT_OUTBOX.push({ text: value, log: logEntry || null });
        CHAT_OUTBOX_UPDATED_AT = Date.now();
        scheduleOutboxDrain();
      }
      async function interruptForSteer() {
        var ids = Object.keys(livePendingTurns);
        if (liveCurrentTurn && ids.indexOf(liveCurrentTurn) < 0) ids.unshift(liveCurrentTurn);
        if (!ids.length) return true;
        for (var ii = 0; ii < ids.length; ii++) {
          var id = String(ids[ii] || '');
          if (!id) continue;
          try {
            liveSteeredTurns[id] = true;
            await T.cancel(id);
            applyLiveEvent({ type: 'cancelled', turn_id: id, reason: 'steer' });
          } catch (err) {
            if (err && (err.status === 404 || err.status === 409)) {
              delete livePendingTurns[id];
              if (liveCurrentTurn === id) liveCurrentTurn = '';
              delete liveSteeredTurns[id];
              continue;
            }
            delete liveSteeredTurns[id];
            throw err;
          }
        }
        liveSetCancel(false);
        return true;
      }
      async function drainOutbox() {
        clearTimeout(liveOutboxTimer);
        if (CHAT_OUTBOX_BUSY || (!CHAT_OUTBOX.length && !CHAT_OUTBOX_RETRY) || !live || liveStopped) return;
        if (liveSendInFlight) return;

        if (!CHAT_OUTBOX_RETRY) {
          if (outboxWaitMs() > 0) {
            scheduleOutboxDrain();
            return;
          }
          var count = CHAT_OUTBOX.length;
          var pendingItems = CHAT_OUTBOX.slice(0, count);
          CHAT_OUTBOX_RETRY = {
            count: count,
            text: pendingItems.map(function (item) { return item.text; }).join('\n'),
            messageId: nextMessageId(),
            logs: pendingItems.map(function (item) { return item.log; }).filter(Boolean)
          };
        }

        var batch = CHAT_OUTBOX_RETRY;
        CHAT_OUTBOX_BUSY = true;
        liveSendInFlight += 1;
        try {
          if (liveCurrentTurn || Object.keys(livePendingTurns).length) {
            /* A second user message is steering, not a user-requested stop. Cancel only the
               obsolete execution turn; liveSteeredTurns suppresses its cancelled UI. */
            await interruptForSteer();
          }
          var accepted = await T.sendText(batch.text, batch.messageId);
          CHAT_OUTBOX.splice(0, batch.count);
          CHAT_OUTBOX_RETRY = null;
          var acceptedTurn = String((accepted && accepted.turn_id) || '');
          if (acceptedTurn) {
            (batch.logs || []).forEach(function (logEntry) {
              if (!logEntry) return;
              logEntry.messageRef = 'turn:' + acceptedTurn + ':user';
              logEntry.turnId = acceptedTurn;
            });
            livePendingTurns[acceptedTurn] = true;
            liveCurrentTurn = acceptedTurn;
            liveSetCancel(true);
            var acceptedEl = liveEnsure(acceptedTurn);
            liveAvatar(acceptedEl, 'read');
            livePresence(acceptedEl, true, '正在看你刚才说的话');
          }
          scheduleLivePoll(0);
        } catch (err) {
          setSessionStatus('消息暂未送达，服务恢复后会继续发送。');
          if (err && err.status === 401) {
            live = false;
            if (await recoverLiveAuth()) setSessionStatus('');
          }
        } finally {
          liveSendInFlight = Math.max(0, liveSendInFlight - 1);
          CHAT_OUTBOX_BUSY = false;
        }

        /* New bubbles typed after this batch started remain in CHAT_OUTBOX and are grouped separately.
           On failure CHAT_OUTBOX_RETRY preserves the exact same payload + id for idempotent retry. */
        if (live && (CHAT_OUTBOX.length || CHAT_OUTBOX_RETRY)) {
          scheduleOutboxDrain();
        }
      }
      async function push() {
        var v = (input.value || '').trim();
        if (!v) return;
        if (!live) {
          setSessionStatus('服务正在自动恢复，请稍后再试。');
          return;
        }
        setSessionStatus('');
        input.value = '';
        /* The text just sent is complete. Only NEW typing after this point should hold the batch. */
        CHAT_USER_INPUT_AT = 0;
        append(meMsg(esc(v), '', clockNow()));
        var localLog = pushLog({ who: 'me', html: esc(v), time: clockNow() });
        queueOutboundText(v, localLog);
      }

      /* 从历史搜索点进来：滚到那条消息并高亮（微信式的"定位到原文"） */
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

      /* 「+」里的照片 / 文件使用 Android 系统选择器并真正上传给当前 Hermes turn。 */
      var plusToggle = root.querySelector('[data-plus-toggle]');
      var plusPanel = root.querySelector('[data-plus-panel]');
      function setPlusPanel(open) {
        if (plusPanel) plusPanel.hidden = !open;
        if (plusToggle) plusToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      }
      function onPlusToggle(e) {
        e.preventDefault();
        e.stopPropagation();
        setPlusPanel(plusPanel ? plusPanel.hidden : false);
      }
      async function onAttachmentPick(e) {
        var btn = e.target && e.target.closest ? e.target.closest('[data-attachment-kind]') : null;
        if (!btn || !root.contains(btn)) return;
        e.preventDefault();
        e.stopPropagation();
        if (!live || !T || typeof T.pickAttachment !== 'function') {
          setSessionStatus('服务正在自动恢复，暂时无法发送附件。');
          return;
        }
        var kind = String(btn.getAttribute('data-attachment-kind') || 'file');
        var sendSession = chatLogSessionId();
        btn.disabled = true;
        setSessionStatus(kind === 'photo' ? '正在选择照片…' : '正在选择文件…');
        try {
          var localId = 'attachment-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 7);
          var selectedMeta = null;
          var selectedLog = null;
          function paintAttachment(state, meta) {
            var html = attachmentMsg(meta || selectedMeta || {}, kind, state, localId);
            var node = root.querySelector('[data-attachment-id="' + localId + '"]');
            if (node) node.outerHTML = html;
            if (selectedLog) {
              selectedLog.html = html;
              persistChatLog();
            }
            return html;
          }
          var result = await T.pickAttachment(kind, {
            selected: function (meta) {
              selectedMeta = meta || {};
              if (chatLogSessionId() !== sendSession) return;
              var html = attachmentMsg(selectedMeta, kind, 'sending', localId);
              append(meMsg(html, '', clockNow()));
              selectedLog = pushLog({ who: 'me', html: html, time: clockNow() });
              setPlusPanel(false);
              setSessionStatus('');
            }
          });
          if (!result || result.cancelled) {
            setSessionStatus('');
            return;
          }
          var turn = String(result.turn_id || '');
          bindChatLogSession(sendSession);
          if (!selectedLog) {
            var html = attachmentMsg(result, kind, 'sent', localId);
            if (chatLogSessionId() === sendSession) append(meMsg(html, '', clockNow()));
            selectedLog = pushLog({ who: 'me', html: html, time: clockNow() });
          } else {
            paintAttachment('sent', Object.assign({}, selectedMeta || {}, result || {}));
          }
          selectedLog.messageRef = turn ? 'turn:' + turn + ':user' : '';
          selectedLog.turnId = turn;
          persistChatLog();
          setPlusPanel(false);
          setSessionStatus('');
          if (turn) {
            livePendingTurns[turn] = true;
            liveCurrentTurn = turn;
            liveSetCancel(true);
            var attachmentEl = liveEnsure(turn);
            livePresence(attachmentEl, true, '正在查看你发来的' + (kind === 'photo' ? '照片' : '文件'));
            liveAvatar(attachmentEl, 'read');
          }
          scheduleLivePoll(0);
        } catch (err) {
          if (typeof selectedLog !== 'undefined' && selectedLog) paintAttachment('failed', selectedMeta || {});
          var code = String(err && err.payload && err.payload.error || err && err.message || '');
          setSessionStatus(code === 'attachment_too_large'
            ? '文件太大，请选择 20 MB 以内的文件。'
            : '附件发送失败，请重试。');
        } finally {
          btn.disabled = false;
        }
      }
      if (plusToggle) plusToggle.addEventListener('click', onPlusToggle);
      root.addEventListener('click', onAttachmentPick);

      /* 表情面板里的贴图：点一张就发出去，然后收起面板（不跳页） */
      var stkState = (ctx && ctx.state && ctx.state !== 'empty' && ctx.state !== 'keyboard')
        ? ctx.state : 'normal';
      var stkItems = root.querySelectorAll('[data-stk]');
      var stickerToggle = root.querySelector('[data-sticker-toggle]');
      var stickerPanel = root.querySelector('.stkpanel');
      function setStickerPanel(open) {
        if (stickerPanel) stickerPanel.hidden = !open;
        if (stickerToggle) {
          stickerToggle.classList.toggle('is-on', !!open);
          stickerToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        }
      }
      function onStickerToggle(e) {
        e.preventDefault();
        e.stopPropagation();
        setStickerPanel(stickerPanel ? stickerPanel.hidden : false);
      }
      function onStkTap(e) {
        var s2 = pick(STICKERS, e.currentTarget.getAttribute('data-stk'), STICKERS[0].k);
        var html = '<span class="stkmsg">' + K.sticker(s2.k, { alt: s2.label }) + '</span>';
        append(meMsg(html, '', clockNow()));
        var stickerLog = pushLog({ who: 'me', html: html, time: clockNow() });
        /* Sticker media must use the same real attachment lane as photos/files.
           Never turn it into "[表情包：…]" text: that loses the actual pixels and makes
           Hermes treat a visual reaction as a caption. Until a bundled sticker asset is
           resolved to bytes by the native bridge, keep the local bubble but do not fake-send it. */
        if (live && T && typeof T.sendSticker === 'function') {
          T.sendSticker(s2.k, s2.label).then(function (accepted) {
            var turn = String(accepted && accepted.turn_id || '');
            if (!turn) return;
            stickerLog.messageRef = 'turn:' + turn + ':user';
            stickerLog.turnId = turn;
            persistChatLog();
            livePendingTurns[turn] = true;
            liveCurrentTurn = turn;
            liveSetCancel(true);
            scheduleLivePoll(0);
          }).catch(function () {
            setSessionStatus('表情包发送失败，请重试。');
          });
        } else if (live) {
          setSessionStatus('当前版本暂不能发送真实表情包图片。');
        }
        /* 收起表情面板但不触发整页 hashchange/render。之前这里重渲染聊天页，
           会把仍在 DOM 里的工具/思考进度一起销毁。 */
        setStickerPanel(false);
        try { history.replaceState(null, '', '#/chat?state=' + stkState); } catch (ignore) {}
      }
      if (stickerToggle) stickerToggle.addEventListener('click', onStickerToggle);
      for (var si = 0; si < stkItems.length; si++) stkItems[si].addEventListener('click', onStkTap);

      /* Android WebView 在不同系统/键盘上对 adjustResize 的 viewport 行为并不一致。
         同时监听 visualViewport：如果系统已经 resize，lift=0；如果键盘覆盖 WebView，
         就把输入区按实际遮挡高度抬起。这样不会写死 150/180px。 */
      var scr = root.querySelector('.screen--chat');
      var cwrap = root.querySelector('.composerwrap');
      var vv = window.visualViewport || null;
      var keyboardT = null;
      function syncKeyboardLift() {
        if (!cwrap) return;
        var focused = document.activeElement === input;
        var lift = 0;
        if (focused && vv) {
          lift = Math.max(0, Math.round(window.innerHeight - vv.height - vv.offsetTop));
        }
        cwrap.style.setProperty('--keyboard-lift', lift + 'px');
        if (focused) {
          requestAnimationFrame(function () { jumpTo(list.scrollHeight); });
        }
      }
      function onFocus() {
        if (scr) scr.classList.add('is-typing');
        syncKeyboardLift();
        clearTimeout(keyboardT);
        keyboardT = setTimeout(syncKeyboardLift, 80);
      }
      function onBlur()  {
        if (scr) scr.classList.remove('is-typing');
        clearTimeout(keyboardT);
        if (cwrap) cwrap.style.setProperty('--keyboard-lift', '0px');
      }
      input.addEventListener('focus', onFocus);
      input.addEventListener('blur', onBlur);
      if (vv) {
        vv.addEventListener('resize', syncKeyboardLift);
        vv.addEventListener('scroll', syncKeyboardLift);
      }

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
      /* GPT 风格 Activity：默认只是浅灰动作行；点某一行，只展开这一项的详情。 */
      function onActivityTap(e) {
        var row = e.target && e.target.closest ? e.target.closest('[data-activity-toggle]') : null;
        if (!row || !list.contains(row)) return;
        e.preventDefault();
        var item = row.closest('.activity-item');
        var detail = item && item.querySelector('.activity-detail');
        if (!detail) return;
        var open = detail.hidden;
        detail.hidden = !open;
        row.setAttribute('aria-expanded', open ? 'true' : 'false');
        item.classList.toggle('is-open', open);
      }
      list.addEventListener('click', onActivityTap);
      async function onApprovalTap(e) {
        var control = e.target.closest && e.target.closest('[data-approval-decision]');
        if (!control || !list.contains(control)) return;
        e.preventDefault();
        e.stopPropagation();
        var cardEl = control.closest('[data-approval-id]');
        var approvalId = cardEl && cardEl.getAttribute('data-approval-id');
        if (!approvalId || !T || typeof T.respondApproval !== 'function') return;
        var decision = control.getAttribute('data-approval-decision') || 'deny';
        var scope = control.getAttribute('data-approval-scope') || 'once';
        var buttons = cardEl.querySelectorAll('[data-approval-decision]');
        var status = cardEl.querySelector('[data-approval-status]');
        for (var ai = 0; ai < buttons.length; ai++) buttons[ai].disabled = true;
        if (status) status.textContent = '正在提交…';
        try {
          var result = await T.respondApproval(approvalId, decision, scope);
          resolveApprovalCard(approvalId, String(result && result.status || (decision === 'allow' ? 'approved' : 'denied')));
          scheduleLivePoll(0);
        } catch (err) {
          if (err && (err.status === 404 || err.status === 409)) {
            if (status) status.textContent = '这项请求已经失效';
            scheduleLiveBootstrap(0);
          } else {
            for (var aj = 0; aj < buttons.length; aj++) buttons[aj].disabled = false;
            if (status) status.textContent = '提交失败，请重试';
          }
        }
      }
      list.addEventListener('click', onApprovalTap);
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
        var routedStickerLog = pushLog({ who: 'me', html: html, time: clockNow() });
        if (live && T && typeof T.sendSticker === 'function') {
          T.sendSticker(sk.k, sk.label).then(function (accepted) {
            var turn = String(accepted && accepted.turn_id || '');
            if (!turn) return;
            routedStickerLog.messageRef = 'turn:' + turn + ':user';
            routedStickerLog.turnId = turn;
            persistChatLog();
            livePendingTurns[turn] = true;
            liveCurrentTurn = turn;
            liveSetCancel(true);
            scheduleLivePoll(0);
          }).catch(function () {
            setSessionStatus('表情包发送失败，请重试。');
          });
        } else if (live) {
          setSessionStatus('当前版本暂不能发送真实表情包图片。');
        }
      }

      async function onSessionDrawerClick(e) {
        var close = e.target && e.target.closest ? e.target.closest('[data-session-drawer-close]') : null;
        if (close) { setSessionDrawer(false); return; }

        var refresh = e.target && e.target.closest ? e.target.closest('[data-session-refresh]') : null;
        if (refresh) {
          e.preventDefault();
          refresh.disabled = true;
          try { await refreshSessions(); } finally { refresh.disabled = false; }
          return;
        }

        var item = e.target && e.target.closest ? e.target.closest('[data-session-key]') : null;
        if (!item || !root.contains(item)) return;
        e.preventDefault();
        var key = String(item.getAttribute('data-session-key') || '');
        var id = String(item.getAttribute('data-session-id') || '');
        var deleteButton = e.target && e.target.closest ? e.target.closest('[data-session-delete]') : null;
        if (deleteButton) {
          e.stopPropagation();
          if (!id || !T || typeof T.deleteSession !== 'function') {
            setSessionStatus('当前版本暂不支持删除服务器会话。');
            return;
          }
          deleteButton.disabled = true;
          setSessionStatus('正在删除会话…');
          try {
            await T.deleteSession(id);
            await refreshSessions();
            setSessionStatus('');
          } catch (err) {
            var code = String(err && err.payload && err.payload.error || '');
            setSessionStatus(code === 'active_session_delete_forbidden'
              ? '当前会话不能直接删除，请先切换到其他会话。'
              : '删除会话失败，请稍后重试。');
            deleteButton.disabled = false;
          }
          return;
        }
        if (!key && !id) return;
        var alreadyCurrent = CURRENT_SESSION_ID
          ? (id && id === CURRENT_SESSION_ID)
          : (CURRENT_SESSION_KEY && key && key === CURRENT_SESSION_KEY);
        if (alreadyCurrent) {
          setSessionDrawer(false);
          return;
        }
        if (liveSendInFlight || liveCurrentTurn || Object.keys(livePendingTurns).length
            || CHAT_OUTBOX.length || CHAT_OUTBOX_RETRY) {
          setSessionStatus('当前消息或回复尚未结束，请先完成或停止后再切换会话。');
          setSessionDrawer(false);
          return;
        }
        if (!T || typeof T.selectSession !== 'function') {
          setSessionStatus('当前版本暂不支持切换服务器会话。');
          setSessionDrawer(false);
          return;
        }

        setSessionStatus('正在切换会话…');
        setSessionDrawer(false);
        clearTimeout(livePollTimer);
        clearTimeout(liveBootstrapTimer);
        var previousSessionId = CURRENT_SESSION_ID;
        var previousSessionKey = CURRENT_SESSION_KEY;
        try {
          await T.selectSession(key, id);
          CURRENT_SESSION_ID = '';
          CURRENT_SESSION_KEY = '';
          /* 解绑旧会话：只清内存，绝不清空后回写旧 key（旧会话缓存必须原样保留）；
             新会话的缓存等 bootstrap 确认身份后再装入 */
          bindChatLogSession('');
          bindTurnActivitySession('');
          liveTurns = Object.create(null);
          liveCompleted = Object.create(null);
          liveCovered = Object.create(null);
          livePendingTurns = Object.create(null);
          liveCurrentTurn = '';
          liveSetCancel(false);
          list.innerHTML = liveEmpty();
          await liveBootstrap();
          await refreshSessions();
        } catch (err) {
          CURRENT_SESSION_ID = previousSessionId;
          CURRENT_SESSION_KEY = previousSessionKey;
          bindChatLogSession(previousSessionId || previousSessionKey || '');
          bindTurnActivitySession(previousSessionId || previousSessionKey || '');
          paintSessionList();
          setSessionStatus('会话切换失败，请稍后重试。');
        }
      }
      function onSessionOpen(e) {
        e.preventDefault();
        e.stopPropagation();
        setSessionDrawer(true);
        refreshSessions().catch(function () {});
      }
      if (sessionOpen) sessionOpen.addEventListener('click', onSessionOpen);
      if (sessionScrim) sessionScrim.addEventListener('click', onSessionDrawerClick);
      if (sessionDrawer) sessionDrawer.addEventListener('click', onSessionDrawerClick);

      async function startLiveTransport() {
        if (!T) {
          live = false;
          setSessionStatus('Mobile Transport 不可用');
          return;
        }
        try {
          if (typeof T.ensureToken === 'function') await T.ensureToken(false);
          live = true;
          refreshHermesModelControls(true);
          liveBootstrap();
        } catch (err) {
          live = false;
          setSessionStatus('服务暂时不可用，正在自动恢复…');
        }
      }
      startLiveTransport();

      function onComposerInput() {
        CHAT_USER_INPUT_AT = Date.now();
        if (CHAT_OUTBOX.length || CHAT_OUTBOX_RETRY) scheduleOutboxDrain();
      }
      function onKey(e) {
        if (e.isComposing || e.keyCode === 229) return;
        if (e.key === 'Enter') push();
      }
      input.addEventListener('input', onComposerInput);
      input.addEventListener('keydown', onKey);
      send.addEventListener('click', push);
      if (stop) stop.addEventListener('click', liveCancel);
      if (mic) mic.addEventListener('click', onVoiceInput);
      return function () {
        root.removeEventListener('click', onChatMenuTap);
        root.removeEventListener('click', onHermesControl);
        if (sessionOpen) sessionOpen.removeEventListener('click', onSessionOpen);
        if (sessionScrim) sessionScrim.removeEventListener('click', onSessionDrawerClick);
        if (sessionDrawer) sessionDrawer.removeEventListener('click', onSessionDrawerClick);
        input.removeEventListener('input', onComposerInput);
        input.removeEventListener('keydown', onKey);
        send.removeEventListener('click', push);
        if (stop) stop.removeEventListener('click', liveCancel);
        if (mic) mic.removeEventListener('click', onVoiceInput);
        input.removeEventListener('focus', onFocus);
        input.removeEventListener('blur', onBlur);
        if (vv) {
          vv.removeEventListener('resize', syncKeyboardLift);
          vv.removeEventListener('scroll', syncKeyboardLift);
        }
        clearTimeout(keyboardT);

        if (plusToggle) plusToggle.removeEventListener('click', onPlusToggle);
        root.removeEventListener('click', onAttachmentPick);
        if (stickerToggle) stickerToggle.removeEventListener('click', onStickerToggle);
        for (var sj = 0; sj < stkItems.length; sj++) stkItems[sj].removeEventListener('click', onStkTap);
        if (upill) upill.removeEventListener('click', onPill);
        list.removeEventListener('scroll', onScroll);
        list.removeEventListener('click', onApprovalTap);
        list.removeEventListener('click', onActivityTap);
        send.removeEventListener('click', push);
        if (mic) mic.removeEventListener('click', onVoiceInput);
        liveStopped = true;
        clearTimeout(livePollTimer);
        clearTimeout(liveOutboxTimer);
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
        + ' title="FOX_PIXEL_SPRITE · 叶青栩"'
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
                   + (muted ? ' · 已静音' : '')
                   + ' · <span data-calltime>' + callClock() + '</span>';

      return `
      <div class="screen screen--call">
        <div class="call">
          ${share
            ? '<div class="call__share">'
              + '<span class="call__share-ic">' + icon('screen', 26) + '</span>'
              + '<span class="call__share-t">正在共享这块屏幕</span>'
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
      /* 真机不生成任何演示通话转写；真实语音接入后只写真实转写。 */
      var t = null;
      return function () {
        if (t) clearInterval(t);
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

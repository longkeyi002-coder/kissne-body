/* =====================================================================
   Kissne 手机端 UI · screens-b.js
   页面 07–14：记忆库 / 设备管理 / 设置 / 通知 / Skills / MCP / 运维
   ===================================================================== */
(function () {
  'use strict';
  var K = window.KSN;
  var ph = K.ph, btn = K.btn, icon = K.icon, chip = K.chip, appbar = K.appbar,
      card = K.card, field = K.field, tabbar = K.tabbar, modal = K.modal,
      note = K.note, sectionTitle = K.sectionTitle, listRow = K.listRow,
      banner = K.banner, kv = K.kv, toast = K.toast, esc = K.esc;

  /* =====================================================================
     07 记忆库页 — Lifemem external provider journal projection
     ===================================================================== */
  var MEMORY_STATES = [{ key: 'list', label: '时间线' }, { key: 'detail', label: '记忆详情' }];
  var MEMORY_INDEX = { items: [], builtin: [], loaded: false, error: '', space: '', query: '', mode: 'active' };
  var MEMORY_SPACES = [
    { k: '', v: '全部' }, { k: 'reality', v: '现实' }, { k: 'relationship', v: '关系' },
    { k: 'ai_self', v: '叶青栩' }, { k: 'ai_world', v: '小机星' }
  ];

  function memoryItemById(id) {
    id=String(id||'');
    return MEMORY_INDEX.items.concat(MEMORY_INDEX.builtin || []).find(function(item){ return String(item.id||'')===id; }) || null;
  }
  function memoryTitle(item) { return String(item && item.title || '未命名记忆'); }
  function memorySpaceLabel(space) {
    var row=MEMORY_SPACES.find(function(x){return x.k===String(space||'');});
    return row ? row.v : String(space||'');
  }
  function memoryTime(value) {
    var n=Number(value||0); if(!n) return '';
    var d=new Date(n*1000); return isNaN(d.getTime()) ? '' : d.toLocaleString([], {year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
  }
  function memoryTimelineHtml() {
    if(!MEMORY_INDEX.loaded && MEMORY_INDEX.error) return '<div class="mempty"><div class="mempty__t">暂时无法读取记忆库</div><div class="mempty__s">Lifemem 当前不可用。</div></div>';
    if(!MEMORY_INDEX.loaded) return '<div class="mempty"><div class="mempty__t">正在读取记忆…</div></div>';
    var all = MEMORY_INDEX.items.concat(MEMORY_INDEX.builtin || []);
    if(!all.length) return '<div class="mempty"><div class="mempty__t">暂无匹配记忆</div><div class="mempty__s">这里显示 Runtime 已确认写入的长期记忆。</div></div>';
    return '<div class="memtimeline">'+all.map(function(item){
      return '<a class="memtimeline__item" data-nav="#/memory?state=detail&id='+encodeURIComponent(String(item.id||''))+'">'
        +'<span class="memtimeline__dot"></span><span class="memtimeline__time">'+esc(memoryTime(item.occurred_at))+'</span>'
        +'<span class="memtimeline__card"><b>'+esc(memoryTitle(item))+'</b>'
        +'<span>'+esc(memorySpaceLabel(item.memory_space))+(item.emotion?' · '+esc(item.emotion):'')+'</span></span></a>';
    }).join('')+'</div>';
  }

  K.registerScreen({
    no:'07', id:'memory', name:'记忆库页', route:'#/memory', tab:null,
    purpose:'读取 Lifemem 外部记忆供应商的真实时间线；不读取 Hermes builtin MEMORY.md / USER.md。',
    out:['#/home','#/memory?state=detail'], states:MEMORY_STATES,
    render:function(ctx){
      var state=ctx.state||'list', id=ctx.params&&ctx.params.get('id')||'', item=memoryItemById(id);
      if(state==='detail'){
        var detail=item
          ? '<div class="memdetail"><h2 class="memdetail__t">'+esc(memoryTitle(item))+'</h2>'
            +'<div class="memdetail__meta">'+chip(memorySpaceLabel(item.memory_space))+'<span class="muted">'+esc(memoryTime(item.occurred_at))+'</span></div>'
            +'<p class="muted">'+esc(item.status==='candidate'?'待审核 · '+(item.admission_reason||''):'已生效')+'</p>'
            +'<p class="memdetail__body">'+esc(item.body||item.text||'')+'</p>'
            +(item.evidence_context?'<details><summary>查看原话附近语境</summary><p>'+esc(item.evidence_context)+'</p></details>':'')
            +(item.source_ref&&item.source_ref.session_id?'<div class="muted">来源会话 '+esc(item.source_ref.session_id)+' · turn '+esc(item.source_ref.turn_id||0)+'</div>':'')
            +(item.source?'<div class="muted">来源：'+esc(item.source)+'</div>':'')
            +(item.status==='candidate'?'<div class="memreviewform">'
              +'<label>记忆内容<input data-review-summary value="'+esc(item.title||'')+'"></label>'
              +'<label>归属主体<input data-review-subject value="'+esc(item.subject||'')+'" placeholder="例如：用户、Kissne"></label>'
              +'<label>适用范围<input data-review-scope value="'+esc(item.scope||'')+'" placeholder="例如：Kissne界面约定"></label>'
              +'<label>类型<select data-review-category>'+['fact','preference','agreement','event','project','relationship','temporary'].map(function(c){return '<option value="'+c+'"'+(item.category===c?' selected':'')+'>'+({fact:'事实',preference:'偏好',agreement:'约定',event:'经历',project:'项目',relationship:'关系',temporary:'临时'})[c]+'</option>';}).join('')+'</select></label>'
              +'<button class="btn" data-memory-review="approve" data-id="'+esc(item.id)+'">确认记住</button>'
              +'<button class="btn btn--ghost" data-memory-review="reject" data-id="'+esc(item.id)+'">不记住</button></div>':'')
            +(item.deletable?'<button type="button" class="btn btn--ghost is-small" data-memory-delete="'+esc(item.id)+'" style="margin-top:12px">删除这条记忆</button>':'')
            +'</div>'
          : '<div class="mempty"><div class="mempty__t">这条记忆不在当前时间线中</div></div>';
        return '<div class="screen">'+appbar({title:'记忆详情',back:'#/memory'})+'<div class="screen__body"><div data-memory-notice hidden></div>'+detail+'</div></div>';
      }
      var filters='<div class="chips">'+MEMORY_SPACES.map(function(row){
        return '<button class="chip'+(MEMORY_INDEX.space===row.k?' is-on':'')+'" data-memory-space="'+esc(row.k)+'">'+esc(row.v)+'</button>';
      }).join('')+'</div>';
      return '<div class="screen">'+appbar({title:'记忆库',sub:'Lifemem · 时间线',back:'#/home',
        right:'<button class="iconbtn" data-memory-refresh aria-label="刷新">'+icon('sync')+'</button>'})
        +'<div class="screen__body"><div class="searchbar"><span>'+icon('search',16)+'</span>'
        +'<input class="memorysearch" data-memory-search placeholder="搜索时间线" value="'+esc(MEMORY_INDEX.query)+'"></div>'
        +'<div class="chips"><button class="chip" data-memory-mode="active">已记住</button><button class="chip" data-memory-mode="candidate">待审核</button></div>'+filters+'<div class="adminnotice" data-memory-notice hidden></div><div data-memory-list>'+memoryTimelineHtml()+'</div></div></div>';
    },
    mount:function(root,ctx){
      var T=window.KissneTransport, host=root.querySelector('[data-memory-list]'), refresh=root.querySelector('[data-memory-refresh]');
      var search=root.querySelector('[data-memory-search]'), notice=root.querySelector('[data-memory-notice]'), stopped=false, timer=0, requestSeq=0;
      function show(text){if(notice){notice.hidden=!text;notice.textContent=text||'';}}
      function paint(){if(host&&!stopped)host.innerHTML=memoryTimelineHtml();}
      async function reload(){
        if(!T||typeof T.memoryTimeline!=='function'){MEMORY_INDEX.loaded=false;MEMORY_INDEX.error='transport_unavailable';paint();return;}
        var seq=++requestSeq, mode=MEMORY_INDEX.mode;
        show('正在读取 Lifemem…');
        try{
          if(typeof T.ensureToken==='function') await T.ensureToken(false);
          var payload=mode==='candidate'
            ? await T.memoryCandidates()
            : await T.memoryTimeline({limit:100,space:MEMORY_INDEX.space,q:MEMORY_INDEX.query});
          if(stopped||seq!==requestSeq)return;
          MEMORY_INDEX.items=(Array.isArray(payload&&payload.items)?payload.items:[]).map(function(item){
            return mode==='candidate'?Object.assign({},item,{title:item.summary,body:item.quote,source_ref:{session_id:item.session_id,turn_id:item.turn_id}}):item;
          }).filter(function(item){return MEMORY_INDEX.mode!=='candidate'||((!MEMORY_INDEX.space||item.memory_space===MEMORY_INDEX.space)&&(!MEMORY_INDEX.query||String(item.title+' '+item.body).indexOf(MEMORY_INDEX.query)>=0));});
          MEMORY_INDEX.builtin=[];
          MEMORY_INDEX.loaded=true; MEMORY_INDEX.error=''; if(!stopped){show('');paint();}
        }catch(err){if(stopped||seq!==requestSeq)return;MEMORY_INDEX.loaded=false;MEMORY_INDEX.error=String(err&&err.message||'memory_unavailable');if(!stopped){show('记忆库读取失败');paint();}}
      }
      function onRefresh(e){e.preventDefault();reload();}
      function onSpace(e){var b=e.target.closest('[data-memory-space]');if(!b)return;MEMORY_INDEX.space=String(b.getAttribute('data-memory-space')||'');location.hash='#/memory';reload();}
      function onSearch(){clearTimeout(timer);timer=setTimeout(function(){MEMORY_INDEX.query=String(search&&search.value||'').trim();reload();},320);}
      async function onDelete(e){
        var b=e.target.closest('[data-memory-delete]'); if(!b||!T||typeof T.deleteAdminMemory!=='function')return;
        e.preventDefault(); b.disabled=true;
        try { await T.deleteAdminMemory(b.getAttribute('data-memory-delete')); await reload(); location.hash='#/memory'; }
        catch (err) { show('删除记忆失败'); b.disabled=false; }
      }
      async function onReview(e){
        var mode=e.target.closest('[data-memory-mode]');
        if(mode){MEMORY_INDEX.mode=mode.getAttribute('data-memory-mode');reload();return;}
        var b=e.target.closest('[data-memory-review]');if(!b||!T||!T.reviewMemory)return;
        e.preventDefault();b.disabled=true;
        var payload={action:b.getAttribute('data-memory-review'),id:Number(b.getAttribute('data-id'))};
        if(payload.action==='approve'){
          payload.updates={};
          ['summary','subject','scope','category'].forEach(function(k){var el=root.querySelector('[data-review-'+k+']');payload.updates[k]=el?el.value:'';});
        }
        try{await T.reviewMemory(payload);MEMORY_INDEX.loaded=false;location.hash='#/memory';}
        catch(err){show('审核未完成：'+String(err&&err.message||err));b.disabled=false;}
      }
      root.addEventListener('click',onReview);
      if(refresh)refresh.addEventListener('click',onRefresh);
      root.addEventListener('click',onSpace);
      root.addEventListener('click',onDelete);
      if(search)search.addEventListener('input',onSearch);
      if((ctx&&ctx.state||'list')==='list')reload();
      return function(){root.removeEventListener('click',onReview);stopped=true;clearTimeout(timer);if(refresh)refresh.removeEventListener('click',onRefresh);root.removeEventListener('click',onSpace);root.removeEventListener('click',onDelete);if(search)search.removeEventListener('input',onSearch);};
    }
  });

  /* =====================================================================
     08 高级诊断页
     ===================================================================== */
  K.registerScreen({
    no: '08', id: 'device', name: '高级诊断', route: '#/device', tab: null,
    purpose: '仅用于排查运行问题。认证、token 续期和服务恢复均由 App 自动完成。',
    out: ['#/home', '#/settings'],
    states: [{ key: 'normal', label: '自动状态' }],
    render: function () {
      return `
      <div class="screen">
        ${appbar({ title: '高级诊断', back: '#/settings',
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
          ${note('这些信息仅用于诊断。已配对设备会自动恢复；首次使用或凭据失效时必须重新输入一次性配对码。')}
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
              throw err;
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
          <div class="srchbox sessionpage__search">
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
        try { row.blur(); } catch (ignore) {}
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
          var idx = window.KissneSessionIndex || {};
          (idx.sessions || []).forEach(function (s) {
            s.active = id ? s.id === id : (!!key && s.key === key);
          });
          if (idx.raw && id) idx.raw.active_session_id = id;
          paint();
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
    purpose: '账号信息、通知、运维、版本更新与高级诊断入口。',
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
            + listRow({ title: '高级诊断', sub: '服务状态 / 安装标识', icon: 'plug', to: '#/device' })
            + listRow({ title: '会话列表', sub: '查看服务器上的全部对话', icon: 'chat', to: '#/sessions' })
            + listRow({ title: '本地 Laya（实验）', sub: '在手机上判断长期记忆候选', icon: 'cpu', to: '#/laya' })
            + listRow({ title: '模型设置', sub: '跟随 Hermes', icon: 'cpu' })
            + listRow({ title: '通知设置', sub: '新消息 / 服务状态 / 记忆同步', icon: 'bell', to: '#/notifications' })
            + listRow({ title: '运维与部署', sub: '版本 / 上游合并 / 回滚 / 部署日志', icon: 'server', to: '#/admin' })
          , { tight: true })}
          ${card(
            listRow({ title: '检查更新', sub: '检查并下载最新 Kissne APK', icon: 'refresh', action: 'check-update', right: chip('自动检查', 'solid') })
            + listRow({ title: '关于 Kissne', sub: 'V0.2.23 · Android 合体版', icon: 'info' })
          , { tight: true })}
          ${note('版本更新会自动检查；发现新版本后可在 App 内直接下载，再由 Android 系统确认安装。')}
        </div>
      </div>`;
    }
  });


  /* =====================================================================
     本地 Laya 实验页
     ===================================================================== */
  K.registerScreen({
    no: '09A', id: 'laya', name: '本地 Laya', route: '#/laya', tab: null,
    purpose: 'Laya 在手机本地运行。模型只保存在本机；输入不会上传，也不会自动写入记忆。',
    out: ['#/settings'], states: [{ key: 'default', label: '默认' }],
    render: function () {
      return '<div class="screen">'
        + appbar({ title: '本地 Laya', sub: '手机端实验', back: '#/settings' })
        + '<div class="screen__body">'
        + card('<div class="muted">首次需要从 Hugging Face 下载约 648 MiB 模型文件，保存在手机本机。请连接 Wi-Fi 并预留约 700 MB 空间。模型和推理均在手机本地运行，不经过 Kissne 服务器。</div>')
        + '<div class="field"><label class="field__label" for="layaInput">要判断的内容</label>'
        + '<textarea id="layaInput" data-laya-input rows="4" maxlength="1200" placeholder="例如：我每周三晚上要去游泳"></textarea></div>'
        + '<div class="row" style="gap:10px;margin:12px 0">'
        + '<button class="btn btn--primary" type="button" data-laya-run>判断是否适合作为记忆</button>'
        + '<button class="btn" type="button" data-laya-download>下载 / 安装模型</button></div>'
        + '<div class="adminnotice" data-laya-status role="status">正在检查模型状态…</div>'
        + '<div class="card" data-laya-result hidden style="margin-top:12px;white-space:pre-line"></div>'
        + note('实验功能：Laya 的中文效果尚未在你的手机上验证。结果只作参考，不会保存或发送。')
        + '</div></div>';
    },
    mount: function(root) {
      var T=window.KissneTransport, status=root.querySelector('[data-laya-status]');
      var input=root.querySelector('[data-laya-input]'), run=root.querySelector('[data-laya-run]');
      var download=root.querySelector('[data-laya-download]'), result=root.querySelector('[data-laya-result]');
      var stopped=false, timer=null, busy=false;
      function show(p) {
        if(!status||stopped)return;
        if(!p||!p.supported){status.textContent='此功能需要 Kissne Android 原生 App。';return;}
        if(p.downloading){status.textContent='正在下载模型：'+Math.round((p.progress||0)*100)+'%';return;}
        status.textContent=p.installed?'模型已在本机安装，可离线判断。':'模型尚未下载（约 648 MiB）。';
      }
      async function refresh() {
        if(!T||typeof T.layaStatus!=='function'){show({supported:false});return;}
        try{show(await T.layaStatus());}catch(e){if(status)status.textContent='无法读取本地 Laya 状态：'+String(e.message||e);}
      }
      async function install() {
        if(busy||!T||!T.layaDownload)return;
        busy=true;download.disabled=true;
        try{await T.layaDownload();await refresh();}
        catch(e){if(status)status.textContent='模型下载失败：'+String(e.message||e);}
        finally{busy=false;download.disabled=false;}
      }
      async function classify() {
        var text=String(input&&input.value||'').trim();
        if(!text){if(status)status.textContent='先输入一段内容。';return;}
        if(busy||!T||!T.layaClassify)return;
        busy=true;run.disabled=true;result.hidden=false;result.textContent='正在手机本地推理…';
        try {
          var p=await T.layaClassify(text), a=p.answer||{}, probs=a.probabilities||{};
          var labels=Object.keys(probs);
          result.textContent='判断：'+String(a.choice||'')+' · 置信度 '+String(a.confidence||0)+'\n'
            +'判定来源：'+(a.heuristic_override?'本地规则已纠正模型的过度否定':'Laya 模型')+'\n'
            +labels.map(function(k){return k+' '+probs[k];}).join(' / ')
            +'\n推理耗时约 '+Math.round(p.elapsed_ms||0)+' ms';
        } catch(e){result.textContent='本地判断失败：'+String(e.message||e);}
        finally{busy=false;run.disabled=false;await refresh();}
      }
      if(run)run.addEventListener('click',classify);
      if(download)download.addEventListener('click',install);
      refresh();timer=setInterval(refresh,1500);
      return function(){stopped=true;if(timer)clearInterval(timer);if(run)run.removeEventListener('click',classify);if(download)download.removeEventListener('click',install);};
    }
  });

  /* =====================================================================
     10 通知和弹窗
     ===================================================================== */
  K.registerScreen({
    no: '10', id: 'notifications', name: '通知和弹窗', route: '#/notifications', tab: null,
    purpose: '消息、服务恢复、记忆同步与确认操作的通知状态。',
    out: ['#/chat', '#/memory'],
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
            + '<div class="demo">' + toast({ icon: 'check', kind: 'ok', title: '服务已恢复', body: 'Kissne 已自动恢复，可以继续使用', time: '09:41' }) + '</div>'
            + '<div class="demo">' + toast({ icon: 'check', title: '记忆已保存', body: '「周末计划」已写入记忆库', time: '09:38' }) + '</div>'
          , { tight: true })}

          ${sectionTitle('状态横幅')}
          ${card(
            '<div class="demo">' + banner({ icon: 'wifioff', kind: 'warn', title: '服务暂时不可用',
              body: 'Kissne 正在后台自动恢复，聊天记录不会丢失。' }) + '</div>'
            + '<div class="demo">' + banner({ icon: 'alert', kind: 'warn', title: '记忆同步暂缓',
              body: '服务恢复后会自动继续同步。' }) + '</div>'

          , { tight: true })}

          ${sectionTitle('确认弹窗')}
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
            T.ensureToken(false).then(function () {
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



  /* =====================================================================
     13 Skills
     ===================================================================== */
  var SKILL_INDEX = { items: [], loaded: false, error: '' };
  function skillsHtml() {
    if (!SKILL_INDEX.loaded) return '<div class="mempty">正在读取 Runtime Skills…</div>';
    if (SKILL_INDEX.error) return '<div class="mempty"><div class="mempty__t">暂时无法读取 Skills</div><div class="mempty__s">'+esc(SKILL_INDEX.error)+'</div></div>';
    if (!SKILL_INDEX.items.length) return '<div class="mempty"><div class="mempty__t">当前没有已安装 Skill</div></div>';
    return '<div class="list">'+SKILL_INDEX.items.map(function(item){
      return listRow({ title: item.name || '未命名 Skill', sub: (item.description || '已从 Hermes Runtime 读取') + ' · ' + (item.source || '本地'), icon: 'box' });
    }).join('')+'</div>';
  }
  K.registerScreen({
    no: '13', id: 'skills', name: 'Skills', route: '#/skills', tab: null,
    purpose: '读取 Hermes Runtime 当前实际安装的 Skills。',
    out: ['#/home', '#/settings'],
    states: [{ key: 'default', label: '默认' }],
    render: function () {
      return '<div class="screen">'
        + appbar({ title: 'Skills', sub: 'Hermes Runtime · 已安装能力', back: '#/home', right: '<button class="iconbtn" data-skills-refresh aria-label="刷新">'+icon('refresh')+'</button>' })
        + '<div class="screen__body">'
        + '<div class="adminnotice" data-skills-notice hidden></div><div data-skills-list>'+skillsHtml()+'</div>'
        + '</div></div>';
    },
    mount: function(root) {
      var T=window.KissneTransport, host=root.querySelector('[data-skills-list]'), notice=root.querySelector('[data-skills-notice]'), refresh=root.querySelector('[data-skills-refresh]'), stopped=false;
      function paint(){if(host&&!stopped)host.innerHTML=skillsHtml();}
      async function reload(){
        if(!T||typeof T.adminSkills!=='function'){SKILL_INDEX.loaded=true;SKILL_INDEX.error='当前版本未接入 Skills 数据接口';paint();return;}
        try{if(T.ensureToken)await T.ensureToken(false);var p=await T.adminSkills();SKILL_INDEX.items=Array.isArray(p&&p.items)?p.items:[];SKILL_INDEX.loaded=true;SKILL_INDEX.error='';paint();}
        catch(err){SKILL_INDEX.loaded=true;SKILL_INDEX.error=String(err&&err.message||'skills_unavailable');if(notice){notice.hidden=false;notice.textContent='Skills 读取失败';}paint();}
      }
      if(refresh)refresh.addEventListener('click',reload);reload();
      return function(){stopped=true;if(refresh)refresh.removeEventListener('click',reload);};
    }
  });

  /* =====================================================================
     14 MCP
     ===================================================================== */
  var MCP_INDEX = { items: [], loaded: false, error: '' };
  function mcpHtml() {
    if (!MCP_INDEX.loaded) return '<div class="mempty">正在读取 MCP Runtime…</div>';
    if (MCP_INDEX.error) return '<div class="mempty"><div class="mempty__t">暂时无法读取 MCP</div><div class="mempty__s">'+esc(MCP_INDEX.error)+'</div></div>';
    if (!MCP_INDEX.items.length) return '<div class="mempty"><div class="mempty__t">当前没有配置 MCP Server</div><div class="mempty__s">页面只显示真实配置，不生成演示服务器。</div></div>';
    return '<div class="list">'+MCP_INDEX.items.map(function(item){
      var state=item.connected?'已连接':(item.enabled?'已配置':'已停用');
      var transport=item.transport==='stdio'?'本地进程':(item.transport==='http'?'HTTP':'未识别');
      return listRow({ title: item.name, sub: state+' · '+transport+(item.url?' · '+item.url:'')+(item.tool_count!=null?' · '+item.tool_count+' 个工具':''), icon: 'server' });
    }).join('')+'</div>';
  }
  K.registerScreen({
    no: '14', id: 'mcp', name: 'MCP', route: '#/mcp', tab: null,
    purpose: '读取 Hermes Runtime 当前配置与连接状态的 MCP Server。',
    out: ['#/home', '#/settings'],
    states: [{ key: 'default', label: '默认' }],
    render: function () {
      return '<div class="screen">'
        + appbar({ title: 'MCP', sub: 'Runtime · 外部工具与数据源', back: '#/home', right: '<button class="iconbtn" data-mcp-refresh aria-label="刷新">'+icon('refresh')+'</button>' })
        + '<div class="screen__body">'
        + '<div class="adminnotice" data-mcp-notice hidden></div><div data-mcp-list>'+mcpHtml()+'</div>'
        + '</div></div>';
    },
    mount: function(root) {
      var T=window.KissneTransport,host=root.querySelector('[data-mcp-list]'),notice=root.querySelector('[data-mcp-notice]'),refresh=root.querySelector('[data-mcp-refresh]'),stopped=false;
      function paint(){if(host&&!stopped)host.innerHTML=mcpHtml();}
      async function reload(){
        if(!T||typeof T.adminMcp!=='function'){MCP_INDEX.loaded=true;MCP_INDEX.error='当前版本未接入 MCP 数据接口';paint();return;}
        try{if(T.ensureToken)await T.ensureToken(false);var p=await T.adminMcp();MCP_INDEX.items=Array.isArray(p&&p.items)?p.items:[];MCP_INDEX.loaded=true;MCP_INDEX.error='';paint();}
        catch(err){MCP_INDEX.loaded=true;MCP_INDEX.error=String(err&&err.message||'mcp_unavailable');if(notice){notice.hidden=false;notice.textContent='MCP 读取失败';}paint();}
      }
      if(refresh)refresh.addEventListener('click',reload);reload();
      return function(){stopped=true;if(refresh)refresh.removeEventListener('click',reload);};
    }
  });

})();



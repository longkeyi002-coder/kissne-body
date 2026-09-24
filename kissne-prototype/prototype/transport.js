/* Kissne prototype -> real Kissne Mobile transport. UI-free. */
(function () {
  'use strict';

  /* Android app shell: keep credentials/networking in the native layer.
     The browser/file:// prototype below remains as a standalone fallback. */
  var Native = window.KissneNativeTransport;
  if (Native && typeof Native.request === 'function') {
    var nativeSeq = 0;
    var nativePending = Object.create(null);

    function NativeApiError(status, payload, message) {
      this.name = 'KissneApiError';
      this.status = Number(status) || 0;
      this.payload = payload || null;
      this.message = message || (payload && payload.error) || ('HTTP ' + this.status);
    }
    NativeApiError.prototype = Object.create(Error.prototype);

    function nativeBase(value) {
      var v = String(value || '').trim();
      if (!v) return String(Native.getBase() || '').replace(/\/+$/, '');
      if (!/^https?:\/\//i.test(v)) {
        /* Bare private/LAN endpoints are the only implicit cleartext case.
           Public names keep HTTPS as the safe default. */
        var host = v.split('/')[0].split(':')[0].toLowerCase();
        var local = host === 'localhost' || host === '127.0.0.1' ||
          /^10\./.test(host) || /^192\.168\./.test(host) ||
          /^172\.(1[6-9]|2\d|3[0-1])\./.test(host);
        v = (local ? 'http://' : 'https://') + v;
      }
      return v.replace(/\/+$/, '');
    }
    function nativeMessageId() {
      var r = '';
      try { r = (crypto && crypto.randomUUID) ? crypto.randomUUID() : ''; } catch (e) {}
      if (!r) r = Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
      return 'android-web-' + r;
    }
    function nativeCall(action, payload, timeoutMs, hooks) {
      return new Promise(function (resolve, reject) {
        var id = 'n' + (++nativeSeq);
        var timer = setTimeout(function () {
          var waiter = nativePending[id];
          if (!waiter) return;
          delete nativePending[id];
          reject(new NativeApiError(0, { error: 'native_timeout' }, 'native_timeout'));
        }, Number(timeoutMs) > 0 ? Number(timeoutMs) : 15000);
        nativePending[id] = {
          resolve: function (value) { clearTimeout(timer); resolve(value); },
          reject: function (error) { clearTimeout(timer); reject(error); },
          selected: hooks && typeof hooks.selected === 'function' ? hooks.selected : null
        };
        try {
          Native.request(id, action, JSON.stringify(payload || {}));
        } catch (err) {
          clearTimeout(timer);
          delete nativePending[id];
          reject(new NativeApiError(0, null, err && err.message ? err.message : 'native_bridge_error'));
        }
      });
    }
    window.KissneNativeBridge = {
      attachmentSelected: function (id, raw) {
        var waiter = nativePending[id];
        if (!waiter || typeof waiter.selected !== 'function') return;
        var payload = {};
        try { payload = raw ? JSON.parse(raw) : {}; } catch (e) { payload = {}; }
        waiter.selected(payload);
      },
      resolve: function (id, ok, raw) {
        var waiter = nativePending[id];
        if (!waiter) return;
        delete nativePending[id];
        var payload = {};
        try { payload = raw ? JSON.parse(raw) : {}; } catch (e) { payload = { raw: raw }; }
        if (ok) waiter.resolve(payload);
        else {
          var status = Number(payload && payload.status) || 0;
          waiter.reject(new NativeApiError(status, payload, payload && payload.error));
        }
      }
    };

    window.KissneTransport = {
      ApiError: NativeApiError,
      base: function () { return nativeBase(''); },
      setBase: function (value) { return String(Native.setBase(nativeBase(value)) || nativeBase(value)); },
      installationId: function () { return String(Native.installationId() || ''); },
      token: function () { return Native.hasToken() ? 'native-secure' : ''; },
      hasToken: function () { return !!Native.hasToken(); },
      hasBootstrapCache: function () {
        return typeof Native.hasBootstrapCache === 'function' && !!Native.hasBootstrapCache();
      },
      isConnected: function () { return typeof Native.isConnected === 'function' ? !!Native.isConnected() : !!Native.hasToken(); },
      clearToken: function () { Native.clearToken(); },
      cursor: function () {
        var n = Number(Native.getCursor());
        return isFinite(n) && n >= 0 ? n : 0;
      },
      pair: function (opts) {
        opts = opts || {};
        var base = nativeBase(opts.apiBase || '');
        if (base) Native.setBase(base);
        return nativeCall('pair', { api_base: base, pairing_code: String(opts.pairingCode || opts.pairing_code || '') });
      },
      ensureToken: function (force) {
        return nativeCall('ensureToken', { force: !!force });
      },
      sessions: function () { return nativeCall('sessions', {}); },
      history: function (limit, before) { return nativeCall('history', { limit: Number(limit) || 50, before: String(before || '') }); },
      search: function (q, limit) { return nativeCall('search', { q: String(q || ''), limit: Number(limit) || 20 }); },
      deleteSession: function (sessionId) { return nativeCall('deleteSession', { session_id: String(sessionId || '') }); },
      selectSession: function (sessionKey, sessionId) {
        return nativeCall('selectSession', {
          session_key: String(sessionKey || ''),
          session_id: String(sessionId || '')
        });
      },
      bootstrap: function (force) {
        return nativeCall('bootstrap', {
          cursor: Number(Native.getCursor()) || 0,
          force: !!force
        });
      },
      sendText: function (text, messageId, replyTo) {
        return nativeCall('sendText', {
          text: String(text || ''),
          message_id: messageId || nativeMessageId(),
          reply_to: String(replyTo || '')
        });
      },
      poll: function () { return nativeCall('poll', { cursor: Number(Native.getCursor()) || 0 }); },
      ack: function (nextCursor) { return nativeCall('ack', { cursor: Number(nextCursor) || 0 }); },
      cancel: function (turnId) { return nativeCall('cancel', { turn_id: String(turnId || '') }); },
      voiceInput: function () { return nativeCall('voiceInput', {}, 45000); },
      pickAttachment: function (kind, hooks) {
        return nativeCall('pickAttachment', { kind: String(kind || 'file') }, 120000, hooks || null);
      },
      sendSticker: async function (key, label) {
        var assets = window.KSN && window.KSN.ASSETS;
        var rel = assets && assets.stickers && assets.stickers[String(key || '')];
        if (!rel) throw new Error('sticker_asset_not_found');
        var url = new URL('assets/' + rel, location.href).toString();
        var response = await fetch(url, { cache: 'force-cache' });
        if (!response.ok) throw new Error('sticker_asset_read_failed');
        var blob = await response.blob();
        var buffer = await blob.arrayBuffer();
        var bytes = new Uint8Array(buffer);
        var chunk = 0x8000, binary = '';
        for (var i = 0; i < bytes.length; i += chunk) {
          binary += String.fromCharCode.apply(null, bytes.subarray(i, Math.min(i + chunk, bytes.length)));
        }
        return nativeCall('sendSticker', {
          key: String(key || ''),
          label: String(label || key || ''),
          mime_type: blob.type || 'image/webp',
          bytes_base64: btoa(binary)
        }, 120000);
      },
      modelOptions: function () { return nativeCall('modelOptions', {}); },
      setModel: function (model, effort, provider) {
        return nativeCall('setModel', {
          model: String(model || ''),
          effort: String(effort || ''),
          provider: String(provider || '')
        });
      },
      respondApproval: function (approvalId, decision, scope) {
        return nativeCall('approval', {
          approval_id: String(approvalId || ''),
          decision: String(decision || ''),
          scope: String(scope || 'once')
        });
      },
      adminStatus: function () { return nativeCall('adminStatus', {}); },
      revoke: function () { return nativeCall('revoke', {}); }
    };
    return;
  }
  var KEY = {
    base: 'kissne.web.api_base',
    installation: 'kissne.web.installation_id',
    token: 'kissne.web.device_token',
    cursor: 'kissne.web.cursor'
  };
  var webBootstrapCache = null;
  var webBootstrapToken = '';
  function get(k) { try { return localStorage.getItem(k) || ''; } catch (e) { return ''; } }
  function set(k, v) {
    try {
      if (v === null || v === undefined || v === '') localStorage.removeItem(k);
      else localStorage.setItem(k, String(v));
    } catch (e) {}
  }
  function clearToken() {
    webBootstrapCache = null;
    webBootstrapToken = '';
    set(KEY.token, '');
    set(KEY.cursor, '');
  }
  function normalizeBase(value) {
    var v = String(value || '').trim();
    if (!v) {
      v = get(KEY.base);
      if (!v && /^https?:$/.test(location.protocol)) v = location.origin;
    }
    if (!v) return '';
    if (!/^https?:\/\//i.test(v)) v = 'https://' + v;
    return v.replace(/\/+$/, '');
  }
  function apiBase() { return normalizeBase(''); }
  function adminBase() {
    return normalizeBase('');
  }
  function setBase(value) { var v = normalizeBase(value); set(KEY.base, v); return v; }
  function installationId() {
    var id = get(KEY.installation);
    if (id) return id;
    var rand = '';
    try { rand = (crypto && crypto.randomUUID) ? crypto.randomUUID() : ''; } catch (e) {}
    if (!rand) rand = Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
    id = 'kissne-web-' + rand;
    set(KEY.installation, id);
    return id;
  }
  function deviceToken() { return get(KEY.token); }
  function cursor() {
    var n = parseInt(get(KEY.cursor) || '0', 10);
    return isFinite(n) && n >= 0 ? n : 0;
  }
  function ApiError(status, payload, message) {
    this.name = 'KissneApiError';
    this.status = status || 0;
    this.payload = payload || null;
    this.message = message || (payload && payload.error) || ('HTTP ' + status);
  }
  ApiError.prototype = Object.create(Error.prototype);

  async function request(path, opts) {
    opts = opts || {};
    var base = normalizeBase(opts.base || '');
    if (!base) throw new ApiError(0, null,
      location.protocol === 'file:' ? 'api_base_required_for_file_protocol' : 'api_base_required');
    var headers = { Accept: 'application/json' };
    if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
    if (opts.auth !== false) {
      var token = deviceToken();
      if (!token) throw new ApiError(401, { error: 'missing_device_token' }, 'missing_device_token');
      headers.Authorization = 'Bearer ' + token;
    }
    var res;
    try {
      res = await fetch(base + path, {
        method: opts.method || 'GET',
        headers: headers,
        body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
        cache: 'no-store',
        credentials: 'omit'
      });
    } catch (err) {
      throw new ApiError(0, null, err && err.message ? err.message : 'network_error');
    }
    var raw = await res.text();
    var payload = {};
    if (raw) {
      try { payload = JSON.parse(raw); } catch (e) { payload = { raw: raw }; }
    }
    if (!res.ok) {
      if (res.status === 401 && opts.clearAuthOn401 !== false) clearToken();
      throw new ApiError(res.status, payload, payload && payload.error);
    }
    return payload;
  }

  async function pair(opts) {
    opts = opts || {};
    var base = setBase(opts.apiBase || '');
    var body = { installation_id: installationId(), pairing_code: String(opts.pairingCode || opts.pairing_code || '') };
    if (!body.pairing_code) throw new ApiError(401, { error: 'pairing_code_required' }, 'pairing_code_required');
    var out = await request('/mobile/pair', { method: 'POST', body: body, auth: false, base: base });
    if (out.device_token) {
      webBootstrapCache = null;
      webBootstrapToken = '';
      set(KEY.token, out.device_token);
      set(KEY.cursor, '0');
    }
    return out;
  }
  async function ensureToken(force) {
    if (deviceToken() && !force) return { ok: true, existing: true, installation_id: installationId() };
    if (deviceToken() && force) return { ok: true, existing: true, installation_id: installationId() };
    throw new ApiError(401, { error: 'pairing_required' }, 'pairing_required');
  }
  function sessions() {
    return request('/admin/sessions', {
      method: 'GET',
      base: adminBase()
    });
  }
  function deleteSession(sessionId) {
    var id = String(sessionId || '').trim();
    if (!id) throw new ApiError(400, { error: 'session_id_required' }, 'session_id_required');
    return request('/admin/sessions', { method: 'DELETE', body: { session_id: id }, base: adminBase() });
  }
  function memories() {
    return request('/admin/memory', { method: 'GET', base: adminBase() });
  }
  function deleteMemory(memoryId) {
    var id = String(memoryId || '').trim();
    if (!id) throw new ApiError(400, { error: 'memory_id_required' }, 'memory_id_required');
    return request('/admin/memory/' + encodeURIComponent(id), {
      method: 'DELETE',
      base: adminBase()
    });
  }
  async function selectSession(sessionKey, sessionId) {
    var key = String(sessionKey || '').trim();
    var id = String(sessionId || '').trim();
    if (!key && !id) throw new ApiError(400, { error: 'session_identity_required' }, 'session_identity_required');
    var body = {};
    if (key) body.session_key = key;
    if (id) body.session_id = id;
    var out = await request('/admin/sessions', { method: 'POST', body: body, base: adminBase() });
    webBootstrapCache = null;
    webBootstrapToken = '';
    return out;
  }
  function hasBootstrapCache() {
    return !!webBootstrapCache && !!deviceToken() && webBootstrapToken === deviceToken();
  }
  async function bootstrap(force) {
    if (!force && hasBootstrapCache()) {
      var cached = Object.assign({}, webBootstrapCache);
      cached.cached = true;
      return cached;
    }
    var out = await request('/mobile/bootstrap', { method: 'POST', body: { cursor: cursor() } });
    if (out && out.bound) {
      webBootstrapCache = out;
      webBootstrapToken = deviceToken();
    } else {
      webBootstrapCache = null;
      webBootstrapToken = '';
    }
    return out;
  }
  function makeMessageId() {
    var r = '';
    try { r = (crypto && crypto.randomUUID) ? crypto.randomUUID() : ''; } catch (e) {}
    if (!r) r = Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
    return 'web-' + r;
  }
  function sendText(text, messageId) {
    var body = { text: String(text || ''), message_id: messageId || makeMessageId() };
    return request('/mobile/messages', { method: 'POST', body: body });
  }

  function pickAttachment() {
    return Promise.reject(new ApiError(0, { error: 'native_attachment_picker_required' }, 'native_attachment_picker_required'));
  }
  function poll() { return request('/mobile/messages?cursor=' + encodeURIComponent(cursor()), { method: 'GET' }); }
  async function ack(nextCursor) {
    var n = Number(nextCursor);
    if (!isFinite(n) || n < 0) return { ok: false };
    var out = await request('/mobile/messages', { method: 'POST', body: { ack: { cursor: n } } });
    set(KEY.cursor, String(n));
    return out;
  }
  function cancel(turnId) {
    return request('/mobile/cancel', { method: 'POST', body: { turn_id: String(turnId || '') } });
  }
  function modelOptions() {
    return request('/mobile/model-options', { method: 'GET', clearAuthOn401: false });
  }
  function setModel(model, effort, provider) {
    return request('/mobile/set-model', {
      method: 'POST',
      clearAuthOn401: false,
      body: {
        model: String(model || ''),
        effort: String(effort || ''),
        provider: String(provider || '')
      }
    });
  }
  function respondApproval(approvalId, decision, scope) {
    return request('/mobile/approval', {
      method: 'POST',
      body: {
        approval_id: String(approvalId || ''),
        decision: String(decision || ''),
        scope: String(scope || 'once')
      }
    });
  }
  function adminStatus() {
    return request('/admin/status', { method: 'GET', base: adminBase(), clearAuthOn401: false });
  }

  window.KissneTransport = {
    ApiError: ApiError,
    base: apiBase,
    setBase: setBase,
    installationId: installationId,
    token: deviceToken,
    hasToken: function () { return !!deviceToken(); },
    hasBootstrapCache: hasBootstrapCache,
    isConnected: function () { return hasBootstrapCache(); },
    clearToken: clearToken,
    cursor: cursor,
    pair: pair,
    ensureToken: ensureToken,
    sessions: sessions,
    deleteSession: deleteSession,
    selectSession: selectSession,
    bootstrap: bootstrap,
    sendText: sendText,
    pickAttachment: pickAttachment,
    poll: poll,
    ack: ack,
    cancel: cancel,
    modelOptions: modelOptions,
    setModel: setModel,
    respondApproval: respondApproval,
    adminStatus: adminStatus
  };
})();
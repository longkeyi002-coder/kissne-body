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
    function nativeCall(action, payload) {
      return new Promise(function (resolve, reject) {
        var id = 'n' + (++nativeSeq);
        nativePending[id] = { resolve: resolve, reject: reject };
        try {
          Native.request(id, action, JSON.stringify(payload || {}));
        } catch (err) {
          delete nativePending[id];
          reject(new NativeApiError(0, null, err && err.message ? err.message : 'native_bridge_error'));
        }
      });
    }
    window.KissneNativeBridge = {
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
        return nativeCall('pair', { api_base: base });
      },
      ensureToken: function (force) {
        return nativeCall('ensureToken', { force: !!force });
      },
      bootstrap: function () { return nativeCall('bootstrap', { cursor: Number(Native.getCursor()) || 0 }); },
      sendText: function (text, messageId) {
        return nativeCall('sendText', {
          text: String(text || ''),
          message_id: messageId || nativeMessageId()
        });
      },
      poll: function () { return nativeCall('poll', { cursor: Number(Native.getCursor()) || 0 }); },
      ack: function (nextCursor) { return nativeCall('ack', { cursor: Number(nextCursor) || 0 }); },
      cancel: function (turnId) { return nativeCall('cancel', { turn_id: String(turnId || '') }); },
      modelOptions: function () { return nativeCall('modelOptions', {}); },
      setModel: function (model, effort) {
        return nativeCall('setModel', {
          model: String(model || ''),
          effort: String(effort || '')
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
      adminMerge: function () { return nativeCall('adminMerge', {}); },
      adminRollback: function () { return nativeCall('adminRollback', {}); },
      adminDeployLog: function (lines) {
        return nativeCall('adminDeployLog', { lines: Number(lines) || 100 });
      },
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
  function get(k) { try { return localStorage.getItem(k) || ''; } catch (e) { return ''; } }
  function set(k, v) {
    try {
      if (v === null || v === undefined || v === '') localStorage.removeItem(k);
      else localStorage.setItem(k, String(v));
    } catch (e) {}
  }
  function clearToken() { set(KEY.token, ''); set(KEY.cursor, ''); }
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
    var base = normalizeBase('');
    return /\/mobile$/i.test(base) ? base.replace(/\/mobile$/i, '') : base;
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
    var body = { installation_id: installationId() };
    var out = await request('/mobile/pair', { method: 'POST', body: body, auth: false, base: base });
    if (out.device_token) { set(KEY.token, out.device_token); set(KEY.cursor, '0'); }
    return out;
  }
  async function ensureToken(force) {
    if (!force && deviceToken()) return { ok: true, existing: true, installation_id: installationId() };
    return pair({});
  }
  function bootstrap() { return request('/mobile/bootstrap', { method: 'POST', body: { cursor: cursor() } }); }
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
  function setModel(model, effort) {
    return request('/mobile/set-model', {
      method: 'POST',
      clearAuthOn401: false,
      body: {
        model: String(model || ''),
        effort: String(effort || '')
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
  function adminMerge() {
    return request('/admin/merge', { method: 'POST', base: adminBase(), clearAuthOn401: false });
  }
  function adminRollback() {
    return request('/admin/rollback', { method: 'POST', base: adminBase(), clearAuthOn401: false });
  }
  function adminDeployLog(lines) {
    var n = Math.max(1, Math.min(500, Number(lines) || 100));
    return request('/admin/deploy-log?lines=' + encodeURIComponent(n), {
      method: 'GET',
      base: adminBase(),
      clearAuthOn401: false
    });
  }

  window.KissneTransport = {
    ApiError: ApiError,
    base: apiBase,
    setBase: setBase,
    installationId: installationId,
    token: deviceToken,
    hasToken: function () { return !!deviceToken(); },
    isConnected: function () { return !!deviceToken(); },
    clearToken: clearToken,
    cursor: cursor,
    pair: pair,
    ensureToken: ensureToken,
    bootstrap: bootstrap,
    sendText: sendText,
    poll: poll,
    ack: ack,
    cancel: cancel,
    modelOptions: modelOptions,
    setModel: setModel,
    respondApproval: respondApproval,
    adminStatus: adminStatus,
    adminMerge: adminMerge,
    adminRollback: adminRollback,
    adminDeployLog: adminDeployLog
  };
})();
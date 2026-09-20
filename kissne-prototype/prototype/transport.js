/* Kissne prototype -> real Kissne Mobile transport. UI-free. */
(function () {
  'use strict';
  var KEY = {
    base: 'kissne.web.api_base',
    installation: 'kissne.web.installation_id',
    token: 'kissne.web.device_token',
    session: 'kissne.web.session_key',
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
  function sessionKey() { return get(KEY.session); }
  function setSessionKey(value) { set(KEY.session, String(value || '').trim()); }
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
      if (res.status === 401) clearToken();
      throw new ApiError(res.status, payload, payload && payload.error);
    }
    return payload;
  }

  async function pair(opts) {
    opts = opts || {};
    var code = String(opts.pairingCode || '').trim();
    var sk = String(opts.sessionKey || '').trim();
    var base = setBase(opts.apiBase || '');
    if (!code) throw new ApiError(400, { error: 'pairing_code_required' }, 'pairing_code_required');
    if (sk) setSessionKey(sk);
    var body = { pairing_code: code, installation_id: installationId() };
    if (sk) body.session_key = sk;
    var out = await request('/mobile/pair', { method: 'POST', body: body, auth: false, base: base });
    if (out.device_token) { set(KEY.token, out.device_token); set(KEY.cursor, '0'); }
    return out;
  }
  function bootstrap() { return request('/mobile/bootstrap', { method: 'POST', body: { cursor: cursor() } }); }
  function makeMessageId() {
    var r = '';
    try { r = (crypto && crypto.randomUUID) ? crypto.randomUUID() : ''; } catch (e) {}
    if (!r) r = Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
    return 'web-' + r;
  }
  function sendMessage(opts, messageId) {
    opts = opts || {};
    var body = {
      text: String(opts.text || ''),
      message_id: messageId || opts.messageId || makeMessageId()
    };
    var attachments = Array.isArray(opts.attachments) ? opts.attachments : [];
    if (attachments.length) body.attachments = attachments;
    var sk = sessionKey();
    if (sk) body.session_key = sk;
    return request('/mobile/messages', { method: 'POST', body: body });
  }
  function sendText(text, messageId) {
    return sendMessage({ text: text }, messageId);
  }
  function blobToBase64(blob) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () {
        var raw = String(reader.result || '');
        resolve(raw.indexOf(',') >= 0 ? raw.slice(raw.indexOf(',') + 1) : raw);
      };
      reader.onerror = function () { reject(reader.error || new Error('attachment_read_failed')); };
      reader.readAsDataURL(blob);
    });
  }
  async function attachmentFromUrl(url, type, label) {
    var res = await fetch(url, { cache: 'no-store', credentials: 'omit' });
    if (!res.ok) throw new ApiError(res.status, null, 'attachment_load_failed');
    var blob = await res.blob();
    return {
      type: type || 'image',
      mime_type: blob.type || 'image/png',
      data: await blobToBase64(blob),
      label: label || undefined
    };
  }
  async function sendAsset(url, type, label, messageId) {
    var attachment = await attachmentFromUrl(url, type, label);
    return sendMessage({ attachments: [attachment] }, messageId);
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

  window.KissneTransport = {
    ApiError: ApiError,
    base: apiBase,
    setBase: setBase,
    installationId: installationId,
    token: deviceToken,
    hasToken: function () { return !!deviceToken(); },
    clearToken: clearToken,
    sessionKey: sessionKey,
    setSessionKey: setSessionKey,
    cursor: cursor,
    pair: pair,
    bootstrap: bootstrap,
    sendMessage: sendMessage,
    sendText: sendText,
    blobToBase64: blobToBase64,
    attachmentFromUrl: attachmentFromUrl,
    sendAsset: sendAsset,
    poll: poll,
    ack: ack,
    cancel: cancel
  };
})();
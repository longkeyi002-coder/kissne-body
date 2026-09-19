/* =====================================================================
   Kissne 手机端 · backend.js
   后端 API 客户端：配对、引导、发消息、轮询接收
   ===================================================================== */
window.KSN = window.KSN || {};
(function () {
  'use strict';

  /* ---------- 状态 ---------- */
  var _server = '';        // host:port
  var _token = '';         // device token（配对成功后获得）
  var _connected = false;
  var _cursor = 0;         // 消息游标
  var _pollTimer = null;
  var _onStatusChange = null;
  var _onMessage = null;   // 收到新消息时的回调

  /* ---------- 工具 ---------- */
  function url(path) {
    return 'http://' + _server + path;
  }

  function headers() {
    var h = { 'Content-Type': 'application/json' };
    if (_token) h['Authorization'] = 'Bearer ' + _token;
    return h;
  }

  /* ---------- 配对 ---------- */
  function pair(pairingCode, serverAddress, callback) {
    _server = serverAddress;
    _connected = false;

    fetch(url('/pair'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: pairingCode })
    })
    .then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    })
    .then(function (data) {
      if (data.token) {
        _token = data.token;
        _connected = true;
        _cursor = 0;
        _notify();
        callback(null, data);
      } else {
        callback(new Error(data.error || '配对失败'));
      }
    })
    .catch(function (err) {
      callback(err);
    });
  }

  /* ---------- 引导（获取对话信息 + 历史） ---------- */
  function bootstrap(callback) {
    if (!_connected || !_token) {
      callback(new Error('未连接'));
      return;
    }

    fetch(url('/bootstrap'), {
      method: 'POST',
      headers: headers(),
      body: JSON.stringify({})
    })
    .then(function (res) { return res.json(); })
    .then(function (data) {
      callback(null, data);
    })
    .catch(callback);
  }

  /* ---------- 发消息 ---------- */
  function sendMessage(text, callback) {
    if (!_connected || !_token) {
      callback(new Error('未连接'));
      return;
    }

    var messageId = 'msg_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);

    fetch(url('/messages'), {
      method: 'POST',
      headers: headers(),
      body: JSON.stringify({ text: text, message_id: messageId })
    })
    .then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    })
    .then(function (data) {
      callback(null, data);
    })
    .catch(function (err) {
      callback(err);
    });
  }

  /* ---------- 轮询接收 ---------- */
  function startPolling(onEvent) {
    if (_pollTimer) return;

    function poll() {
      if (!_connected || !_token) return;

      fetch(url('/messages') + '?cursor=' + _cursor, {
        method: 'GET',
        headers: headers()
      })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (data.events && data.events.length) {
          data.events.forEach(function (evt) {
            if (evt.cursor) _cursor = evt.cursor;
            if (onEvent) onEvent(evt);
          });
        }
        if (data.cursor) _cursor = data.cursor;
      })
      .catch(function () {})
      .then(function () {
        _pollTimer = setTimeout(poll, 1000);
      });
    }

    poll();
  }

  function stopPolling() {
    clearTimeout(_pollTimer);
    _pollTimer = null;
  }

  /* ---------- 取消 ---------- */
  function cancelTurn(turnId, callback) {
    if (!_connected || !_token) {
      callback(new Error('未连接'));
      return;
    }

    fetch(url('/cancel'), {
      method: 'POST',
      headers: headers(),
      body: JSON.stringify({ turn_id: turnId })
    })
    .then(function (res) { return res.json(); })
    .then(function (data) { callback(null, data); })
    .catch(callback);
  }

  /* ---------- 断开 ---------- */
  function revoke(callback) {
    if (!_connected || !_token) {
      callback(null);
      return;
    }

    fetch(url('/revoke'), {
      method: 'POST',
      headers: headers(),
      body: JSON.stringify({})
    })
    .then(function () {
      _token = '';
      _connected = false;
      _cursor = 0;
      stopPolling();
      _notify();
      if (callback) callback(null);
    })
    .catch(function () {
      _token = '';
      _connected = false;
      _notify();
      if (callback) callback(null);
    });
  }

  /* ---------- 状态通知 ---------- */
  function _notify() {
    if (_onStatusChange) _onStatusChange(_connected);
  }

  function onStatusChange(fn) { _onStatusChange = fn; }
  function onMessage(fn) { _onMessage = fn; }
  function isConnected() { return _connected; }
  function getServer() { return _server; }

  /* ---------- 导出 ---------- */
  window.KSN.backend = {
    pair: pair,
    bootstrap: bootstrap,
    sendMessage: sendMessage,
    startPolling: startPolling,
    stopPolling: stopPolling,
    cancelTurn: cancelTurn,
    revoke: revoke,
    onStatusChange: onStatusChange,
    onMessage: onMessage,
    isConnected: isConnected,
    getServer: getServer
  };
})();

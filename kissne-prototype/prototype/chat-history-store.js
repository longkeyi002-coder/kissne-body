/* Searchable local chat replicas; this never writes SELF or long-term memories. */
(function (root) {
  'use strict';
  function create(factory) {
    var database;
    function db() {
      if (!database) database = new Promise(function (resolve, reject) {
        if (!factory) { reject(new Error('local_history_unavailable')); return; }
        var request = factory.open('kissne-chat-history', 1);
        request.onupgradeneeded = function () { var messages = request.result.createObjectStore('messages', { keyPath: 'key' }); messages.createIndex('terms', 'terms', { multiEntry: true }); };
        request.onsuccess = function () { resolve(request.result); }; request.onerror = function () { reject(request.error); };
      }).catch(function (error) { database = null; throw error; });
      return database;
    }
    function normalize(row, ns) {
      if (!row || !ns || !/^(user|assistant)$/.test(row.role || '')) return null;
      var presentation = String(row.presentation || (row.metadata && row.metadata.presentation) || '');
      if (presentation && !/^(final|answer|assistant_text)$/.test(presentation)) return null;
      if (row.tool_name || row.tool_call_id || row.tool_calls) return null;
      var text = String(row.text || '').trim();
      if (row.role === 'assistant' && root.KissneChatPresentation) text = root.KissneChatPresentation.channels(text).answer;
      if (!text || /^(?:↪ Redirected|Interrupting current task|I'll respond to your message shortly\.)/.test(text) || !row.message_ref) return null;
      var chars = Array.from(text.normalize('NFKC').toLowerCase()), terms = new Set();
      chars.forEach(function (char, i) { terms.add(ns + '\u0000' + char); if (i) terms.add(ns + '\u0000' + chars[i - 1] + char); });
      return { key: ns + '\u0000' + (row.turn_id ? 'turn:' + row.turn_id + ':' + row.role : row.message_ref), terms: Array.from(terms),
        row: { role: row.role, text: text, message_ref: row.message_ref, turn_id: row.turn_id || '', session_id: row.session_id || '', created_at: row.created_at || 0 } };
    }
    return {
      put: async function (ns, rows) {
        var records = (rows || []).map(function (row) { return normalize(row, ns); }).filter(Boolean); if (!records.length) return;
        var connection = await db();
        return new Promise(function (resolve, reject) { var tx = connection.transaction('messages', 'readwrite'); records.forEach(function (record) { tx.objectStore('messages').put(record); }); tx.oncomplete = resolve; tx.onerror = function () { reject(tx.error); }; });
      },
      search: async function (ns, query, limit) {
        var normalized = String(query || '').normalize('NFKC').toLowerCase().trim(); if (!ns || !normalized) return [];
        var connection = await db(), term = Array.from(normalized).slice(0, 2).join('');
        return new Promise(function (resolve, reject) {
          var results = [], request = connection.transaction('messages').objectStore('messages').index('terms').openCursor(ns + '\u0000' + term);
          request.onsuccess = function () { var cursor = request.result;
            if (!cursor) { results.sort(function (a, b) { return Number(b.created_at) - Number(a.created_at); }); resolve(results.slice(0, Number(limit) || 500)); return; }
            if (cursor.value.row.text.normalize('NFKC').toLowerCase().indexOf(normalized) >= 0) results.push(cursor.value.row); cursor.continue();
          }; request.onerror = function () { reject(request.error); };
        });
      },
      close: async function () { if (database) (await database).close(); database = null; }
    };
  }
  function attach(transport) {
    var store = create(root.indexedDB), session = '';
    async function namespace() {
      if (!transport.hasToken()) return '';
      if (transport.cacheIdentity) return transport.cacheIdentity();
      var bytes = new TextEncoder().encode(transport.base() + '|' + transport.installationId() + '|' + transport.token());
      var hash = await root.crypto.subtle.digest('SHA-256', bytes);
      return Array.from(new Uint8Array(hash)).map(function (byte) { return byte.toString(16).padStart(2, '0'); }).join('');
    }
    ['bootstrap', 'history', 'search', 'poll', 'sendText'].forEach(function (action) {
      var original = transport[action]; if (!original) return;
      transport[action] = async function () {
        var args = arguments, ns = await namespace().catch(function () { return ''; }), current = session;
        var payload = await original.apply(transport, args);
        if (action === 'bootstrap') session = String(payload && payload.conversation && payload.conversation.session_id || session);
        var rows = (payload && (payload.history || payload.messages || payload.results) || []).filter(function (row) { return row && row.role; }).map(function (row) { return Object.assign({}, row, { session_id: row.session_id || (action === 'bootstrap' ? session : current) }); });
        if (action === 'poll') rows = (payload.events || []).filter(function (event) { return event.type === 'completed' && !/^(hidden|internal_notification|commentary)$/.test(event.presentation || ''); }).map(function (event) { return { role: 'assistant', text: event.text || '', turn_id: event.turn_id, session_id: event.session_id || current, message_ref: event.message_ref || 'turn:' + event.turn_id + ':assistant', created_at: event.created_at || Date.now() / 1000 }; });
        if (action === 'sendText' && payload.turn_id) rows = [{ role: 'user', text: args[0], turn_id: payload.turn_id, message_ref: 'turn:' + payload.turn_id + ':user', session_id: current, created_at: Date.now() / 1000 }];
        await store.put(ns, rows).catch(function () {}); return payload;
      };
    });
    transport.searchLocal = async function (q, limit) { return { results: await store.search(await namespace(), q, limit) }; };
  }
  var api = { create: create, attach: attach };
  if (typeof module === 'object' && module.exports) module.exports = api; else root.KissneChatHistory = api;
})(typeof window !== 'undefined' ? window : globalThis);

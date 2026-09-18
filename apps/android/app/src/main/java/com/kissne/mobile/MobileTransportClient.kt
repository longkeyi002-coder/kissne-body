package com.kissne.mobile

import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL

class MobileTransportException(val status: Int, message: String) : Exception(message)

class MobileTransportClient(private val baseUrl: String, private val tokenProvider: () -> String?, private val connectTimeoutMs: Int = 10_000, private val readTimeoutMs: Int = 30_000) {
    private fun nullableString(json: JSONObject, key: String): String? = if (json.isNull(key)) null else json.optString(key).ifBlank { null }
    private fun request(method: String, path: String, body: JSONObject? = null): JSONObject {
        val connection = (URL(baseUrl.trimEnd('/') + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method; connectTimeout = connectTimeoutMs; readTimeout = readTimeoutMs
            setRequestProperty("Accept", "application/json")
            tokenProvider()?.takeIf { it.isNotBlank() }?.let { setRequestProperty("Authorization", "Bearer $it") }
            if (body != null) { doOutput = true; setRequestProperty("Content-Type", "application/json"); outputStream.use { it.write(body.toString().toByteArray()) } }
        }
        val status = connection.responseCode; val stream = if (status in 200..299) connection.inputStream else connection.errorStream
        val text = stream?.use { BufferedReader(InputStreamReader(it)).readText() } ?: ""; connection.disconnect()
        val json = if (text.isBlank()) JSONObject() else JSONObject(text)
        if (status !in 200..299) throw MobileTransportException(status, json.optString("error", "HTTP $status"))
        return json
    }
    fun bootstrap(cursor: Long): Bootstrap {
        val json = request("POST", "/bootstrap", JSONObject().put("cursor", cursor))
        val conversation = json.optJSONObject("conversation"); val history = mutableListOf<HistoryMessage>()
        val array = json.optJSONArray("history") ?: JSONArray()
        for (i in 0 until array.length()) { val item = array.optJSONObject(i) ?: continue; history += HistoryMessage(item.optString("role", "assistant"), nullableString(item, "text") ?: "", nullableString(item, "message_id")) }
        val covered = mutableListOf<Long>(); val coveredJson = json.optJSONArray("covered_event_seqs") ?: JSONArray()
        for (i in 0 until coveredJson.length()) covered += coveredJson.optLong(i)
        return Bootstrap(json.optBoolean("bound", false), nullableString(conversation ?: JSONObject(), "session_id"), nullableString(conversation ?: JSONObject(), "session_key"), history, nullableString(json, "pending_turn_id"), covered)
    }
    fun pair(pairingCode: String, installationId: String, sessionKey: String): String = request("POST", "/pair", JSONObject().put("pairing_code", pairingCode).put("installation_id", installationId).put("session_key", sessionKey)).getString("device_token")
    fun send(messageId: String, text: String): SendReceipt { val json = request("POST", "/messages", JSONObject().put("message_id", messageId).put("text", text)); return SendReceipt(messageId, json.optString("turn_id"), json.optBoolean("duplicate", false)) }
    fun poll(cursor: Long): List<MobileEvent> {
        val array = request("GET", "/messages?cursor=$cursor").optJSONArray("events") ?: JSONArray(); val events = mutableListOf<MobileEvent>()
        for (i in 0 until array.length()) { val item = array.optJSONObject(i) ?: continue; events += MobileEvent(item.optLong("seq"), MobileEventType.fromWire(item.optString("type")), nullableString(item, "turn_id"), nullableString(item, "message_id"), nullableString(item, "reply_to"), nullableString(item, "text")) }
        return events
    }
    fun ack(cursor: Long) { request("POST", "/messages", JSONObject().put("ack", JSONObject().put("cursor", cursor))) }
    fun cancel(turnId: String): String = request("POST", "/cancel", JSONObject().put("turn_id", turnId)).optString("state", "cancelled")
}

package com.kissne.mobile

import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

class MobileTransportException(val status: Int, message: String) : Exception(message)

class MobileTransportClient(
    private val baseUrl: String,
    private val tokenProvider: () -> String?,
    private val connectTimeoutMs: Int = 10_000,
    private val readTimeoutMs: Int = 30_000
) {
    private fun request(method: String, path: String, body: JSONObject? = null): JSONObject {
        val connection = (URL(baseUrl.trimEnd('/') + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = connectTimeoutMs
            readTimeout = readTimeoutMs
            setRequestProperty("Accept", "application/json")
            tokenProvider()?.takeIf { it.isNotBlank() }?.let {
                setRequestProperty("Authorization", "Bearer " + it)
            }
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json")
                outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
        }
        val status = connection.responseCode
        val stream = if (status in 200..299) connection.inputStream else connection.errorStream
        val text = stream?.use { BufferedReader(InputStreamReader(it)).readText() } ?: ""
        connection.disconnect()
        val json = if (text.isBlank()) JSONObject() else JSONObject(text)
        if (status !in 200..299) {
            throw MobileTransportException(status, json.optString("error", "HTTP " + status))
        }
        return json
    }

    fun bootstrap(): Bootstrap {
        val json = request("POST", "/bootstrap")
        val conversation = json.optJSONObject("conversation")
        val history = mutableListOf<HistoryMessage>()
        val array = json.optJSONArray("history") ?: JSONArray()
        for (i in 0 until array.length()) {
            val item = array.optJSONObject(i) ?: continue
            history += HistoryMessage(item.optString("role", "assistant"), item.optString("text"),
                item.optString("message_id").ifBlank { null })
        }
        return Bootstrap(
            bound = json.optBoolean("bound", false),
            conversationId = conversation?.optString("session_id")?.ifBlank { null },
            conversationTitle = conversation?.optString("session_key")?.ifBlank { null },
            history = history,
            pendingTurnId = json.optString("pending_turn_id").ifBlank { null }
        )
    }

    fun pair(pairingCode: String, installationId: String): String =
        request("POST", "/pair", JSONObject()
            .put("pairing_code", pairingCode)
            .put("installation_id", installationId))
            .getString("device_token")

    fun send(messageId: String, text: String): SendReceipt {
        val json = request("POST", "/messages", JSONObject()
            .put("message_id", messageId).put("text", text))
        return SendReceipt(messageId, json.optString("turn_id"), json.optBoolean("duplicate", false))
    }

    fun poll(cursor: Long): List<MobileEvent> {
        val json = request("GET", "/messages?cursor=" + URLEncoder.encode(cursor.toString(), "UTF-8"))
        val array = json.optJSONArray("events") ?: JSONArray()
        val events = mutableListOf<MobileEvent>()
        for (i in 0 until array.length()) {
            val item = array.optJSONObject(i) ?: continue
            events += MobileEvent(item.optLong("seq"), MobileEventType.fromWire(item.optString("type")),
                item.optString("turn_id").ifBlank { null },
                item.optString("message_id").ifBlank { null },
                item.optString("reply_to").ifBlank { null },
                item.optString("text").ifBlank { null })
        }
        return events
    }

    fun ack(cursor: Long) {
        request("POST", "/messages", JSONObject().put("ack", JSONObject().put("cursor", cursor)))
    }

    fun cancel(turnId: String): String =
        request("POST", "/cancel", JSONObject().put("turn_id", turnId)).optString("state", "cancelled")
}

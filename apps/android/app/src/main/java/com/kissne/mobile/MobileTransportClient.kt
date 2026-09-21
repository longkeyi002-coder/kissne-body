package com.kissne.mobile

import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL

class MobileTransportException(val status: Int, message: String) : Exception(message)

class MobileTransportClient(
    private val baseUrl: String,
    private val tokenProvider: () -> String?,
    private val connectTimeoutMs: Int = 10_000,
    private val readTimeoutMs: Int = 30_000,
) {
    private fun nullableString(json: JSONObject, key: String): String? =
        if (json.isNull(key)) null else json.optString(key).ifBlank { null }

    private fun adminBaseUrl(): String {
        val base = baseUrl.trimEnd('/')
        return if (base.endsWith("/mobile")) base.removeSuffix("/mobile") else base
    }

    private fun request(
        method: String,
        path: String,
        body: JSONObject? = null,
        auth: Boolean = true,
        adminRoot: Boolean = false,
    ): JSONObject {
        val requestBase = if (adminRoot) adminBaseUrl() else baseUrl.trimEnd('/')
        val connection = (URL(requestBase + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = connectTimeoutMs
            readTimeout = readTimeoutMs
            setRequestProperty("Accept", "application/json")
            if (auth) tokenProvider()?.takeIf { it.isNotBlank() }?.let {
                setRequestProperty("Authorization", "Bearer $it")
            }
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json")
                outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
        }

        return try {
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.use {
                BufferedReader(InputStreamReader(it, Charsets.UTF_8)).readText()
            }.orEmpty()
            val json = if (text.isBlank()) JSONObject() else JSONObject(text)
            if (status !in 200..299) {
                throw MobileTransportException(status, json.optString("error", "HTTP $status"))
            }
            json
        } finally {
            connection.disconnect()
        }
    }

    fun sessionsPayload(): JSONObject =
        request("GET", "/admin/sessions", adminRoot = true)

    fun bootstrapPayload(cursor: Long): JSONObject =
        request("POST", "/bootstrap", JSONObject().put("cursor", cursor))

    fun bootstrap(cursor: Long): Bootstrap {
        val json = bootstrapPayload(cursor)
        val conversation = json.optJSONObject("conversation")
        val history = mutableListOf<HistoryMessage>()
        val array = json.optJSONArray("history") ?: JSONArray()

        for (i in 0 until array.length()) {
            val item = array.optJSONObject(i) ?: continue
            history += HistoryMessage(
                role = item.optString("role", "assistant"),
                text = nullableString(item, "text").orEmpty(),
                messageId = nullableString(item, "message_id"),
            )
        }

        val covered = mutableListOf<Long>()
        val coveredJson = json.optJSONArray("covered_event_seqs") ?: JSONArray()
        for (i in 0 until coveredJson.length()) {
            covered += coveredJson.optLong(i)
        }

        return Bootstrap(
            bound = json.optBoolean("bound", false),
            conversationId = nullableString(conversation ?: JSONObject(), "session_id"),
            conversationTitle = nullableString(conversation ?: JSONObject(), "session_key"),
            history = history,
            pendingTurnId = nullableString(json, "pending_turn_id"),
            coveredEventSeqs = covered,
        )
    }

    fun pairPayload(
        installationId: String,
        sessionKey: String? = null,
        rotateToken: Boolean = false,
    ): JSONObject {
        val body = JSONObject().put("installation_id", installationId)
        sessionKey?.trim()?.takeIf { it.isNotBlank() }?.let { body.put("session_key", it) }
        if (rotateToken) body.put("rotate_token", true)
        return request("POST", "/pair", body, auth = false)
    }

    fun pair(installationId: String): String =
        pairPayload(installationId, rotateToken = true).getString("device_token")

    fun sendPayload(messageId: String, text: String): JSONObject =
        request(
            "POST",
            "/messages",
            JSONObject().put("message_id", messageId).put("text", text),
        )

    fun send(messageId: String, text: String): SendReceipt {
        val json = sendPayload(messageId, text)
        return SendReceipt(
            messageId = messageId,
            turnId = json.optString("turn_id"),
            duplicate = json.optBoolean("duplicate", false),
        )
    }

    fun pollPayload(cursor: Long): JSONObject = request("GET", "/messages?cursor=$cursor")

    fun poll(cursor: Long): List<MobileEvent> {
        val array = pollPayload(cursor).optJSONArray("events") ?: JSONArray()
        val events = mutableListOf<MobileEvent>()

        for (i in 0 until array.length()) {
            val item = array.optJSONObject(i) ?: continue
            events += MobileEvent(
                seq = item.optLong("seq"),
                type = MobileEventType.fromWire(item.optString("type")),
                turnId = nullableString(item, "turn_id"),
                messageId = nullableString(item, "message_id"),
                replyTo = nullableString(item, "reply_to"),
                text = nullableString(item, "text"),
            )
        }
        return events
    }

    fun ack(cursor: Long) {
        request("POST", "/messages", JSONObject().put("ack", JSONObject().put("cursor", cursor)))
    }

    fun cancelPayload(turnId: String): JSONObject =
        request("POST", "/cancel", JSONObject().put("turn_id", turnId))

    fun approvalPayload(approvalId: String, decision: String, scope: String): JSONObject =
        request(
            "POST",
            "/approval",
            JSONObject()
                .put("approval_id", approvalId)
                .put("decision", decision)
                .put("scope", scope),
        )

    fun modelOptionsPayload(): JSONObject =
        request("GET", "/model-options")

    fun setModelPayload(model: String? = null, effort: String? = null): JSONObject {
        val body = JSONObject()
        model?.trim()?.takeIf { it.isNotBlank() }?.let { body.put("model", it) }
        effort?.trim()?.takeIf { it.isNotBlank() }?.let { body.put("effort", it) }
        return request("POST", "/set-model", body)
    }

    fun revoke(): JSONObject =
        request("POST", "/revoke")

    fun adminStatusPayload(): JSONObject =
        request("GET", "/admin/status", adminRoot = true)

    fun adminMergePayload(): JSONObject =
        request("POST", "/admin/merge", adminRoot = true)

    fun adminRollbackPayload(): JSONObject =
        request("POST", "/admin/rollback", adminRoot = true)

    fun adminDeployLogPayload(lines: Int = 100): JSONObject {
        val safeLines = lines.coerceIn(1, 500)
        return request("GET", "/admin/deploy-log?lines=$safeLines", adminRoot = true)
    }

    fun cancel(turnId: String): String = cancelPayload(turnId).optString("state", "cancelled")
}

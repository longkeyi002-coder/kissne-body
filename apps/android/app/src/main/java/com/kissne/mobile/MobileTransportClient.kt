package com.kissne.mobile

import org.json.JSONObject
import java.io.BufferedReader
import java.io.DataOutputStream
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID

class MobileTransportException(val status: Int, message: String) : Exception(message)

class MobileTransportClient(
    private val baseUrl: String,
    private val tokenProvider: () -> String?,
    private val connectTimeoutMs: Int = 10_000,
    private val readTimeoutMs: Int = 30_000,
) {
    private fun requestUrl(path: String): URL =
        URL(resolveMobileRequestUrl(baseUrl, path))

    private fun request(
        method: String,
        path: String,
        body: JSONObject? = null,
        auth: Boolean = true,
    ): JSONObject {
        val connection = (requestUrl(path).openConnection() as HttpURLConnection).apply {
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
        request("GET", "/admin/sessions")

    fun deleteSessionPayload(sessionId: String): JSONObject =
        request("DELETE", "/admin/sessions", JSONObject().put("session_id", sessionId))

    fun selectSessionPayload(sessionKey: String?, sessionId: String?): JSONObject {
        val body = JSONObject()
        sessionKey?.trim()?.takeIf { it.isNotBlank() }?.let { body.put("session_key", it) }
        sessionId?.trim()?.takeIf { it.isNotBlank() }?.let { body.put("session_id", it) }
        return request("POST", "/admin/sessions", body)
    }

    fun historyPayload(limit: Int = 50, before: String? = null): JSONObject {
        val query = StringBuilder("/history?limit=").append(limit.coerceIn(1, 100))
        before?.takeIf { it.isNotBlank() }?.let {
            query.append("&before=").append(java.net.URLEncoder.encode(it, "UTF-8"))
        }
        return request("GET", query.toString())
    }

    fun searchPayload(queryText: String, limit: Int = 20): JSONObject =
        request("GET", "/search?q=" + java.net.URLEncoder.encode(queryText, "UTF-8") +
            "&limit=" + limit.coerceIn(1, 50))


    fun bootstrapPayload(cursor: Long): JSONObject =
        request("POST", "/bootstrap", JSONObject().put("cursor", cursor))


    fun pairPayload(
        installationId: String,
        sessionKey: String? = null,
        sessionId: String? = null,
    ): JSONObject {
        val body = JSONObject().put("installation_id", installationId)
        sessionKey?.trim()?.takeIf { it.isNotBlank() }?.let { body.put("session_key", it) }
        sessionId?.trim()?.takeIf { it.isNotBlank() }?.let { body.put("session_id", it) }
        return request("POST", "/pair", body, auth = false)
    }


    fun sendPayload(messageId: String, text: String, replyTo: String? = null): JSONObject {
        val body = JSONObject().put("message_id", messageId).put("text", text)
        replyTo?.trim()?.takeIf { it.isNotBlank() }?.let { body.put("reply_to", it) }
        return request("POST", "/messages", body)
    }


    fun pollPayload(cursor: Long): JSONObject = request("GET", "/messages?cursor=$cursor")


    fun ack(cursor: Long) {
        request("POST", "/messages", JSONObject().put("ack", JSONObject().put("cursor", cursor)))
    }

    fun sendAttachmentPayload(
        messageId: String,
        kind: String,
        fileName: String,
        mimeType: String,
        bytes: ByteArray,
    ): JSONObject {
        val boundary = "Kissne-" + UUID.randomUUID().toString()
        val connection = (requestUrl("/messages").openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = connectTimeoutMs
            readTimeout = maxOf(readTimeoutMs, 120_000)
            doOutput = true
            setChunkedStreamingMode(64 * 1024)
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")
            tokenProvider()?.takeIf { it.isNotBlank() }?.let {
                setRequestProperty("Authorization", "Bearer $it")
            }
        }
        val crlf = "\r\n"
        fun DataOutputStream.field(name: String, value: String) {
            writeBytes("--$boundary$crlf")
            writeBytes("Content-Disposition: form-data; name=\"$name\"$crlf")
            writeBytes("Content-Type: text/plain; charset=UTF-8$crlf$crlf")
            write(value.toByteArray(Charsets.UTF_8))
            writeBytes(crlf)
        }
        return try {
            DataOutputStream(connection.outputStream).use { out ->
                out.field("message_id", messageId)
                out.field("kind", normalizeAttachmentKind(kind))
                out.field("file_name", fileName)
                out.field("mime_type", mimeType)
                out.writeBytes("--$boundary$crlf")
                out.writeBytes(
                    "Content-Disposition: form-data; name=\"file\"; filename=\"upload.bin\"$crlf"
                )
                out.writeBytes(
                    "Content-Type: " + mimeType.ifBlank { "application/octet-stream" } + crlf + crlf
                )
                out.write(bytes)
                out.writeBytes(crlf)
                out.writeBytes("--$boundary--$crlf")
                out.flush()
            }
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

    fun setModelPayload(
        model: String? = null,
        effort: String? = null,
        provider: String? = null,
    ): JSONObject {
        val body = JSONObject()
        model?.trim()?.takeIf { it.isNotBlank() }?.let { body.put("model", it) }
        effort?.trim()?.takeIf { it.isNotBlank() }?.let { body.put("effort", it) }
        provider?.trim()?.takeIf { it.isNotBlank() }?.let { body.put("provider", it) }
        return request("POST", "/set-model", body)
    }

    fun revoke(): JSONObject =
        request("POST", "/revoke")

    fun adminStatusPayload(): JSONObject =
        request("GET", "/admin/status")


}


internal fun resolveMobileRequestUrl(baseUrl: String, path: String): String =
    baseUrl.trimEnd('/') + "/" + path.trimStart('/')


internal fun normalizeAttachmentKind(kind: String): String = when (kind.trim().lowercase()) {
    "photo" -> "photo"
    "sticker" -> "sticker"
    else -> "file"
}

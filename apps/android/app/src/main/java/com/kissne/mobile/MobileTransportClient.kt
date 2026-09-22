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

    fun memoriesPayload(): JSONObject =
        request("GET", "/admin/memory")

    fun deleteMemoryPayload(memoryId: String): JSONObject =
        request("DELETE", "/admin/memory/$memoryId")

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


    fun sendPayload(messageId: String, text: String): JSONObject =
        request(
            "POST",
            "/messages",
            JSONObject().put("message_id", messageId).put("text", text),
        )


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
                out.field("kind", if (kind == "photo") "photo" else "file")
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

    fun setModelPayload(model: String? = null, effort: String? = null): JSONObject {
        val body = JSONObject()
        model?.trim()?.takeIf { it.isNotBlank() }?.let { body.put("model", it) }
        effort?.trim()?.takeIf { it.isNotBlank() }?.let { body.put("effort", it) }
        return request("POST", "/set-model", body)
    }

    fun revoke(): JSONObject =
        request("POST", "/revoke")

    fun adminStatusPayload(): JSONObject =
        request("GET", "/admin/status")

    fun adminMergePayload(): JSONObject =
        request("POST", "/admin/merge")

    fun adminRollbackPayload(): JSONObject =
        request("POST", "/admin/rollback")

    fun adminDeployLogPayload(lines: Int = 100): JSONObject {
        val safeLines = lines.coerceIn(1, 500)
        return request("GET", "/admin/deploy-log?lines=$safeLines")
    }

}


internal fun resolveMobileRequestUrl(baseUrl: String, path: String): String =
    baseUrl.trimEnd('/') + "/" + path.trimStart('/')

package com.kissne.mobile

import android.view.HapticFeedbackConstants
import android.webkit.JavascriptInterface
import android.webkit.WebView
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.Executors

class PrototypeBridge(
    private val webView: WebView,
    private val store: MobileSessionStore,
    private val checkUpdates: () -> Unit = {},
    private val startVoiceInput: (String) -> Unit = {},
    private val startAttachmentPicker: (String, String) -> Unit = { _, _ -> },
) {
    /*
     * Keep chat transport isolated from slower control-plane calls.
     * Provider/model discovery can legitimately take seconds; when every bridge
     * request shared one single-thread executor it blocked bootstrap, polling
     * and sendText behind modelOptions, making the send button look dead.
     */
    private val transportExecutor = Executors.newSingleThreadExecutor()
    private val backgroundExecutor = Executors.newSingleThreadExecutor()
    private val controlExecutor = Executors.newFixedThreadPool(2)

    @Volatile private var bootstrapCacheJson: String? = null
    @Volatile private var bootstrapCacheToken: String? = null

    private fun baseUrl(): String = store.apiBase.ifBlank { BuildConfig.MOBILE_BASE_URL }.trimEnd('/')

    private fun client(): MobileTransportClient = MobileTransportClient(
        baseUrl = baseUrl(),
        tokenProvider = { store.deviceToken },
    )

    @JavascriptInterface fun getBase(): String = baseUrl()

    @JavascriptInterface fun setBase(value: String): String {
        store.apiBase = value
        return baseUrl()
    }

    @JavascriptInterface fun installationId(): String = store.installationId()
    @JavascriptInterface fun hasToken(): Boolean = !store.deviceToken.isNullOrBlank()
    @JavascriptInterface fun hasBootstrapCache(): Boolean =
        cachedBootstrapPayload() != null

    @JavascriptInterface fun isConnected(): Boolean = hasBootstrapCache()

    @JavascriptInterface fun clearToken() {
        invalidateBootstrapCache()
        store.clearToken()
    }
    @JavascriptInterface fun getCursor(): Long = store.cursor

    private fun cachedBootstrapPayload(): JSONObject? {
        val token = store.deviceToken?.takeIf { it.isNotBlank() } ?: return null
        if (bootstrapCacheToken != token) return null
        val raw = bootstrapCacheJson ?: return null
        return try {
            JSONObject(raw).put("cached", true)
        } catch (_: Throwable) {
            null
        }
    }

    @Synchronized
    private fun invalidateBootstrapCache(clearPersistedMetadata: Boolean = true) {
        bootstrapCacheJson = null
        bootstrapCacheToken = null
        if (clearPersistedMetadata) store.clearBootstrapSession()
    }

    @Synchronized
    private fun rememberBootstrap(payload: JSONObject): JSONObject {
        val bound = payload.optBoolean("bound", false)
        if (!bound) {
            invalidateBootstrapCache()
            return payload
        }
        val conversation = payload.optJSONObject("conversation") ?: JSONObject()
        val sessionId = conversation.optString("session_id").takeIf { it.isNotBlank() }
        val sessionKey = conversation.optString("session_key").takeIf { it.isNotBlank() }
        bootstrapCacheJson = payload.toString()
        bootstrapCacheToken = store.deviceToken
        store.saveBootstrapSession(sessionId, sessionKey)
        return payload
    }

    @Synchronized
    private fun ensureDeviceToken(force: Boolean = false): JSONObject {
        val existing = store.deviceToken
        if (!force && !existing.isNullOrBlank()) {
            return JSONObject()
                .put("ok", true)
                .put("installation_id", store.installationId())
                .put("existing", true)
        }
        // auto_pair contract: only installation_id is required. No pairing code,
        // no legacy rotate flag. The server returns a fresh device_token.
        val paired = client().pairPayload(store.installationId())
        val token = paired.optString("device_token")
        if (token.isBlank()) throw IllegalStateException("device_token_missing")
        store.saveToken(token)
        return JSONObject()
            .put("ok", paired.optBoolean("ok", true))
            .put("installation_id", paired.optString("installation_id", store.installationId()))
            .put("existing", false)
    }


    @Synchronized
    private fun refreshDeviceTokenAfterUnauthorized(failedToken: String?): JSONObject {
        val current = store.deviceToken
        if (!current.isNullOrBlank() && current != failedToken) {
            return JSONObject()
                .put("ok", true)
                .put("installation_id", store.installationId())
                .put("existing", true)
        }
        invalidateBootstrapCache()
        store.invalidateToken()
        return ensureDeviceToken(force = true)
    }

    private fun shouldRecoverUnauthorized(action: String): Boolean =
        action in setOf(
            "sessions", "memories", "deleteMemory", "bootstrap", "sendText", "poll", "ack", "cancel",
            "modelOptions", "setModel", "approval",
            "adminStatus", "adminDeployLog",
        )

    private fun executeAction(action: String, body: JSONObject): JSONObject =
        when (action) {
            "pair", "ensureToken" -> {
                body.optString("api_base").takeIf { it.isNotBlank() }?.let { store.apiBase = it }
                ensureDeviceToken(body.optBoolean("force", false))
            }
            "sessions" -> client().sessionsPayload()
            "memories" -> client().memoriesPayload()
            "deleteMemory" -> {
                val memoryId = body.optString("memory_id")
                if (memoryId.isBlank()) throw IllegalArgumentException("memory_id_required")
                client().deleteMemoryPayload(memoryId)
            }
            "selectSession" -> {
                val sessionKey = body.optString("session_key")
                val sessionId = body.optString("session_id")
                if (sessionKey.isBlank() && sessionId.isBlank()) {
                    throw IllegalArgumentException("session_identity_required")
                }
                val selected = client().pairPayload(
                    installationId = store.installationId(),
                    sessionKey = sessionKey.takeIf { it.isNotBlank() },
                    sessionId = sessionId.takeIf { it.isNotBlank() },
                )
                val returnedToken = selected.optString("device_token")
                if (returnedToken.isNotBlank() && returnedToken != store.deviceToken) {
                    invalidateBootstrapCache()
                    store.saveToken(returnedToken)
                } else {
                    invalidateBootstrapCache()
                }
                selected
            }
            "bootstrap" -> {
                val force = body.optBoolean("force", false)
                val cached = if (force) null else cachedBootstrapPayload()
                cached ?: rememberBootstrap(
                    client().bootstrapPayload(body.optLong("cursor", store.cursor))
                )
            }
            "sendText" -> client().sendPayload(
                messageId = body.optString("message_id"),
                text = body.optString("text"),
            ).also {
                invalidateBootstrapCache(clearPersistedMetadata = false)
            }
            "poll" -> client().pollPayload(body.optLong("cursor", store.cursor))
            "ack" -> {
                val cursor = body.optLong("cursor", store.cursor)
                client().ack(cursor)
                store.cursor = cursor
                JSONObject().put("ok", true).put("cursor", cursor)
            }
            "cancel" -> client().cancelPayload(body.optString("turn_id"))
            "modelOptions" -> client().modelOptionsPayload()
            "setModel" -> client().setModelPayload(
                model = body.optString("model").takeIf { it.isNotBlank() },
                effort = body.optString("effort").takeIf { it.isNotBlank() },
                provider = body.optString("provider").takeIf { it.isNotBlank() },
            )
            "approval" -> client().approvalPayload(
                approvalId = body.optString("approval_id"),
                decision = body.optString("decision"),
                scope = body.optString("scope", "once"),
            )
            "revoke" -> {
                val result = client().revoke()
                invalidateBootstrapCache()
                store.clearToken()
                result
            }
            "adminStatus" -> client().adminStatusPayload()
            "adminMerge" -> client().adminMergePayload()
            "adminRollback" -> client().adminRollbackPayload()
            "adminDeployLog" -> client().adminDeployLogPayload(
                body.optInt("lines", 100),
            )
            else -> throw IllegalArgumentException("unknown_native_action")
        }

    @JavascriptInterface
    fun checkForUpdates() {
        webView.post { checkUpdates() }
    }

    @JavascriptInterface
    fun haptic() {
        webView.post {
            webView.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
        }
    }

    @JavascriptInterface
    fun request(id: String, action: String, payload: String) {
        if (action == "voiceInput") {
            webView.post { startVoiceInput(id) }
            return
        }
        if (action == "pickAttachment") {
            val body = try {
                if (payload.isBlank()) JSONObject() else JSONObject(payload)
            } catch (error: Throwable) {
                resolve(id, false, JSONObject().put("status", 0)
                    .put("error", error.message ?: "invalid_native_payload"))
                return
            }
            val kind = body.optString("kind", "file").let {
                if (it == "photo") "photo" else "file"
            }
            webView.post { startAttachmentPicker(id, kind) }
            return
        }
        val executor = when (bridgeLane(action)) {
            BridgeLane.TRANSPORT -> transportExecutor
            BridgeLane.BACKGROUND -> backgroundExecutor
            BridgeLane.CONTROL -> controlExecutor
        }
        executor.execute {
            val body = try {
                if (payload.isBlank()) JSONObject() else JSONObject(payload)
            } catch (error: Throwable) {
                resolve(
                    id,
                    false,
                    JSONObject().put("status", 0).put("error", error.message ?: "invalid_native_payload"),
                )
                return@execute
            }

            val failedToken = store.deviceToken
            try {
                resolve(id, true, executeAction(action, body))
            } catch (firstError: Throwable) {
                val firstStatus = (firstError as? MobileTransportException)?.status ?: 0
                var finalError = firstError

                if (firstStatus == 401 && shouldRecoverUnauthorized(action)) {
                    try {
                        invalidateBootstrapCache()
                        /*
                         * auto_pair contract: POST /mobile/pair with installation_id only.
                         * No pairing_code or extra rotation field is sent.
                         * MobileTransportClient.pairPayload() is unauthenticated and
                         * MobileSessionStore.saveToken() persists the replacement token
                         * in EncryptedSharedPreferences without resetting the cursor.
                         */
                        refreshDeviceTokenAfterUnauthorized(failedToken)
                        if (action != "bootstrap") {
                            executeAction(
                                "bootstrap",
                                JSONObject().put("cursor", store.cursor).put("force", true),
                            )
                        }
                        resolve(id, true, executeAction(action, body))
                        return@execute
                    } catch (retryError: Throwable) {
                        finalError = retryError
                    }
                }

                val finalStatus = (finalError as? MobileTransportException)?.status ?: firstStatus
                if (finalStatus == 401) store.invalidateToken()
                resolve(
                    id,
                    false,
                    JSONObject()
                        .put("status", finalStatus)
                        .put("error", finalError.message ?: "native_transport_error"),
                )
            }
        }
    }

    fun uploadPickedAttachment(
        requestId: String,
        kind: String,
        fileName: String,
        mimeType: String,
        bytes: ByteArray,
    ) {
        transportExecutor.execute {
            val messageId = "android-media-" + UUID.randomUUID().toString()
            val failedToken = store.deviceToken
            try {
                val result = client().sendAttachmentPayload(
                    messageId, kind, fileName, mimeType, bytes,
                )
                invalidateBootstrapCache(clearPersistedMetadata = false)
                resolve(requestId, true, result)
            } catch (firstError: Throwable) {
                var finalError = firstError
                val firstStatus = (firstError as? MobileTransportException)?.status ?: 0
                if (firstStatus == 401) {
                    try {
                        refreshDeviceTokenAfterUnauthorized(failedToken)
                        rememberBootstrap(client().bootstrapPayload(store.cursor))
                        val retried = client().sendAttachmentPayload(
                            messageId, kind, fileName, mimeType, bytes,
                        )
                        invalidateBootstrapCache(clearPersistedMetadata = false)
                        resolve(requestId, true, retried)
                        return@execute
                    } catch (retryError: Throwable) {
                        finalError = retryError
                    }
                }
                val status = (finalError as? MobileTransportException)?.status ?: firstStatus
                if (status == 401) store.invalidateToken()
                resolve(
                    requestId,
                    false,
                    JSONObject().put("status", status)
                        .put("error", finalError.message ?: "attachment_upload_failed"),
                )
            }
        }
    }

    fun notifyAttachmentSelected(
        requestId: String,
        kind: String,
        fileName: String,
        mimeType: String,
    ) {
        val payload = JSONObject()
            .put("kind", kind)
            .put("file_name", fileName)
            .put("mime_type", mimeType)
        val script = "window.KissneNativeBridge && window.KissneNativeBridge.attachmentSelected(" +
            JSONObject.quote(requestId) + "," + JSONObject.quote(payload.toString()) + ");"
        webView.post { webView.evaluateJavascript(script, null) }
    }

    fun resolveNative(id: String, ok: Boolean, payload: JSONObject) {
        resolve(id, ok, payload)
    }

    private fun resolve(id: String, ok: Boolean, payload: JSONObject) {
        val script = "window.KissneNativeBridge && window.KissneNativeBridge.resolve(" +
            JSONObject.quote(id) + "," + ok + "," + JSONObject.quote(payload.toString()) + ");"
        webView.post { webView.evaluateJavascript(script, null) }
    }

    fun close() {
        transportExecutor.shutdownNow()
        backgroundExecutor.shutdownNow()
        controlExecutor.shutdownNow()
    }
}

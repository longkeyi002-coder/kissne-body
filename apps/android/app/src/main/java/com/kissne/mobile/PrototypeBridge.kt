package com.kissne.mobile

import android.view.HapticFeedbackConstants
import android.webkit.JavascriptInterface
import android.webkit.WebView
import org.json.JSONObject
import java.util.concurrent.Executors

class PrototypeBridge(
    private val webView: WebView,
    private val store: MobileSessionStore,
    private val checkUpdates: () -> Unit = {},
) {
    /*
     * Keep chat transport isolated from slower control-plane calls.
     * Provider/model discovery can legitimately take seconds; when every bridge
     * request shared one single-thread executor it blocked bootstrap, polling
     * and sendText behind modelOptions, making the send button look dead.
     */
    private val transportExecutor = Executors.newSingleThreadExecutor()
    private val controlExecutor = Executors.newFixedThreadPool(2)

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
    @JavascriptInterface fun isConnected(): Boolean =
        !store.deviceToken.isNullOrBlank() && store.connectionReady
    @JavascriptInterface fun clearToken() = store.clearToken()
    @JavascriptInterface fun getCursor(): Long = store.cursor

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
        store.invalidateToken()
        return ensureDeviceToken(force = true)
    }

    private fun shouldRecoverUnauthorized(action: String): Boolean =
        action in setOf(
            "sessions", "bootstrap", "sendText", "poll", "ack", "cancel",
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
            "selectSession" -> {
                val sessionKey = body.optString("session_key")
                if (sessionKey.isBlank()) throw IllegalArgumentException("session_key_required")
                val selected = client().pairPayload(store.installationId(), sessionKey)
                val returnedToken = selected.optString("device_token")
                if (returnedToken.isNotBlank() && returnedToken != store.deviceToken) {
                    store.saveToken(returnedToken)
                }
                selected
            }
            "bootstrap" -> {
                val boot = client().bootstrapPayload(body.optLong("cursor", store.cursor))
                store.markConnectionReady(true)
                boot
            }
            "sendText" -> client().sendPayload(
                messageId = body.optString("message_id"),
                text = body.optString("text"),
            )
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
            )
            "approval" -> client().approvalPayload(
                approvalId = body.optString("approval_id"),
                decision = body.optString("decision"),
                scope = body.optString("scope", "once"),
            )
            "revoke" -> {
                val result = client().revoke()
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
        val executor = when (bridgeLane(action)) {
            BridgeLane.CONTROL -> controlExecutor
            BridgeLane.TRANSPORT -> transportExecutor
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
                        /*
                         * auto_pair contract: POST /mobile/pair with installation_id only.
                         * No pairing_code or extra rotation field is sent.
                         * MobileTransportClient.pairPayload() is unauthenticated and
                         * MobileSessionStore.saveToken() persists the replacement token
                         * in EncryptedSharedPreferences without resetting the cursor.
                         */
                        refreshDeviceTokenAfterUnauthorized(failedToken)
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

    private fun resolve(id: String, ok: Boolean, payload: JSONObject) {
        val script = "window.KissneNativeBridge && window.KissneNativeBridge.resolve(" +
            JSONObject.quote(id) + "," + ok + "," + JSONObject.quote(payload.toString()) + ");"
        webView.post { webView.evaluateJavascript(script, null) }
    }

    fun close() {
        transportExecutor.shutdownNow()
        controlExecutor.shutdownNow()
    }
}

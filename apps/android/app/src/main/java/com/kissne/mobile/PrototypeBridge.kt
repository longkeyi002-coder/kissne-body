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
        val paired = client().pairPayload(store.installationId())
        val token = paired.optString("device_token")
        if (token.isBlank()) throw IllegalStateException("device_token_missing")
        store.saveToken(token)
        return JSONObject()
            .put("ok", paired.optBoolean("ok", true))
            .put("installation_id", paired.optString("installation_id", store.installationId()))
            .put("existing", false)
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
        val executor = when (action) {
            "modelOptions", "setModel", "sessions", "selectSession",
            "adminStatus", "adminMerge", "adminRollback", "adminDeployLog" -> controlExecutor
            else -> transportExecutor
        }
        executor.execute {
            try {
                val body = if (payload.isBlank()) JSONObject() else JSONObject(payload)
                val result = when (action) {
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
                resolve(id, true, result)
            } catch (error: Throwable) {
                val status = (error as? MobileTransportException)?.status ?: 0
                /*
                 * Optional control endpoints must never invalidate an otherwise
                 * working chat session. A reverse-proxy/version mismatch on
                 * model/admin routes can return 401 independently of the core
                 * mobile transport. Core transport 401s still clear the token.
                 */
                val coreAuthAction = action in setOf(
                    "sessions", "selectSession", "bootstrap", "sendText", "poll", "ack",
                    "cancel", "approval", "revoke",
                )
                if (status == 401 && coreAuthAction) store.clearToken()
                val payloadJson = JSONObject()
                    .put("status", status)
                    .put("error", error.message ?: "native_transport_error")
                resolve(id, false, payloadJson)
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

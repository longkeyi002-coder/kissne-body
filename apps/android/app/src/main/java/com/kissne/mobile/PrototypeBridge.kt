package com.kissne.mobile

import android.view.HapticFeedbackConstants
import android.webkit.JavascriptInterface
import android.webkit.WebView
import org.json.JSONObject
import java.util.concurrent.Executors

class PrototypeBridge(
    private val webView: WebView,
    private val store: MobileSessionStore,
) {
    private val executor = Executors.newSingleThreadExecutor()

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
    @JavascriptInterface fun getSessionKey(): String = store.sessionKey
    @JavascriptInterface fun setSessionKey(value: String) { store.sessionKey = value }
    @JavascriptInterface fun getCursor(): Long = store.cursor

    @JavascriptInterface
    fun haptic() {
        webView.post {
            webView.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
        }
    }

    @JavascriptInterface
    fun request(id: String, action: String, payload: String) {
        executor.execute {
            try {
                val body = if (payload.isBlank()) JSONObject() else JSONObject(payload)
                val result = when (action) {
                    "pair" -> {
                        body.optString("api_base").takeIf { it.isNotBlank() }?.let { store.apiBase = it }
                        body.optString("session_key").takeIf { it.isNotBlank() }?.let { store.sessionKey = it }
                        val paired = client().pairPayload(
                            pairingCode = body.optString("pairing_code"),
                            installationId = store.installationId(),
                            sessionKey = store.sessionKey.ifBlank { null },
                        )
                        paired.optString("device_token").takeIf { it.isNotBlank() }?.let(store::saveToken)
                        JSONObject()
                            .put("ok", paired.optBoolean("ok", true))
                            .put("installation_id", paired.optString("installation_id"))
                            .put("conversation_bound", paired.optBoolean("conversation_bound", false))
                    }
                    "bootstrap" -> {
                        val boot = client().bootstrapPayload(body.optLong("cursor", store.cursor))
                        store.markConnectionReady(boot.optBoolean("bound", false))
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
                    else -> throw IllegalArgumentException("unknown_native_action")
                }
                resolve(id, true, result)
            } catch (error: Throwable) {
                val status = (error as? MobileTransportException)?.status ?: 0
                if (status == 401) store.clearToken()
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

    fun close() { executor.shutdownNow() }
}

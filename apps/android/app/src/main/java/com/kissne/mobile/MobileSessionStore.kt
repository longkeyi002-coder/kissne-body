package com.kissne.mobile

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.util.UUID

class MobileSessionStore(context: Context) {
    private val prefs = EncryptedSharedPreferences.create(
        context,
        "kissne_mobile_secure",
        MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
    )

    val deviceToken: String?
        get() = prefs.getString("device_token", null)

    val connectionReady: Boolean
        get() = prefs.getBoolean("connection_ready", false)

    val cachedSessionId: String?
        get() = prefs.getString("bootstrap_session_id", null)

    val cachedSessionKey: String?
        get() = prefs.getString("bootstrap_session_key", null)

    var cursor: Long
        get() = prefs.getLong("cursor", 0L)
        set(value) {
            prefs.edit().putLong("cursor", value).apply()
        }

    var apiBase: String
        get() = prefs.getString("api_base", null).orEmpty()
        set(value) {
            val normalized = value.trim().trimEnd('/')
            prefs.edit().putString("api_base", normalized).apply()
        }

    fun installationId(): String {
        val existing = prefs.getString("installation_id", null)
        if (existing != null) return existing

        val created = "android-${UUID.randomUUID()}"
        prefs.edit().putString("installation_id", created).apply()
        return created
    }

    fun saveToken(token: String) {
        prefs.edit()
            .putString("device_token", token)
            .putBoolean("connection_ready", false)
            .apply()
    }

    fun invalidateToken() {
        prefs.edit()
            .remove("device_token")
            .putBoolean("connection_ready", false)
            .remove("bootstrap_session_id")
            .remove("bootstrap_session_key")
            .apply()
    }

    fun saveBootstrapSession(sessionId: String?, sessionKey: String?) {
        val editor = prefs.edit().putBoolean("connection_ready", true)
        if (sessionId.isNullOrBlank()) editor.remove("bootstrap_session_id")
        else editor.putString("bootstrap_session_id", sessionId)
        if (sessionKey.isNullOrBlank()) editor.remove("bootstrap_session_key")
        else editor.putString("bootstrap_session_key", sessionKey)
        editor.apply()
    }

    fun clearBootstrapSession() {
        prefs.edit()
            .putBoolean("connection_ready", false)
            .remove("bootstrap_session_id")
            .remove("bootstrap_session_key")
            .apply()
    }

    fun markConnectionReady(ready: Boolean) {
        if (ready) prefs.edit().putBoolean("connection_ready", true).apply()
        else clearBootstrapSession()
    }

    fun clearToken() {
        prefs.edit()
            .remove("device_token")
            .putBoolean("connection_ready", false)
            .remove("bootstrap_session_id")
            .remove("bootstrap_session_key")
            .putLong("cursor", 0L)
            .apply()
    }
}

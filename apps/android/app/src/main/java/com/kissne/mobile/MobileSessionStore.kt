package com.kissne.mobile

import android.content.Context
import java.util.UUID

class MobileSessionStore(context: Context) {
    private val prefs = context.getSharedPreferences("kissne_mobile", Context.MODE_PRIVATE)
    val deviceToken: String? get() = prefs.getString("device_token", null)
    var cursor: Long
        get() = prefs.getLong("cursor", 0L)
        set(value) = prefs.edit().putLong("cursor", value).apply()
    fun installationId(): String {
        prefs.getString("installation_id", null)?.let { return it }
        val value = "android-" + UUID.randomUUID()
        prefs.edit().putString("installation_id", value).apply()
        return value
    }
    fun saveToken(token: String) { prefs.edit().putString("device_token", token).apply() }
    fun clearToken() { prefs.edit().remove("device_token").apply() }
}

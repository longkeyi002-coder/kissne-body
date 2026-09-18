package com.kissne.mobile

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.util.UUID

class MobileSessionStore(context: Context) {
    private val prefs = EncryptedSharedPreferences.create(
        context,
        "kissne_mobile_secure",
        MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
    )
    val deviceToken: String? get() = prefs.getString("device_token", null)
    var cursor: Long
        get() = prefs.getLong("cursor", 0L)
        set(value) = prefs.edit().putLong("cursor", value).apply()
    fun installationId(): String = prefs.getString("installation_id", null) ?: ("android-" + UUID.randomUUID()).also {
        prefs.edit().putString("installation_id", it).apply()
    }
    fun saveToken(token: String) { prefs.edit().putString("device_token", token).apply() }
    fun clearToken() { prefs.edit().remove("device_token").apply() }
}

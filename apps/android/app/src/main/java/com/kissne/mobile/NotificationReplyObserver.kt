package com.kissne.mobile

import android.content.Context

/** Reads its own cursor without acknowledging events needed by the chat UI. */
internal object NotificationReplyObserver {
    @Synchronized
    fun poll(context: Context, store: MobileSessionStore): Boolean {
        if (store.deviceToken.isNullOrBlank()) return false
        val prefs = context.getSharedPreferences("kissne_notifications", Context.MODE_PRIVATE)
        val key = "cursor:" + store.installationId()
        val cursor = prefs.getLong(key, store.cursor)
        val client = MobileTransportClient(BuildConfig.MOBILE_BASE_URL, { store.deviceToken }, 5000, 10000)
        val payload = client.pollPayload(cursor)
        val events = payload.optJSONArray("events")
        for (index in 0 until (events?.length() ?: 0)) {
            val event = events?.optJSONObject(index) ?: continue
            if (event.optString("type") != "completed") continue
            if (!isReplyPresentation(event.optString("presentation"))) continue
            val text = event.optString("text").trim()
            if (text.isBlank()) continue
            val id = event.optString("turn_id").ifBlank {
                event.optString("event_id").ifBlank { event.optString("message_id") }
            }
            KissneNotificationService.notifyReply(context, id, "Kissne 回复完成", text.replace(Regex("\\s+"), " ").take(64))
        }
        // Never acknowledge or change the UI cursor: it still needs these events.
        prefs.edit().putLong(key, maxOf(prefs.getLong(key, cursor), payload.optLong("next_cursor", cursor))).apply()
        if (payload.has("pending_turn_id")) {
            return !payload.isNull("pending_turn_id") && payload.optString("pending_turn_id").isNotBlank()
        }
        val boot = client.bootstrapPayload(cursor)
        return !boot.isNull("pending_turn_id") && boot.optString("pending_turn_id").isNotBlank()
    }
}

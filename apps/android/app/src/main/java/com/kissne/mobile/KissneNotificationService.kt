package com.kissne.mobile

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/** Keeps a resident status notification and alerts when a background reply arrives. */
class KissneNotificationService : Service() {
    private val reader = Executors.newSingleThreadScheduledExecutor()
    @Volatile private var stopped = false
    private var lastStatus = ""
    private var lastLegacyCheck = 0L
    private var legacyPending = false
    private val sessionStore by lazy { MobileSessionStore(this) }

    override fun onCreate() {
        super.onCreate()
        ensureChannel(this)
        startForeground(NOTIFICATION_ID, notification(this, "Kissne 已就绪", "打开人人星继续对话"))
        reader.scheduleWithFixedDelay({ readReplies() }, 0, 3, TimeUnit.SECONDS)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // WebView activity hints are not evidence that the server is still working.
        // The independent, read-only observer owns the resident status.
        return START_STICKY
    }

    private fun readReplies() {
        if (stopped) return
        try {
            val store = sessionStore
            if (store.deviceToken.isNullOrBlank()) {
                setStatus("Kissne 未连接", "打开 Kissne 恢复连接")
                return
            }
            val prefs = getSharedPreferences("kissne_notifications", MODE_PRIVATE)
            val key = "cursor:" + store.installationId()
            val cursor = prefs.getLong(key, store.cursor)
            val client = MobileTransportClient(BuildConfig.MOBILE_BASE_URL, { store.deviceToken }, 5000, 10000)
            val payload = client.pollPayload(cursor)
            if (stopped) return
            val events = payload.optJSONArray("events")
            for (index in 0 until (events?.length() ?: 0)) {
                val event = events?.optJSONObject(index) ?: continue
                if (event.optString("type") != "completed") continue
                if (event.optString("presentation") in listOf("hidden", "internal_notification", "tool_progress", "tool_call", "tool_result")) continue
                val text = event.optString("text").trim()
                if (text.isBlank()) continue
                val id = event.optString("turn_id").ifBlank {
                    event.optString("event_id").ifBlank { event.optString("message_id") }
                }
                notifyReply(this, id, "Kissne 回复完成", text.replace(Regex("\\s+"), " ").take(64))
            }
            // Never acknowledge or change the UI cursor: it still needs these events.
            prefs.edit().putLong(key, payload.optLong("next_cursor", cursor)).apply()
            val pending = if (payload.has("pending_turn_id")) {
                !payload.isNull("pending_turn_id") && payload.optString("pending_turn_id").isNotBlank()
            } else {
                // Compatibility with the deployed older adapter. Bootstrap is non-destructive.
                val now = android.os.SystemClock.elapsedRealtime()
                if (lastLegacyCheck == 0L || now - lastLegacyCheck >= 15000) {
                    val boot = client.bootstrapPayload(cursor)
                    legacyPending = !boot.isNull("pending_turn_id") && boot.optString("pending_turn_id").isNotBlank()
                    lastLegacyCheck = now
                }
                legacyPending
            }
            if (pending) setStatus("Kissne 正在工作", "正在处理你的消息")
            else setStatus("Kissne 已就绪", "打开人人星继续对话")
        } catch (_: Exception) {
            if (!stopped) setStatus("Kissne 连接暂不可用", "正在等待恢复连接")
        }
    }

    private fun setStatus(title: String, body: String) {
        if (stopped || lastStatus == title) return
        NotificationManagerCompat.from(this).notify(NOTIFICATION_ID, notification(this, title, body))
        lastStatus = title
    }

    override fun onTimeout(startId: Int, fgsType: Int) {
        // Android 15 limits dataSync foreground services; stop promptly when its budget expires.
        stopSelf()
    }

    override fun onDestroy() {
        stopped = true
        reader.shutdownNow()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun notification(context: Context, title: String, body: String): Notification {
        val open = PendingIntent.getActivity(
            context,
            0,
            Intent(context, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
            },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.kissne_app_icon)
            .setContentTitle(title)
            .setContentText(body)
            .setContentIntent(open)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    companion object {
        private fun messageNotification(context: Context, title: String, body: String): Notification {
            val open = PendingIntent.getActivity(
                context,
                1,
                Intent(context, MainActivity::class.java).apply {
                    flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
                },
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
            return NotificationCompat.Builder(context, MESSAGE_CHANNEL_ID)
                .setSmallIcon(R.drawable.kissne_app_icon)
                .setContentTitle(title)
                .setContentText(body)
                .setContentIntent(open)
                .setAutoCancel(true)
                .setCategory(NotificationCompat.CATEGORY_MESSAGE)
                .setPriority(NotificationCompat.PRIORITY_DEFAULT)
                .build()
        }

        @Synchronized
        fun notifyReply(context: Context, id: String, title: String, body: String) {
            if (id.isBlank()) return
            val prefs = context.getSharedPreferences("kissne_notifications", Context.MODE_PRIVATE)
            val seen = LinkedHashSet(prefs.getStringSet("seen_replies", emptySet()).orEmpty())
            if (!seen.add(id)) return
            while (seen.size > 128) seen.remove(seen.first())
            prefs.edit().putStringSet("seen_replies", seen).apply()
            if (!MainActivity.isVisible) {
                ensureChannel(context)
                NotificationManagerCompat.from(context).notify(
                    MESSAGE_NOTIFICATION_ID, messageNotification(context, title, body),
                )
            }
        }

        const val CHANNEL_ID = "kissne_status"
        const val MESSAGE_CHANNEL_ID = "kissne_messages"
        const val NOTIFICATION_ID = 2107
        const val MESSAGE_NOTIFICATION_ID = 2108
        fun start(context: Context) {
            ensureChannel(context)
            ContextCompat.startForegroundService(
                context,
                Intent(context, KissneNotificationService::class.java),
            )
        }

        fun update(context: Context, state: String, title: String, body: String) {
            // Status hints may wake an observer only while the app is foregrounded.
            // Background service starts are restricted after Android ends dataSync.
            if (MainActivity.isVisible) start(context)
        }

        private fun ensureChannel(context: Context) {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Kissne 状态",
                NotificationManager.IMPORTANCE_LOW,
            ).apply {
                description = "Kissne 对话处理状态"
                setSound(null, null)
                enableVibration(false)
                setShowBadge(false)
            }
            val messageChannel = NotificationChannel(
                MESSAGE_CHANNEL_ID,
                "Kissne 消息",
                NotificationManager.IMPORTANCE_DEFAULT,
            ).apply {
                description = "Kissne 的新回复"
            }
            context.getSystemService(NotificationManager::class.java).createNotificationChannels(
                listOf(channel, messageChannel),
            )
        }
    }
}

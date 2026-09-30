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

/** Observes an active task; idle message checks use the system job scheduler. */
class KissneNotificationService : Service() {
    private val reader = Executors.newSingleThreadScheduledExecutor()
    @Volatile private var stopped = false
    private var lastStatus = ""
    private val sessionStore by lazy { MobileSessionStore(this) }

    override fun onCreate() {
        super.onCreate()
        ensureChannel(this)
        startForeground(NOTIFICATION_ID, notification(this, "Kissne 正在工作", "正在处理你的消息"))
        reader.scheduleWithFixedDelay({ readReplies() }, 0, 3, TimeUnit.SECONDS)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // An interrupted task must not resurrect an idle foreground service.
        return START_NOT_STICKY
    }

    private fun readReplies() {
        if (stopped) return
        try {
            val pending = NotificationReplyObserver.poll(this, sessionStore)
            if (stopped) return
            if (pending) setStatus("Kissne 正在工作", "正在处理你的消息")
            else stopSelf()
        } catch (_: Exception) {
            // No stale work notification after an unreachable task. A later hint can resume it.
            stopSelf()
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
        stopForeground(STOP_FOREGROUND_REMOVE)
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
            when (notificationAction(state, MainActivity.isVisible)) {
                NotificationAction.START -> start(context)
                NotificationAction.STOP -> {
                    context.stopService(Intent(context, KissneNotificationService::class.java))
                    NotificationManagerCompat.from(context).cancel(NOTIFICATION_ID)
                }
                NotificationAction.IGNORE -> Unit
            }
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

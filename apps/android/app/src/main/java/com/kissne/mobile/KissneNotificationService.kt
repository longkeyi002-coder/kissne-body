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

/** Keeps a resident status notification and alerts when a background reply arrives. */
class KissneNotificationService : Service() {
    override fun onCreate() {
        super.onCreate()
        ensureChannel(this)
        startForeground(NOTIFICATION_ID, notification(this, "Kissne 已就绪", "打开人人星继续对话"))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val state = intent?.getStringExtra(EXTRA_STATE).orEmpty()
        val title = intent?.getStringExtra(EXTRA_TITLE).orEmpty().ifBlank { "Kissne 已就绪" }
        val body = intent?.getStringExtra(EXTRA_BODY).orEmpty().ifBlank { "打开人人星继续对话" }
        NotificationManagerCompat.from(this).notify(NOTIFICATION_ID, notification(this, title, body))
        if (state == "done" && !MainActivity.isVisible) {
            NotificationManagerCompat.from(this).notify(MESSAGE_NOTIFICATION_ID, messageNotification(this, title, body))
        }
        return START_STICKY
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

    companion object {
        const val CHANNEL_ID = "kissne_status"
        const val MESSAGE_CHANNEL_ID = "kissne_messages"
        const val NOTIFICATION_ID = 2107
        const val MESSAGE_NOTIFICATION_ID = 2108
        private const val EXTRA_STATE = "state"
        private const val EXTRA_TITLE = "title"
        private const val EXTRA_BODY = "body"

        fun start(context: Context) {
            ensureChannel(context)
            ContextCompat.startForegroundService(
                context,
                Intent(context, KissneNotificationService::class.java),
            )
        }

        fun update(context: Context, state: String, title: String, body: String) {
            ensureChannel(context)
            val intent = Intent(context, KissneNotificationService::class.java)
                .putExtra(EXTRA_STATE, state)
                .putExtra(EXTRA_TITLE, title)
                .putExtra(EXTRA_BODY, body)
            ContextCompat.startForegroundService(context, intent)
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

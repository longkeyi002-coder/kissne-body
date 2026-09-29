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

/** Keeps one quiet, actionable status notification for the chat connection. */
class KissneNotificationService : Service() {
    override fun onCreate() {
        super.onCreate()
        ensureChannel(this)
        startForeground(NOTIFICATION_ID, notification(this, "Kissne 已就绪", "打开人人星继续对话"))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val title = intent?.getStringExtra(EXTRA_TITLE).orEmpty().ifBlank { "Kissne 已就绪" }
        val body = intent?.getStringExtra(EXTRA_BODY).orEmpty().ifBlank { "打开人人星继续对话" }
        NotificationManagerCompat.from(this).notify(NOTIFICATION_ID, notification(this, title, body))
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

    companion object {
        const val CHANNEL_ID = "kissne_status"
        const val NOTIFICATION_ID = 2107
        private const val EXTRA_TITLE = "title"
        private const val EXTRA_BODY = "body"

        fun start(context: Context) {
            ensureChannel(context)
            ContextCompat.startForegroundService(
                context,
                Intent(context, KissneNotificationService::class.java),
            )
        }

        fun update(context: Context, title: String, body: String) {
            ensureChannel(context)
            val intent = Intent(context, KissneNotificationService::class.java)
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
            context.getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }
}

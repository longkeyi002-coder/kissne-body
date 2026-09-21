package com.kissne.mobile

import android.app.DownloadManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.Settings
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

data class KissneUpdate(
    val versionCode: Int,
    val versionName: String,
    val downloadUrl: String,
    val notes: String,
)

class UpdateManager(private val activity: AppCompatActivity) {
    private val executor = Executors.newSingleThreadExecutor()
    private val downloadManager = activity.getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
    private var checkedAutomatically = false
    private var pendingUpdate: KissneUpdate? = null
    private var activeDownloadId: Long = -1L

    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action != DownloadManager.ACTION_DOWNLOAD_COMPLETE) return
            val id = intent.getLongExtra(DownloadManager.EXTRA_DOWNLOAD_ID, -1L)
            if (id != activeDownloadId || id < 0) return
            installDownloaded(id)
        }
    }

    init {
        ContextCompat.registerReceiver(
            activity, receiver, IntentFilter(DownloadManager.ACTION_DOWNLOAD_COMPLETE),
            ContextCompat.RECEIVER_NOT_EXPORTED,
        )
    }

    fun checkForUpdates(force: Boolean = false) {
        if (!force && checkedAutomatically) return
        if (!force) checkedAutomatically = true
        executor.execute {
            try {
                val update = fetchLatest()
                activity.runOnUiThread {
                    if (update.versionCode > BuildConfig.VERSION_CODE) showUpdate(update)
                    else if (force) Toast.makeText(activity, "已经是最新版本", Toast.LENGTH_SHORT).show()
                }
            } catch (_: Throwable) {
                if (force) activity.runOnUiThread {
                    Toast.makeText(activity, "暂时无法检查更新", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun fetchLatest(): KissneUpdate {
        val url = URL("https://api.github.com/repos/longkeyi002-coder/kissne-body/releases/tags/kissne-android-latest")
        val connection = (url.openConnection() as HttpURLConnection).apply {
            connectTimeout = 8_000
            readTimeout = 8_000
            setRequestProperty("Accept", "application/vnd.github+json")
            setRequestProperty("User-Agent", "Kissne-Android/${BuildConfig.VERSION_NAME}")
        }
        return try {
            if (connection.responseCode !in 200..299) throw IllegalStateException("update_http_${connection.responseCode}")
            val json = JSONObject(connection.inputStream.bufferedReader().use { it.readText() })
            val body = json.optString("body")
            val versionCode = Regex("""(?m)^versionCode=(\d+)\s*$""")
                .find(body)?.groupValues?.get(1)?.toIntOrNull()
                ?: throw IllegalStateException("update_version_missing")
            val versionName = Regex("""(?m)^versionName=([^\r\n]+)\s*$""")
                .find(body)?.groupValues?.get(1)?.trim().orEmpty()
            val notes = Regex("""(?s)notes=(.*)$""").find(body)?.groupValues?.get(1)?.trim().orEmpty()
            val assets = json.optJSONArray("assets") ?: throw IllegalStateException("update_assets_missing")
            var downloadUrl = ""
            for (i in 0 until assets.length()) {
                val asset = assets.optJSONObject(i) ?: continue
                if (asset.optString("name") == "kissne-android.apk") {
                    downloadUrl = asset.optString("browser_download_url")
                    break
                }
            }
            if (downloadUrl.isBlank()) throw IllegalStateException("update_apk_missing")
            KissneUpdate(versionCode, versionName.ifBlank { "新版本" }, downloadUrl, notes)
        } finally {
            connection.disconnect()
        }
    }

    private fun showUpdate(update: KissneUpdate) {
        val body = buildString {
            append("发现新版本 ").append(update.versionName)
            if (update.notes.isNotBlank()) append("\n\n").append(update.notes)
        }
        AlertDialog.Builder(activity)
            .setTitle("Kissne 有更新")
            .setMessage(body)
            .setNegativeButton("稍后", null)
            .setPositiveButton("立即更新") { _, _ -> requestUpdate(update) }
            .show()
    }

    private fun requestUpdate(update: KissneUpdate) {
        pendingUpdate = update
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && !activity.packageManager.canRequestPackageInstalls()) {
            Toast.makeText(activity, "首次更新需要允许 Kissne 安装更新包", Toast.LENGTH_LONG).show()
            activity.startActivity(
                Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${activity.packageName}"))
            )
            return
        }
        startDownload(update)
    }

    fun onResume() {
        val update = pendingUpdate ?: return
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O || activity.packageManager.canRequestPackageInstalls()) {
            startDownload(update)
        }
    }

    private fun startDownload(update: KissneUpdate) {
        pendingUpdate = null
        val fileName = "kissne-${update.versionName}.apk"
        val request = DownloadManager.Request(Uri.parse(update.downloadUrl))
            .setTitle("Kissne ${update.versionName}")
            .setDescription("正在下载更新…")
            .setMimeType("application/vnd.android.package-archive")
            .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            .setDestinationInExternalFilesDir(activity, Environment.DIRECTORY_DOWNLOADS, fileName)
        activeDownloadId = downloadManager.enqueue(request)
        Toast.makeText(activity, "开始下载更新", Toast.LENGTH_SHORT).show()
    }

    private fun installDownloaded(id: Long) {
        val uri = downloadManager.getUriForDownloadedFile(id) ?: return
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        try {
            activity.startActivity(intent)
        } catch (_: Throwable) {
            Toast.makeText(activity, "更新已下载，请从通知中打开安装", Toast.LENGTH_LONG).show()
        }
    }

    fun close() {
        try { activity.unregisterReceiver(receiver) } catch (_: Throwable) {}
        executor.shutdownNow()
    }
}

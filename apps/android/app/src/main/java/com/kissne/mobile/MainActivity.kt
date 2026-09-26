package com.kissne.mobile

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.view.ViewGroup
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.webkit.WebViewAssetLoader
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.util.Locale

class MainActivity : AppCompatActivity() {
    private lateinit var webView: WebView
    private lateinit var bridge: PrototypeBridge
    private lateinit var updateManager: UpdateManager

    private var speechRecognizer: SpeechRecognizer? = null
    private var pendingVoiceRequestId: String? = null
    private var pendingAttachmentRequestId: String? = null
    private var pendingAttachmentKind: String? = null

    private val attachmentPicker =
        registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
            val requestId = pendingAttachmentRequestId ?: return@registerForActivityResult
            val kind = pendingAttachmentKind ?: "file"
            pendingAttachmentRequestId = null
            pendingAttachmentKind = null
            if (uri == null) {
                if (::bridge.isInitialized) {
                    bridge.resolveNative(requestId, true, JSONObject().put("cancelled", true))
                }
                return@registerForActivityResult
            }
            readAndUploadAttachment(requestId, kind, uri)
        }

    private val recordAudioPermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            val requestId = pendingVoiceRequestId ?: return@registerForActivityResult
            if (granted) {
                beginVoiceRecognition(requestId)
            } else {
                finishVoiceRequest(
                    requestId,
                    false,
                    JSONObject().put("status", 0).put("error", "microphone_permission_denied"),
                )
            }
        }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        WindowCompat.setDecorFitsSystemWindows(window, false)
        window.statusBarColor = Color.TRANSPARENT
        window.navigationBarColor = Color.TRANSPARENT
        WindowInsetsControllerCompat(window, window.decorView).apply {
            isAppearanceLightStatusBars = true
            isAppearanceLightNavigationBars = true
        }

        val store = MobileSessionStore(this).apply {
            // Connection settings were removed. Do not keep a stale server URL
            // from older builds in EncryptedSharedPreferences.
            apiBase = BuildConfig.MOBILE_BASE_URL
        }
        updateManager = UpdateManager(this)
        val assetLoader = WebViewAssetLoader.Builder()
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(this))
            .build()

        webView = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.useWideViewPort = true
            settings.loadWithOverviewMode = false
            settings.textZoom = 100
            settings.allowFileAccess = false
            settings.allowContentAccess = false
            settings.javaScriptCanOpenWindowsAutomatically = false
            settings.setSupportMultipleWindows(false)
            settings.mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            webViewClient = object : WebViewClient() {
                override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest) =
                    assetLoader.shouldInterceptRequest(request.url)

                override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                    val url = request.url
                    return url.scheme != "https" || url.host != "appassets.androidplatform.net"
                }
            }
        }

        val root = FrameLayout(this).apply {
            setBackgroundColor(Color.rgb(253, 252, 248))
            addView(
                webView,
                FrameLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.MATCH_PARENT
                )
            )
        }
        setContentView(root)

        /*
         * Android 15/16 edge-to-edge: consume the system bars on the native root,
         * not as WebView padding. This makes the WebView viewport itself equal to
         * the usable screen area, so CSS 100%/100vh cannot render under the real
         * status bar or gesture navigation region.
         */
        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val bars = insets.getInsets(
                WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout()
            )
            val ime = insets.getInsets(WindowInsetsCompat.Type.ime())
            /*
             * Keep the WebView below the real status bar and above the IME.
             * maxOf() avoids double-counting the gesture/navigation inset when
             * the keyboard is visible. The child WebView is laid out inside
             * this padded root, so CSS 100%/flex automatically follows the
             * visible Android viewport.
             */
            view.setPadding(
                bars.left,
                bars.top,
                bars.right,
                maxOf(bars.bottom, ime.bottom),
            )
            insets
        }
        ViewCompat.requestApplyInsets(root)

        bridge = PrototypeBridge(
            webView = webView,
            store = store,
            checkUpdates = { updateManager.checkForUpdates(force = true) },
            startVoiceInput = { requestId -> startVoiceInput(requestId) },
            startAttachmentPicker = { requestId, kind -> startAttachmentPicker(requestId, kind) },
            openBrowser = { url -> openBrowser(url) },
            openBrowserWithText = { url, text -> openBrowser(url, text) },
        )
        webView.addJavascriptInterface(bridge, "KissneNativeTransport")
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
        val installStamp = packageManager.getPackageInfo(packageName, 0).lastUpdateTime
        clearWebViewCacheAfterUpgrade(installStamp)
        webView.loadUrl(
            embeddedWebAssetEntryUrl(BuildConfig.VERSION_CODE, installStamp)
        )
        webView.postDelayed({ updateManager.checkForUpdates() }, 1_500)
    }

    private fun openBrowser(url: String?, text: String? = null) {
        startActivity(Intent(this, BrowserActivity::class.java).apply {
            url?.takeIf { it.isNotBlank() }?.let { putExtra(BrowserActivity.EXTRA_URL, it) }
            text?.takeIf { it.isNotBlank() }?.let { putExtra(BrowserActivity.EXTRA_TEXT, it) }
        })
    }

    private fun startAttachmentPicker(requestId: String, rawKind: String) {
        val kind = if (rawKind == "photo") "photo" else "file"
        pendingAttachmentRequestId?.takeIf { it != requestId }?.let { previous ->
            if (::bridge.isInitialized) {
                bridge.resolveNative(
                    previous,
                    false,
                    JSONObject().put("status", 0).put("error", "attachment_picker_replaced"),
                )
            }
        }
        pendingAttachmentRequestId = requestId
        pendingAttachmentKind = kind
        attachmentPicker.launch(if (kind == "photo") arrayOf("image/*") else arrayOf("*/*"))
    }

    private fun readAndUploadAttachment(requestId: String, kind: String, uri: Uri) {
        Thread {
            try {
                val name = queryDisplayName(uri).takeIf { it.isNotBlank() }
                    ?: if (kind == "photo") "photo" else "file"
                val mime = contentResolver.getType(uri)?.takeIf { it.isNotBlank() }
                    ?: "application/octet-stream"
                val size = queryAttachmentSize(uri)
                if (::bridge.isInitialized) {
                    bridge.notifyAttachmentSelected(requestId, kind, name, mime, size)
                }
                val bytes = readAttachmentBytes(uri, 20 * 1024 * 1024)
                if (::bridge.isInitialized) {
                    val attachmentId = "local-attachment-" + java.util.UUID.randomUUID().toString()
                    bridge.emitAttachmentSelected(attachmentId, kind, name, mime, bytes.size)
                    bridge.uploadPickedAttachment(requestId, attachmentId, kind, name, mime, bytes)
                }
            } catch (error: Throwable) {
                if (::bridge.isInitialized) {
                    bridge.resolveNative(
                        requestId,
                        false,
                        JSONObject().put("status", 0)
                            .put("error", error.message ?: "attachment_read_failed"),
                    )
                }
            }
        }.start()
    }

    private fun queryDisplayName(uri: Uri): String {
        return try {
            contentResolver.query(
                uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null,
            )?.use { cursor ->
                if (cursor.moveToFirst()) cursor.getString(0).orEmpty() else ""
            }.orEmpty()
        } catch (_: Throwable) {
            ""
        }
    }

    private fun queryAttachmentSize(uri: Uri): Long {
        return try {
            contentResolver.query(
                uri, arrayOf(OpenableColumns.SIZE), null, null, null,
            )?.use { cursor ->
                val index = cursor.getColumnIndex(OpenableColumns.SIZE)
                if (index >= 0 && cursor.moveToFirst() && !cursor.isNull(index)) cursor.getLong(index) else -1L
            } ?: -1L
        } catch (_: Throwable) {
            -1L
        }
    }

    private fun readAttachmentBytes(uri: Uri, maxBytes: Int): ByteArray {
        val input = contentResolver.openInputStream(uri)
            ?: throw IllegalStateException("attachment_open_failed")
        return input.use { stream ->
            val out = ByteArrayOutputStream()
            val buffer = ByteArray(64 * 1024)
            var total = 0
            while (true) {
                val read = stream.read(buffer)
                if (read < 0) break
                total += read
                if (total > maxBytes) throw IllegalArgumentException("attachment_too_large")
                out.write(buffer, 0, read)
            }
            out.toByteArray()
        }
    }

    private fun startVoiceInput(requestId: String) {
        pendingVoiceRequestId?.takeIf { it != requestId }?.let { previous ->
            finishVoiceRequest(
                previous,
                false,
                JSONObject().put("status", 0).put("error", "voice_input_replaced"),
            )
        }
        pendingVoiceRequestId = requestId

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
            == PackageManager.PERMISSION_GRANTED
        ) {
            beginVoiceRecognition(requestId)
        } else {
            recordAudioPermission.launch(Manifest.permission.RECORD_AUDIO)
        }
    }

    private fun beginVoiceRecognition(requestId: String) {
        if (pendingVoiceRequestId != requestId) return
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            finishVoiceRequest(
                requestId,
                false,
                JSONObject().put("status", 0).put("error", "speech_recognition_unavailable"),
            )
            return
        }

        speechRecognizer?.destroy()
        val recognizer = SpeechRecognizer.createSpeechRecognizer(this)
        speechRecognizer = recognizer
        recognizer.setRecognitionListener(object : RecognitionListener {
            override fun onReadyForSpeech(params: Bundle?) = Unit
            override fun onBeginningOfSpeech() = Unit
            override fun onRmsChanged(rmsdB: Float) = Unit
            override fun onBufferReceived(buffer: ByteArray?) = Unit
            override fun onEndOfSpeech() = Unit
            override fun onPartialResults(partialResults: Bundle?) = Unit
            override fun onEvent(eventType: Int, params: Bundle?) = Unit

            override fun onError(error: Int) {
                val code = when (error) {
                    SpeechRecognizer.ERROR_AUDIO -> "speech_audio_error"
                    SpeechRecognizer.ERROR_CLIENT -> "speech_client_error"
                    SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "microphone_permission_denied"
                    SpeechRecognizer.ERROR_NETWORK,
                    SpeechRecognizer.ERROR_NETWORK_TIMEOUT -> "speech_network_error"
                    SpeechRecognizer.ERROR_NO_MATCH -> "speech_no_match"
                    SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> "speech_recognizer_busy"
                    SpeechRecognizer.ERROR_SERVER -> "speech_server_error"
                    SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "speech_timeout"
                    else -> "speech_recognition_error"
                }
                finishVoiceRequest(
                    requestId,
                    false,
                    JSONObject().put("status", 0).put("error", code),
                )
            }

            override fun onResults(results: Bundle?) {
                val text = results
                    ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    ?.firstOrNull { it.isNotBlank() }
                    .orEmpty()
                if (text.isBlank()) {
                    finishVoiceRequest(
                        requestId,
                        false,
                        JSONObject().put("status", 0).put("error", "speech_no_match"),
                    )
                    return
                }
                finishVoiceRequest(
                    requestId,
                    true,
                    JSONObject().put("text", text),
                )
            }
        })

        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(
                RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                RecognizerIntent.LANGUAGE_MODEL_FREE_FORM,
            )
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.getDefault().toLanguageTag())
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
        }
        try {
            recognizer.startListening(intent)
        } catch (error: Throwable) {
            finishVoiceRequest(
                requestId,
                false,
                JSONObject().put("status", 0)
                    .put("error", error.message ?: "speech_recognition_error"),
            )
        }
    }

    private fun finishVoiceRequest(requestId: String, ok: Boolean, payload: JSONObject) {
        if (pendingVoiceRequestId == requestId) pendingVoiceRequestId = null
        val recognizer = speechRecognizer
        speechRecognizer = null
        recognizer?.destroy()
        if (::bridge.isInitialized) bridge.resolveNative(requestId, ok, payload)
    }

    private fun clearWebViewCacheAfterUpgrade(currentInstallStamp: Long) {
        val prefs = getSharedPreferences("kissne_webview", MODE_PRIVATE)
        val versionKey = "asset_version_code"
        val installKey = "asset_install_stamp"
        val previousVersionCode = prefs.getInt(versionKey, 0)
        val previousInstallStamp = prefs.getLong(installKey, 0L)
        val currentVersionCode = BuildConfig.VERSION_CODE

        if (shouldRefreshEmbeddedWebAssets(
                previousVersionCode,
                currentVersionCode,
                previousInstallStamp,
                currentInstallStamp,
            )
        ) {
            webView.clearCache(true)
            webView.clearHistory()
        }
        if (previousVersionCode != currentVersionCode || previousInstallStamp != currentInstallStamp) {
            prefs.edit()
                .putInt(versionKey, currentVersionCode)
                .putLong(installKey, currentInstallStamp)
                .apply()
        }
    }

    override fun onResume() {
        super.onResume()
        if (::updateManager.isInitialized) updateManager.onResume()
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (::webView.isInitialized && webView.canGoBack()) webView.goBack() else super.onBackPressed()
    }

    override fun onDestroy() {
        pendingAttachmentRequestId = null
        pendingAttachmentKind = null
        pendingVoiceRequestId = null
        speechRecognizer?.destroy()
        speechRecognizer = null
        if (::updateManager.isInitialized) updateManager.close()
        if (::bridge.isInitialized) bridge.close()
        if (::webView.isInitialized) {
            webView.removeJavascriptInterface("KissneNativeTransport")
            webView.stopLoading()
            webView.destroy()
        }
        super.onDestroy()
    }
}


internal fun shouldRefreshEmbeddedWebAssets(
    previousVersionCode: Int,
    currentVersionCode: Int,
    previousInstallStamp: Long,
    currentInstallStamp: Long,
): Boolean {
    if (previousVersionCode == 0 || previousInstallStamp == 0L) return false
    return previousVersionCode != currentVersionCode || previousInstallStamp != currentInstallStamp
}


internal fun embeddedWebAssetEntryUrl(versionCode: Int, installStamp: Long): String =
    "https://appassets.androidplatform.net/assets/index.html?native=1&appVersion=" +
        versionCode

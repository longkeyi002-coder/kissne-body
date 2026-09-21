package com.kissne.mobile

import android.annotation.SuppressLint
import android.os.Bundle
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.webkit.WebViewAssetLoader

class MainActivity : AppCompatActivity() {
    private lateinit var webView: WebView
    private lateinit var bridge: PrototypeBridge
    private lateinit var updateManager: UpdateManager

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val store = MobileSessionStore(this)
        updateManager = UpdateManager(this)
        val assetLoader = WebViewAssetLoader.Builder()
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(this))
            .build()

        webView = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
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

        ViewCompat.setOnApplyWindowInsetsListener(webView) { view, insets ->
            val bars = insets.getInsets(
                WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout()
            )
            view.setPadding(0, bars.top, 0, bars.bottom)
            insets
        }
        ViewCompat.requestApplyInsets(webView)

        bridge = PrototypeBridge(webView, store) {
            updateManager.checkForUpdates()
        }
        webView.addJavascriptInterface(bridge, "KissneNativeTransport")
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
        setContentView(webView)
        webView.loadUrl("https://appassets.androidplatform.net/assets/index.html?native=1")
        webView.postDelayed({ updateManager.checkForUpdates() }, 1_500)
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

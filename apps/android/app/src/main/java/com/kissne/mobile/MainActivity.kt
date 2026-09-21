package com.kissne.mobile

import android.annotation.SuppressLint
import android.graphics.Color
import android.os.Bundle
import android.view.ViewGroup
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.webkit.WebViewAssetLoader

class MainActivity : AppCompatActivity() {
    private lateinit var webView: WebView
    private lateinit var bridge: PrototypeBridge
    private lateinit var updateManager: UpdateManager

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

        val store = MobileSessionStore(this)
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

        bridge = PrototypeBridge(webView, store) {
            updateManager.checkForUpdates(force = true)
        }
        webView.addJavascriptInterface(bridge, "KissneNativeTransport")
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
        webView.loadUrl(
            "https://appassets.androidplatform.net/assets/index.html?native=1#/welcome?state=animate"
        )
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

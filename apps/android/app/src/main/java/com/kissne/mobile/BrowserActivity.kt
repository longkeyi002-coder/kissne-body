package com.kissne.mobile

import android.annotation.SuppressLint
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import org.json.JSONObject
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.EditorInfo
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat

/**
 * Isolated external-web surface for Kissne.
 *
 * Deliberately does NOT expose KissneNativeTransport or any JavascriptInterface
 * to remote pages. Site adapters can later use origin-scoped AndroidX WebKit
 * messaging without granting arbitrary pages access to the Kissne bridge.
 */
class BrowserActivity : AppCompatActivity() {
    private lateinit var webView: WebView
    private lateinit var address: EditText
    private lateinit var progress: ProgressBar

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        window.statusBarColor = Color.TRANSPARENT
        window.navigationBarColor = Color.TRANSPARENT

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.WHITE)
        }
        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val bars = insets.getInsets(
                WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout()
            )
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            insets
        }

        val top = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(8, 6, 8, 6)
        }
        fun navButton(label: String, action: () -> Unit): TextView = TextView(this).apply {
            text = label
            textSize = 22f
            gravity = Gravity.CENTER
            setPadding(12, 8, 12, 8)
            setOnClickListener { action() }
        }
        top.addView(navButton("‹") { if (webView.canGoBack()) webView.goBack() else finish() })

        address = EditText(this).apply {
            isSingleLine = true
            textSize = 13f
            hint = "搜索或输入网址"
            imeOptions = EditorInfo.IME_ACTION_GO
            setSelectAllOnFocus(true)
            setOnEditorActionListener { _, actionId, _ ->
                if (actionId == EditorInfo.IME_ACTION_GO) {
                    loadInput(text.toString())
                    clearFocus()
                    true
                } else false
            }
        }
        top.addView(address, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        top.addView(navButton("↻") { webView.reload() })

        progress = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 100
            visibility = View.GONE
        }

        webView = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.databaseEnabled = true
            settings.useWideViewPort = true
            settings.loadWithOverviewMode = false
            settings.setSupportZoom(true)
            settings.builtInZoomControls = true
            settings.displayZoomControls = false
            settings.allowFileAccess = false
            settings.allowContentAccess = true
            settings.mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            settings.javaScriptCanOpenWindowsAutomatically = false
            settings.setSupportMultipleWindows(false)
            CookieManager.getInstance().setAcceptCookie(true)
            CookieManager.getInstance().setAcceptThirdPartyCookies(this, true)
            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                    val scheme = request.url.scheme?.lowercase()
                    return if (scheme == "https" || scheme == "http") {
                        false
                    } else {
                        true
                    }
                }

                override fun onPageFinished(view: WebView, url: String) {
                    address.setText(url)
                    CookieManager.getInstance().flush()
                    if (isDeepSeek(url)) injectDeepSeekAdapter(view)
                }
            }
            webChromeClient = object : WebChromeClient() {
                override fun onProgressChanged(view: WebView, newProgress: Int) {
                    progress.progress = newProgress
                    progress.visibility = if (newProgress in 1..99) View.VISIBLE else View.GONE
                    if (view.url != null && !address.hasFocus()) address.setText(view.url)
                }
            }
        }

        root.addView(top, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        root.addView(progress, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 3))
        root.addView(webView, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        setContentView(root)
        ViewCompat.requestApplyInsets(root)

        val initial = intent.getStringExtra(EXTRA_URL)?.takeIf { it.isNotBlank() } ?: DEEPSEEK_URL
        webView.loadUrl(normalizeUrl(initial))
    }

    private fun loadInput(raw: String) {
        val value = raw.trim()
        if (value.isBlank()) return
        val url = when {
            value.startsWith("https://", true) || value.startsWith("http://", true) -> value
            value.contains('.') && !value.contains(' ') -> "https://$value"
            else -> "https://www.google.com/search?q=" + Uri.encode(value)
        }
        webView.loadUrl(url)
    }

    private fun isDeepSeek(url: String): Boolean =
        runCatching { Uri.parse(url).host?.lowercase() == "chat.deepseek.com" }.getOrDefault(false)

    private fun injectDeepSeekAdapter(view: WebView) {
        val pending = intent.getStringExtra(EXTRA_TEXT)?.takeIf { it.isNotBlank() }
        val payload = JSONObject.quote(pending ?: "")
        val script = """
            (() => {
              if (window.__kissneDeepSeekAdapter) return;
              const findComposer = () => {
                const editable = [...document.querySelectorAll('[contenteditable="true"]')]
                  .find(el => el.offsetParent !== null);
                return editable || [...document.querySelectorAll('textarea')]
                  .find(el => el.offsetParent !== null) || null;
              };
              const setText = (text) => {
                const el = findComposer();
                if (!el) return false;
                el.focus();
                if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
                  const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
                  const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                  if (setter) setter.call(el, text); else el.value = text;
                  el.dispatchEvent(new Event('input', { bubbles: true }));
                  el.dispatchEvent(new Event('change', { bubbles: true }));
                } else {
                  el.textContent = text;
                  el.dispatchEvent(new InputEvent('input', {
                    bubbles: true, inputType: 'insertText', data: text
                  }));
                }
                return true;
              };
              window.__kissneDeepSeekAdapter = { findComposer, setText };
              const pending = $payload;
              if (pending) {
                let tries = 0;
                const timer = setInterval(() => {
                  tries += 1;
                  if (setText(pending) || tries >= 40) clearInterval(timer);
                }, 250);
              }
            })();
        """.trimIndent()
        view.evaluateJavascript(script, null)
    }

    private fun normalizeUrl(raw: String): String =
        if (raw.startsWith("https://", true) || raw.startsWith("http://", true)) raw
        else "https://$raw"

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (::webView.isInitialized && webView.canGoBack()) webView.goBack() else super.onBackPressed()
    }

    override fun onPause() {
        if (::webView.isInitialized) {
            webView.onPause()
            CookieManager.getInstance().flush()
        }
        super.onPause()
    }

    override fun onResume() {
        super.onResume()
        if (::webView.isInitialized) webView.onResume()
    }

    override fun onDestroy() {
        if (::webView.isInitialized) {
            (webView.parent as? ViewGroup)?.removeView(webView)
            webView.destroy()
        }
        super.onDestroy()
    }

    companion object {
        const val EXTRA_URL = "url"
        const val EXTRA_TEXT = "text"
        const val DEEPSEEK_URL = "https://chat.deepseek.com/"
    }
}

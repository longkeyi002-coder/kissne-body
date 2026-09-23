package com.kissne.mobile

import android.annotation.SuppressLint
import androidx.appcompat.app.AlertDialog
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import androidx.activity.OnBackPressedCallback
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
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature

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
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (::webView.isInitialized && webView.canGoBack()) webView.goBack() else finish()
            }
        })
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
        top.addView(navButton("⌕") { runBrowserAgentRead() })
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
                    return scheme != "https"
                }

                override fun onPageFinished(view: WebView, url: String) {
                    address.setText(url)
                    CookieManager.getInstance().flush()
                    val site = BrowserAgent.siteId(url)
                    view.evaluateJavascript(BrowserAgent.readOnlyBootstrap(site), null)
                    if (site == "deepseek") injectDeepSeekAdapter(view)
                    if (site == "chatgpt") injectChatGptAdapter(view)
                }
            }
            webChromeClient = object : WebChromeClient() {
                override fun onProgressChanged(view: WebView, newProgress: Int) {
                    this@BrowserActivity.progress.progress = newProgress
                    this@BrowserActivity.progress.visibility = if (newProgress in 1..99) View.VISIBLE else View.GONE
                    if (view.url != null && !address.hasFocus()) address.setText(view.url)
                }
            }
        }

        root.addView(top, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        root.addView(progress, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 3))
        root.addView(webView, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        setContentView(root)
        ViewCompat.requestApplyInsets(root)

        installWebAiCommandBridge()
        val initial = intent.getStringExtra(EXTRA_URL)?.takeIf { it.isNotBlank() } ?: DEEPSEEK_URL
        webView.loadUrl(normalizeUrl(initial))
    }

    private fun installWebAiCommandBridge() {
        if (!WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER)) return
        WebViewCompat.addWebMessageListener(
            webView,
            "KissneBrowserAgent",
            setOf("https://chat.deepseek.com", "https://chatgpt.com")
        ) { _, message, sourceOrigin, isMainFrame, _ ->
            if (!isMainFrame) return@addWebMessageListener
            val command = BrowserAgent.parseCommand(message.data) ?: return@addWebMessageListener
            val host = sourceOrigin.host?.lowercase()
            if (host != "chat.deepseek.com" && host != "chatgpt.com") return@addWebMessageListener
            runOnUiThread { executeBrowserAgent(command.action, command.query, command.url, true) }
        }
    }

    private fun deliverBrowserAgentResult(result: String) {
        val encoded = JSONObject.quote(result)
        webView.evaluateJavascript(
            "window.dispatchEvent(new CustomEvent('kissne-browser-agent-result',{detail:$encoded}));",
            null
        )
    }

    private fun executeBrowserAgent(
        action: String,
        query: String? = null,
        requestedUrl: String? = null,
        returnToWebAi: Boolean = false,
    ) {
        val decision = BrowserAgent.decide(action, requestedUrl ?: webView.url, query)
        if (decision.requiresConfirmation) {
            AlertDialog.Builder(this)
                .setTitle("确认网页操作")
                .setMessage("此操作可能修改外部网站内容：" + decision.command.action + "。确认后才会执行。")
                .setNegativeButton("取消", null)
                .setPositiveButton("确认") { _, _ ->
                    Toast.makeText(this, "该写操作执行器尚未启用", Toast.LENGTH_SHORT).show()
                }
                .show()
            return
        }
        val command = decision.command
        if (command.action == "open") {
            val target = command.url
            if (BrowserAgent.isAllowedHttpUrl(target)) {
                webView.loadUrl(target!!)
                if (returnToWebAi) deliverBrowserAgentResult(BrowserAgent.resultEnvelope(true, command.action))
            } else if (returnToWebAi) deliverBrowserAgentResult(BrowserAgent.resultEnvelope(false, command.action, error = "invalid_url"))
            return
        }
        if (command.action == "back") {
            if (webView.canGoBack()) webView.goBack()
            if (returnToWebAi) deliverBrowserAgentResult(BrowserAgent.resultEnvelope(true, command.action))
            return
        }
        if (command.action == "forward") {
            if (webView.canGoForward()) webView.goForward()
            if (returnToWebAi) deliverBrowserAgentResult(BrowserAgent.resultEnvelope(true, command.action))
            return
        }
        webView.evaluateJavascript(BrowserAgent.readOnlyCommandScript(command)) { raw ->
            val result = decodeJsResult(raw)
            if (returnToWebAi) deliverBrowserAgentResult(BrowserAgent.resultEnvelope(true, command.action, payload = result))
            Toast.makeText(this, "BrowserAgent 操作完成", Toast.LENGTH_SHORT).show()
        }
    }

    private fun runBrowserAgentRead() {
        if (!::webView.isInitialized) return
        val command = BrowserAgent.Command(action = "read", risk = BrowserAgent.Risk.READ_ONLY)
        webView.evaluateJavascript(BrowserAgent.readOnlyCommandScript(command)) { raw ->
            val result = decodeJsResult(raw)
            if (result.isBlank() || result == "null") {
                Toast.makeText(this, "当前页面暂无可读取内容", Toast.LENGTH_SHORT).show()
            } else {
                val preview = runCatching {
                    val obj = JSONObject(result)
                    obj.optString("text").trim().take(120)
                }.getOrDefault("")
                Toast.makeText(
                    this,
                    if (preview.isBlank()) "BrowserAgent 已读取当前页面" else preview,
                    Toast.LENGTH_LONG
                ).show()
            }
        }
    }

    private fun decodeJsResult(raw: String?): String {
        if (raw.isNullOrBlank() || raw == "null") return ""
        return runCatching { org.json.JSONTokener(raw).nextValue() as? String ?: raw }.getOrDefault(raw)
    }

    private fun loadInput(raw: String) {
        val value = raw.trim()
        if (value.isBlank()) return
        val url = when {
            value.startsWith("https://", true) -> value
            value.startsWith("http://", true) -> "https://" + value.substringAfter("://")
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

    private fun injectChatGptAdapter(view: WebView) {
        val pending = intent.getStringExtra(EXTRA_TEXT)?.takeIf { it.isNotBlank() }
        val payload = JSONObject.quote(pending ?: "")
        val script = """
            (() => {
              if (window.__kissneChatGptAdapter) return;
              const findComposer = () =>
                document.querySelector('#prompt-textarea') ||
                [...document.querySelectorAll('[contenteditable="true"], textarea')]
                  .find(el => el.offsetParent !== null) || null;
              const setText = (text) => {
                const el = findComposer();
                if (!el) return false;
                el.focus();
                if (el.tagName === 'TEXTAREA') {
                  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
                  if (setter) setter.call(el, text); else el.value = text;
                  el.dispatchEvent(new Event('input', { bubbles: true }));
                } else {
                  el.textContent = text;
                  el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
                }
                return true;
              };
              window.__kissneChatGptAdapter = { findComposer, setText };
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
        if (raw.startsWith("https://", true)) raw
        else if (raw.startsWith("http://", true)) "https://" + raw.substringAfter("://")
        else "https://$raw"

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

package com.kissne.mobile

import android.content.Intent
import android.content.ClipboardManager
import android.graphics.drawable.GradientDrawable
import android.widget.FrameLayout
import android.widget.ScrollView
import org.json.JSONArray
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
    private lateinit var pages: FrameLayout
    private val tabs = linkedMapOf<String, WebView>()
    private val tabButtons = linkedMapOf<String, TextView>()
    private var activeTab = ""
    private var lastPageTab = "search"
    private var bookmarksView: View? = null
    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
    private fun rounded(color: Int) = GradientDrawable().apply { setColor(color); cornerRadius = dp(18).toFloat() }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (activeTab == "bookmarks") { switchTab(lastPageTab); return }
                if (::webView.isInitialized && webView.canGoBack()) webView.goBack() else finish()
            }
        })
        window.statusBarColor = Color.TRANSPARENT
        window.navigationBarColor = Color.TRANSPARENT

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.rgb(248, 249, 253))
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
            setPadding(dp(10), dp(8), dp(10), dp(8))
        }
        fun navButton(label: String, action: () -> Unit): TextView = TextView(this).apply {
            text = label
            textSize = 16f
            setTextColor(Color.rgb(55, 65, 90))
            gravity = Gravity.CENTER
            setPadding(dp(12), dp(10), dp(12), dp(10))
            setOnClickListener { action() }
        }
        top.addView(navButton("‹") { if (webView.canGoBack()) webView.goBack() else finish() })

        address = EditText(this).apply {
            isSingleLine = true
            textSize = 13f
            hint = "搜索或输入网址"
            imeOptions = EditorInfo.IME_ACTION_GO
            setSelectAllOnFocus(true)
            background = rounded(Color.WHITE)
            setPadding(dp(12), dp(10), dp(12), dp(10))
            setOnEditorActionListener { _, actionId, _ ->
                if (actionId == EditorInfo.IME_ACTION_GO) {
                    loadInput(text.toString())
                    clearFocus()
                    true
                } else false
            }
        }
        top.addView(address, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        top.addView(navButton("回传") { returnContent() })
        top.addView(navButton("↻") { webView.reload() })

        progress = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 100
            visibility = View.GONE
        }

        pages = FrameLayout(this)
        val shortcuts = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(dp(8), dp(4), dp(8), dp(8)) }
        listOf("chatgpt" to "GPT", "deepseek" to "DeepSeek", "search" to "搜索", "bookmarks" to "收藏").forEach { (id, label) ->
            val button = navButton(label) { if (id == "bookmarks") showBookmarks() else switchTab(id) }
            button.textSize = 14f
            shortcuts.addView(button, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)); tabButtons[id] = button
        }
        val actions = LinearLayout(this).apply { gravity = Gravity.END }
        actions.addView(navButton("收藏此页") { saveBookmark() })

        root.addView(top, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        root.addView(progress, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 3))
        root.addView(shortcuts)
        root.addView(pages, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        root.addView(actions)
        setContentView(root)
        ViewCompat.requestApplyInsets(root)

        val initial = intent.getStringExtra(EXTRA_URL)?.takeIf { it.isNotBlank() } ?: DEEPSEEK_URL
        val firstTab = BrowserAgent.siteId(initial).takeIf { it == "chatgpt" || it == "deepseek" } ?: "search"
        switchTab(firstTab, normalizeUrl(initial))
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun createTabWebView(): WebView {
        return WebView(this).apply {
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
                    if (::webView.isInitialized && view === webView && activeTab != "bookmarks") address.setText(url)
                    CookieManager.getInstance().flush()
                    val site = BrowserAgent.siteId(url)
                    view.evaluateJavascript(BrowserAgent.readOnlyBootstrap(site), null)
                    if (site == "deepseek") injectDeepSeekAdapter(view)
                    if (site == "chatgpt") injectChatGptAdapter(view)
                }
            }
            webChromeClient = object : WebChromeClient() {
                override fun onProgressChanged(view: WebView, newProgress: Int) {
                    if (!::webView.isInitialized || view !== webView || activeTab == "bookmarks") return
                    this@BrowserActivity.progress.progress = newProgress
                    this@BrowserActivity.progress.visibility = if (newProgress in 1..99) View.VISIBLE else View.GONE
                    if (view.url != null && !address.hasFocus()) address.setText(view.url)
                }
            }
        }

    }
    private fun paintTabs() { tabButtons.forEach { (id, button) -> button.background = rounded(if (id == activeTab) Color.rgb(228, 232, 245) else Color.TRANSPARENT) } }
    private fun switchTab(id: String, initialUrl: String? = null) {
        if (::webView.isInitialized) webView.onPause()
        bookmarksView?.visibility = View.GONE; tabs.values.forEach { it.visibility = View.GONE }
        activeTab = id; lastPageTab = id
        webView = tabs.getOrPut(id) {
            createTabWebView().also { view ->
                pages.addView(view, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
                installWebAiCommandBridge(view)
                view.loadUrl(initialUrl ?: when (id) { "chatgpt" -> "https://chatgpt.com/"; "deepseek" -> DEEPSEEK_URL; else -> "https://www.google.com/" })
            }
        }
        webView.visibility = View.VISIBLE; webView.onResume(); address.setText(webView.url ?: initialUrl.orEmpty()); progress.visibility = View.GONE; paintTabs()
    }
    private fun savedBookmarks(): JSONArray = try { JSONArray(getSharedPreferences("browser-bookmarks", MODE_PRIVATE).getString("pages", "[]")) } catch (_: Throwable) { JSONArray() }
    private fun saveBookmark() {
        if (activeTab == "bookmarks") return
        val url = webView.url ?: return
        if (Uri.parse(url).scheme != "https") return
        val saved = savedBookmarks()
        val next = JSONArray().put(JSONObject().put("url", url).put("title", webView.title ?: url))
        for (i in 0 until saved.length()) { val row = saved.optJSONObject(i) ?: continue; if (row.optString("url") != url && next.length() < 100) next.put(row) }
        getSharedPreferences("browser-bookmarks", MODE_PRIVATE).edit().putString("pages", next.toString()).apply(); Toast.makeText(this, "已收藏", Toast.LENGTH_SHORT).show()
    }
    private fun showBookmarks() {
        webView.onPause(); tabs.values.forEach { it.visibility = View.GONE }; bookmarksView?.let { pages.removeView(it) }
        activeTab = "bookmarks"; paintTabs(); progress.visibility = View.GONE
        val entries = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(16), dp(12), dp(16), dp(12)) }
        val saved = savedBookmarks()
        if (saved.length() == 0) entries.addView(TextView(this).apply { text = "收藏的网页会出现在这里"; setPadding(0, dp(20), 0, dp(20)) })
        for (i in 0 until saved.length()) {
            val row = saved.optJSONObject(i) ?: continue
            entries.addView(TextView(this).apply {
                text = row.optString("title") + "\n" + row.optString("url"); textSize = 15f; setPadding(dp(12), dp(14), dp(12), dp(14))
                setOnClickListener { switchTab("search"); webView.loadUrl(row.optString("url")) }
                setOnLongClickListener {
                    AlertDialog.Builder(this@BrowserActivity).setMessage("删除这条收藏？").setNegativeButton("取消", null).setPositiveButton("删除") { _, _ ->
                        val remaining = JSONArray(); for (j in 0 until saved.length()) if (j != i) remaining.put(saved.get(j))
                        getSharedPreferences("browser-bookmarks", MODE_PRIVATE).edit().putString("pages", remaining.toString()).apply(); showBookmarks()
                    }.show(); true
                }
            })
        }
        bookmarksView = ScrollView(this).apply { addView(entries) }
        bookmarksView?.let { pages.addView(it, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)) }
    }
    private fun returnContent() {
        if (activeTab == "bookmarks") return
        val sourceView = webView
        val sourceUrl = sourceView.url.orEmpty()
        val sourceTitle = sourceView.title.orEmpty()
        sourceView.evaluateJavascript("String(window.getSelection()?.toString() || '')") { raw ->
            val selected = decodeJsResult(raw).trim()
            if (selected.isNotEmpty()) previewReturn(selected, sourceUrl, sourceTitle)
            else AlertDialog.Builder(this).setTitle("回传到 Kissne").setItems(arrayOf("粘贴已复制的回答", "手动填写")) { _, choice ->
                val clipboard = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
                val text = if (choice == 0) clipboard.primaryClip?.getItemAt(0)?.coerceToText(this)?.toString().orEmpty() else ""
                previewReturn(text, sourceUrl, sourceTitle)
            }.setNegativeButton("取消", null).show()
        }
    }
    private fun previewReturn(content: String, sourceUrl: String, sourceTitle: String) {
        val input = EditText(this).apply { setText(content); minLines = 4; maxLines = 12; setPadding(dp(16), dp(12), dp(16), dp(12)) }
        AlertDialog.Builder(this).setTitle("回传预览").setView(input).setNegativeButton("取消", null).setPositiveButton("带回聊天") { _, _ ->
            val text = input.text.toString().trim()
            if (text.isNotEmpty()) {
                setResult(RESULT_OK, Intent().putExtra(EXTRA_TEXT, text).putExtra(EXTRA_URL, sourceUrl).putExtra(EXTRA_TITLE, sourceTitle).putExtra(EXTRA_SESSION, intent.getStringExtra(EXTRA_SESSION))); finish()
            }
        }.show()
    }
    private fun installWebAiCommandBridge(view: WebView) {
        if (!WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER)) return
        WebViewCompat.addWebMessageListener(
            view,
            "KissneBrowserAgent",
            setOf("https://chat.deepseek.com", "https://chatgpt.com")
        ) { _, message, sourceOrigin, isMainFrame, _ ->
            if (!isMainFrame || !::webView.isInitialized || view !== webView || activeTab == "bookmarks") return@addWebMessageListener
            val command = BrowserAgent.parseCommand(message.data ?: return@addWebMessageListener) ?: return@addWebMessageListener
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
        if (activeTab == "bookmarks") switchTab("search")
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
                if (String(el.value ?? el.textContent ?? '').trim()) return false;
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
              const browserAgent = {
                run: (command) => {
                  if (!window.KissneBrowserAgent?.postMessage) return false;
                  window.KissneBrowserAgent.postMessage(JSON.stringify(command || {}));
                  return true;
                },
                onResult: (handler) => window.addEventListener('kissne-browser-agent-result', e => handler(e.detail))
              };
              window.__kissneDeepSeekAdapter = { findComposer, setText, browserAgent };
              const pending = $payload;
              if (pending) {
                let tries = 0;
                const timer = setInterval(() => {
                  tries += 1;
                  if (setText(pending)) {
                    clearInterval(timer);
                    window.__kissneTransferApplied = true;
                  } else if (tries >= 40) clearInterval(timer);
                }, 250);
              }
            })();
        """.trimIndent()
        applyTransferScript(view, script)
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
                if (String(el.value ?? el.textContent ?? '').trim()) return false;
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
              const browserAgent = {
                run: (command) => {
                  if (!window.KissneBrowserAgent?.postMessage) return false;
                  window.KissneBrowserAgent.postMessage(JSON.stringify(command || {}));
                  return true;
                },
                onResult: (handler) => window.addEventListener('kissne-browser-agent-result', e => handler(e.detail))
              };
              window.__kissneChatGptAdapter = { findComposer, setText, browserAgent };
              const pending = $payload;
              if (pending) {
                let tries = 0;
                const timer = setInterval(() => {
                  tries += 1;
                  if (setText(pending)) {
                    clearInterval(timer);
                    window.__kissneTransferApplied = true;
                  } else if (tries >= 40) clearInterval(timer);
                }, 250);
              }
            })();
        """.trimIndent()
        applyTransferScript(view, script)
    }

    private fun applyTransferScript(view: WebView, script: String) {
        val expectedText = intent.getStringExtra(EXTRA_TEXT)
        val pageUrl = view.url
        view.evaluateJavascript(script, null)
        if (expectedText.isNullOrBlank()) return
        var attempts = 0
        val check = object : Runnable {
            override fun run() {
                if (isFinishing || isDestroyed || view.url != pageUrl) return
                view.evaluateJavascript("Boolean(window.__kissneTransferApplied)") { applied ->
                    if (applied == "true" && intent.getStringExtra(EXTRA_TEXT) == expectedText) {
                        intent.removeExtra(EXTRA_TEXT)
                    } else if (++attempts < 45) view.postDelayed(this, 250)
                }
            }
        }
        view.postDelayed(check, 300)
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
            tabs.values.forEach { view -> (view.parent as? ViewGroup)?.removeView(view); view.destroy() }
            tabs.clear()
        }
        super.onDestroy()
    }

    companion object {
        const val EXTRA_URL = "url"
        const val EXTRA_TEXT = "text"
        const val EXTRA_TITLE = "title"
        const val EXTRA_SESSION = "session_id"
        const val DEEPSEEK_URL = "https://chat.deepseek.com/"
    }
}

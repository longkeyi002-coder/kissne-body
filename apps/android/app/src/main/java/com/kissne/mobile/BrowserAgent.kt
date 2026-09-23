package com.kissne.mobile

import android.net.Uri

/**
 * Small, explicit command contract for temporary Web-AI/browser assistance.
 * Read-only commands may run directly. Mutating commands must be confirmed by
 * the user before execution and are not auto-executed by this layer.
 */
object BrowserAgent {
    enum class Risk { READ_ONLY, WRITE }

    data class Command(
        val action: String,
        val url: String? = null,
        val query: String? = null,
        val risk: Risk = Risk.READ_ONLY,
    )

    fun classify(action: String): Risk = when (action.lowercase()) {
        "open", "search", "read", "scroll", "back", "forward", "refresh" -> Risk.READ_ONLY
        else -> Risk.WRITE
    }

    fun isAllowedHttpUrl(raw: String?): Boolean {
        val uri = runCatching { Uri.parse(raw ?: "") }.getOrNull() ?: return false
        return uri.scheme?.lowercase() == "https" && !uri.host.isNullOrBlank()
    }

    fun siteId(raw: String?): String {
        val host = runCatching { Uri.parse(raw ?: "").host?.lowercase() }.getOrNull() ?: return "generic"
        return when {
            host == "github.com" || host.endsWith(".github.com") -> "github"
            host == "xiaohongshu.com" || host.endsWith(".xiaohongshu.com") -> "xiaohongshu"
            host == "chat.deepseek.com" -> "deepseek"
            host == "chatgpt.com" || host.endsWith(".chatgpt.com") -> "chatgpt"
            else -> "generic"
        }
    }

    fun readOnlyBootstrap(site: String): String = when (site) {
        "github" -> """
            (() => {
              window.__kissneSiteAdapter = {
                site: 'github',
                read: () => ({
                  title: document.title,
                  url: location.href,
                  text: (document.querySelector('main') || document.body).innerText.slice(0, 24000)
                }),
                search: (q) => {
                  const box = document.querySelector('input[name="q"], input[data-target*="query"], input[type="search"]');
                  if (!box) return false;
                  box.focus(); box.value = q; box.dispatchEvent(new Event('input', {bubbles:true}));
                  return true;
                }
              };
            })();
        """.trimIndent()
        "xiaohongshu" -> """
            (() => {
              window.__kissneSiteAdapter = {
                site: 'xiaohongshu',
                read: () => ({
                  title: document.title,
                  url: location.href,
                  text: (document.querySelector('main') || document.body).innerText.slice(0, 24000)
                }),
                search: (q) => {
                  const box = [...document.querySelectorAll('input')].find(el =>
                    el.type === 'search' || /搜索/.test(el.placeholder || ''));
                  if (!box) return false;
                  box.focus(); box.value = q; box.dispatchEvent(new Event('input', {bubbles:true}));
                  return true;
                }
              };
            })();
        """.trimIndent()
        else -> """
            (() => {
              window.__kissneSiteAdapter = {
                site: 'generic',
                read: () => ({title: document.title, url: location.href, text: document.body.innerText.slice(0, 24000)})
              };
            })();
        """.trimIndent()
    }
}

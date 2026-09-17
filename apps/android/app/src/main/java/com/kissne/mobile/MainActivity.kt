package com.kissne.mobile

import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

class MainActivity : AppCompatActivity() {
    private val executor = Executors.newSingleThreadExecutor()
    private lateinit var store: MobileSessionStore
    private lateinit var client: MobileTransportClient
    private lateinit var transcript: TextView
    private lateinit var status: TextView
    private lateinit var input: EditText
    private lateinit var sendButton: Button
    private lateinit var cancelButton: Button
    private lateinit var pairCode: EditText
    private lateinit var pairButton: Button
    private val polling = AtomicBoolean(false)
    private val state = ChatState()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = MobileSessionStore(this)
        client = MobileTransportClient("https://yeqingxu.cyou/mobile/", { store.deviceToken })
        setContentView(buildUi())
        if (store.deviceToken.isNullOrBlank()) showPairing() else bootstrap()
    }

    private fun buildUi(): View {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 24, 24, 16)
        }
        status = TextView(this)
        pairCode = EditText(this).apply { hint = "输入一次性配对码"; visibility = View.GONE }
        pairButton = Button(this).apply {
            text = "配对"
            visibility = View.GONE
            setOnClickListener { pair() }
        }
        transcript = TextView(this).apply { textSize = 16f }
        input = EditText(this).apply { hint = "输入消息"; minLines = 1; maxLines = 4 }
        sendButton = Button(this).apply { text = "发送"; setOnClickListener { sendMessage() } }
        cancelButton = Button(this).apply {
            text = "停止"; visibility = View.GONE; setOnClickListener { cancelTurn() }
        }
        val actions = LinearLayout(this).apply {
            gravity = Gravity.END
            addView(cancelButton); addView(sendButton)
        }
        root.addView(status); root.addView(pairCode); root.addView(pairButton)
        root.addView(ScrollView(this).apply {
            addView(transcript)
            layoutParams = LinearLayout.LayoutParams(-1, 0, 1f)
        })
        root.addView(input); root.addView(actions)
        return root
    }

    private fun showPairing() {
        status.text = "需要设备配对"
        pairCode.visibility = View.VISIBLE
        pairButton.visibility = View.VISIBLE
        input.visibility = View.GONE
        sendButton.visibility = View.GONE
    }

    private fun pair() {
        val code = pairCode.text.toString().trim()
        if (code.isEmpty()) return
        pairButton.isEnabled = false
        executor.execute {
            try {
                store.saveToken(client.pair(code))
                runOnUiThread {
                    pairCode.visibility = View.GONE
                    pairButton.visibility = View.GONE
                    input.visibility = View.VISIBLE
                    sendButton.visibility = View.VISIBLE
                    bootstrap()
                }
            } catch (error: Exception) {
                runOnUiThread {
                    status.text = "配对失败：" + (error.message ?: "未知错误")
                    pairButton.isEnabled = true
                }
            }
        }
    }

    private fun bootstrap() {
        state.beginBootstrap()
        render()
        executor.execute {
            try {
                val result = client.bootstrap()
                state.bootstrapLoaded(result)
                runOnUiThread { render() }
                if (result.bound) startPolling()
            } catch (error: Exception) {
                state.failed()
                runOnUiThread { status.text = "未连接：" + (error.message ?: "未知错误"); render() }
            }
        }
    }

    private fun sendMessage() {
        val text = input.text.toString().trim()
        if (text.isEmpty() || state.status == ChatState.Status.SENDING) return
        input.setText("")
        val messageId = "android-" + System.currentTimeMillis()
        state.messages += HistoryMessage("user", text, messageId)
        state.sent(SendReceipt(messageId, "", false))
        render()
        executor.execute {
            try {
                val receipt = client.send(messageId, text)
                state.sent(receipt)
                runOnUiThread { render() }
            } catch (error: Exception) {
                state.failed()
                runOnUiThread { status.text = "发送失败：" + (error.message ?: "未知错误"); render() }
            }
        }
    }

    private fun startPolling() {
        if (!polling.compareAndSet(false, true)) return
        executor.execute {
            while (polling.get() && !isFinishing) {
                try {
                    val events = client.poll(store.cursor)
                    for (event in events) {
                        when (event.type) {
                            MobileEventType.PENDING -> state.pending(event.turnId)
                            MobileEventType.DELTA -> state.delta(event.text)
                            MobileEventType.COMPLETED -> state.completed(event.text)
                            MobileEventType.CANCELLED -> state.cancelled()
                            MobileEventType.ERROR -> state.failed()
                        }
                        store.cursor = maxOf(store.cursor, event.seq)
                        runOnUiThread { render() }
                    }
                    if (events.isNotEmpty()) client.ack(store.cursor)
                    Thread.sleep(1200)
                } catch (error: InterruptedException) {
                    break
                } catch (error: Exception) {
                    state.failed()
                    runOnUiThread { status.text = "连接中断，重试中…" }
                    try { Thread.sleep(2500) } catch (_: InterruptedException) { break }
                }
            }
            polling.set(false)
        }
    }

    private fun cancelTurn() {
        val turnId = state.activeTurnId ?: return
        executor.execute {
            try {
                client.cancel(turnId)
                state.cancelled()
                runOnUiThread { render() }
            } catch (error: Exception) {
                state.failed()
                runOnUiThread { status.text = "停止失败：" + (error.message ?: "未知错误") }
            }
        }
    }

    private fun render() {
        transcript.text = buildString {
            state.messages.forEach {
                append(if (it.role == "user") "我：" else "Agent：")
                    .append(it.text).append("\n\n")
            }
            if (state.draftText.isNotBlank()) append("Agent（生成中）：").append(state.draftText)
        }
        status.text = when (state.status) {
            ChatState.Status.LOADING -> "加载当前 Conversation…"
            ChatState.Status.READY -> "已连接"
            ChatState.Status.SENDING -> "等待回复…"
            ChatState.Status.STREAMING -> "正在生成…"
            ChatState.Status.ERROR -> "连接异常"
            ChatState.Status.DISCONNECTED -> "未连接"
        }
        cancelButton.visibility = if (state.activeTurnId != null) View.VISIBLE else View.GONE
        sendButton.isEnabled = state.status == ChatState.Status.READY
    }

    override fun onDestroy() {
        polling.set(false)
        executor.shutdownNow()
        super.onDestroy()
    }
}

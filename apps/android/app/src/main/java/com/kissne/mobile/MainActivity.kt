package com.kissne.mobile

import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
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
    private val requestExecutor = Executors.newSingleThreadExecutor()
    private val pollExecutor = Executors.newSingleThreadExecutor()
    private lateinit var store: MobileSessionStore
    private lateinit var client: MobileTransportClient
    private lateinit var conversationTitle: TextView
    private lateinit var messageList: LinearLayout
    private lateinit var status: TextView
    private lateinit var input: EditText
    private lateinit var sendButton: Button
    private lateinit var cancelButton: Button
    private lateinit var pairCode: EditText
    private lateinit var pairButton: Button
    private val polling = AtomicBoolean(false)
    private val state = ChatState()
    private var currentConversation = "当前 Conversation"

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
            setBackgroundColor(Color.rgb(247, 251, 255))
            setPadding(20, 18, 20, 12)
        }

        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        val avatar = TextView(this).apply {
            text = "叶"
            textSize = 22f
            gravity = Gravity.CENTER
            setTextColor(Color.WHITE)
            background = rounded(Color.rgb(102, 156, 126), 22)
        }
        header.addView(avatar, LinearLayout.LayoutParams(52, 52))
        val titles = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(14, 0, 0, 0)
        }
        titles.addView(TextView(this).apply {
            text = "叶青栩"
            textSize = 21f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.rgb(34, 49, 61))
        })
        conversationTitle = TextView(this).apply {
            text = currentConversation
            textSize = 12f
            setTextColor(Color.rgb(100, 120, 132))
        }
        titles.addView(conversationTitle)
        header.addView(titles, LinearLayout.LayoutParams(0, -2, 1f))
        root.addView(header)

        status = TextView(this).apply {
            textSize = 12f
            setTextColor(Color.rgb(100, 120, 132))
            setPadding(66, 6, 0, 8)
        }
        root.addView(status)

        pairCode = EditText(this).apply {
            hint = "输入一次性配对码"
            visibility = View.GONE
        }
        pairButton = Button(this).apply {
            text = "连接叶青栩"
            visibility = View.GONE
            setOnClickListener { pair() }
        }
        root.addView(pairCode)
        root.addView(pairButton)

        val scroll = ScrollView(this).apply {
            isFillViewport = true
        }
        messageList = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, 8, 0, 12)
        }
        scroll.addView(messageList)
        root.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))

        input = EditText(this).apply {
            hint = "和叶青栩说点什么…"
            minLines = 1
            maxLines = 4
            setPadding(18, 10, 18, 10)
            background = rounded(Color.WHITE, 24)
        }
        sendButton = Button(this).apply {
            text = "发送"
            setOnClickListener { sendMessage() }
        }
        cancelButton = Button(this).apply {
            text = "停止"
            visibility = View.GONE
            setOnClickListener { cancelTurn() }
        }
        val actions = LinearLayout(this).apply {
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, 8, 0, 0)
            addView(input, LinearLayout.LayoutParams(0, -2, 1f))
            addView(cancelButton)
            addView(sendButton)
        }
        root.addView(actions)
        return root
    }

    private fun rounded(color: Int, radius: Int): GradientDrawable =
        GradientDrawable().apply { setColor(color); cornerRadius = radius.toFloat() }

    private fun showPairing() {
        status.text = "第一次使用：输入一次性配对码"
        pairCode.visibility = View.VISIBLE
        pairButton.visibility = View.VISIBLE
        input.visibility = View.GONE
        sendButton.visibility = View.GONE
        messageList.removeAllViews()
    }

    private fun pair() {
        val code = pairCode.text.toString().trim()
        if (code.isEmpty()) return
        pairButton.isEnabled = false
        requestExecutor.execute {
            try {
                store.saveToken(client.pair(code, store.installationId()))
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
        requestExecutor.execute {
            try {
                val result = client.bootstrap()
                currentConversation = result.conversationTitle ?: "当前 Conversation"
                state.bootstrapLoaded(result)
                runOnUiThread { render() }
                if (result.bound) startPolling()
            } catch (error: Exception) {
                state.failed()
                runOnUiThread {
                    status.text = "连接失败：" + (error.message ?: "未知错误")
                    render()
                }
            }
        }
    }

    private fun sendMessage() {
        val text = input.text.toString().trim()
        if (text.isEmpty() || state.status == ChatState.Status.SENDING) return
        input.setText("")
        val retrying = state.status == ChatState.Status.ERROR && state.lastOutbound != null
        val outbound = state.lastOutbound ?: OutboundMessage("android-" + System.currentTimeMillis(), text)
        if (!retrying) {
            state.messages += HistoryMessage("user", text, outbound.messageId)
            state.remember(outbound)
        }
        state.sent(SendReceipt(outbound.messageId, "", false))
        render()
        requestExecutor.execute {
            try {
                val receipt = client.send(outbound.messageId, outbound.text)
                state.sent(receipt)
                runOnUiThread { render() }
            } catch (error: Exception) {
                state.failed()
                runOnUiThread { render() }
            }
        }
    }

    private fun startPolling() {
        if (!polling.compareAndSet(false, true)) return
        pollExecutor.execute {
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
                } catch (_: InterruptedException) {
                    break
                } catch (_: Exception) {
                    state.failed()
                    runOnUiThread { render() }
                    try { Thread.sleep(2500) } catch (_: InterruptedException) { break }
                }
            }
            polling.set(false)
        }
    }

    private fun cancelTurn() {
        val turnId = state.activeTurnId ?: return
        requestExecutor.execute {
            try {
                client.cancel(turnId)
                state.cancelled()
                runOnUiThread { render() }
            } catch (_: Exception) {
                state.failed()
                runOnUiThread { render() }
            }
        }
    }

    private fun render() {
        conversationTitle.text = currentConversation
        messageList.removeAllViews()
        state.messages.forEach { message ->
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(16, 10, 16, 10)
                background = rounded(
                    if (message.role == "user") Color.rgb(224, 241, 232) else Color.WHITE,
                    18
                )
            }
            row.addView(TextView(this).apply {
                text = if (message.role == "user") "我" else "叶青栩"
                textSize = 12f
                typeface = Typeface.DEFAULT_BOLD
                setTextColor(Color.rgb(91, 120, 104))
            })
            row.addView(TextView(this).apply {
                text = message.text
                textSize = 16f
                setTextColor(Color.rgb(36, 48, 56))
                setPadding(0, 4, 0, 0)
            })
            val params = LinearLayout.LayoutParams(-1, -2)
            params.setMargins(0, 6, 0, 6)
            messageList.addView(row, params)
        }
        if (state.draftText.isNotBlank()) {
            val draft = TextView(this).apply {
                text = "叶青栩（正在回复）\n" + state.draftText
                textSize = 16f
                setTextColor(Color.rgb(57, 81, 68))
                setPadding(16, 14, 16, 14)
                background = rounded(Color.rgb(235, 247, 239), 18)
            }
            messageList.addView(draft)
        }
        status.text = when (state.status) {
            ChatState.Status.LOADING -> "正在打开当前 Conversation…"
            ChatState.Status.READY -> "已连接到叶青栩"
            ChatState.Status.SENDING -> "叶青栩正在思考…"
            ChatState.Status.STREAMING -> "叶青栩正在回复…"
            ChatState.Status.ERROR -> "连接异常，可重试"
            ChatState.Status.DISCONNECTED -> "未连接"
        }
        cancelButton.visibility = if (state.activeTurnId != null) View.VISIBLE else View.GONE
        sendButton.isEnabled = state.status == ChatState.Status.READY ||
            (state.status == ChatState.Status.ERROR && state.lastOutbound != null)
        sendButton.text = if (state.status == ChatState.Status.ERROR && state.lastOutbound != null) "重试" else "发送"
    }

    override fun onDestroy() {
        polling.set(false)
        requestExecutor.shutdownNow()
        pollExecutor.shutdownNow()
        super.onDestroy()
    }
}

package com.kissne.mobile

import android.app.Activity
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

class ChatUi(
    private val activity: Activity,
    private val onPair: () -> Unit,
    private val onSend: () -> Unit,
    private val onCancel: () -> Unit
) {
    val root: View
    val status = TextView(activity)
    val pairingCode = EditText(activity)
    val transcript = TextView(activity)
    val input = EditText(activity)
    private val pairButton = Button(activity)
    private val sendButton = Button(activity)
    private val cancelButton = Button(activity)

    init {
        pairingCode.hint = "一次性配对码"
        pairButton.text = "配对"
        pairButton.setOnClickListener { onPair() }
        input.hint = "输入消息"
        input.maxLines = 4
        sendButton.text = "发送"
        sendButton.setOnClickListener { onSend() }
        cancelButton.text = "停止"
        cancelButton.visibility = View.GONE
        cancelButton.setOnClickListener { onCancel() }

        val actions = LinearLayout(activity)
        actions.addView(cancelButton)
        actions.addView(sendButton)

        root = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 24, 24, 16)
            addView(status)
            addView(pairingCode)
            addView(pairButton)
            addView(
                ScrollView(activity).apply {
                    addView(transcript)
                    layoutParams = LinearLayout.LayoutParams(-1, 0, 1f)
                }
            )
            addView(input)
            addView(actions)
        }
    }

    fun showPairing(message: String) {
        status.text = message
        pairingCode.visibility = View.VISIBLE
        pairButton.visibility = View.VISIBLE
        input.visibility = View.GONE
        sendButton.visibility = View.GONE
        cancelButton.visibility = View.GONE
    }

    fun showChat() {
        pairingCode.visibility = View.GONE
        pairButton.visibility = View.GONE
        input.visibility = View.VISIBLE
        sendButton.visibility = View.VISIBLE
    }

    fun pairingCodeValue(): String = pairingCode.text.toString().trim()

    fun consumeInput(): String {
        val text = input.text.toString().trim()
        input.setText("")
        return text
    }

    fun render(state: ChatState) {
        transcript.text = buildString {
            state.messages.forEach {
                append(if (it.role == "user") "我：" else "Agent：")
                append(it.text)
                append("\n\n")
            }
            if (state.draftText.isNotBlank()) {
                append("Agent（生成中）：")
                append(state.draftText)
            }
        }
        status.text = when (state.status) {
            ChatState.Status.LOADING -> "加载当前 Conversation…"
            ChatState.Status.READY -> "已连接"
            ChatState.Status.SENDING -> "等待回复…"
            ChatState.Status.STREAMING -> "正在生成…"
            ChatState.Status.ERROR -> "连接异常"
            ChatState.Status.DISCONNECTED -> "未绑定当前 Conversation，请重新配对或等待绑定"
        }
        cancelButton.visibility =
            if (state.activeTurnId != null) View.VISIBLE else View.GONE
        sendButton.isEnabled =
            state.status == ChatState.Status.READY ||
                (state.status == ChatState.Status.ERROR && state.lastOutbound != null)
        sendButton.text =
            if (state.status == ChatState.Status.ERROR && state.lastOutbound != null) {
                "重试"
            } else {
                "发送"
            }
    }
}

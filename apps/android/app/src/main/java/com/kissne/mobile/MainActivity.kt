package com.kissne.mobile

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

class MainActivity : AppCompatActivity() {
    private val requestExecutor = Executors.newSingleThreadExecutor()
    private val pollExecutor = Executors.newSingleThreadExecutor()
    private lateinit var store: MobileSessionStore
    private lateinit var client: MobileTransportClient
    private lateinit var ui: ChatUi
    private val polling = AtomicBoolean(false)
    private val state = ChatState()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = MobileSessionStore(this)
        client = MobileTransportClient(
            baseUrl = BuildConfig.MOBILE_BASE_URL,
            tokenProvider = { store.deviceToken }
        )
        ui = ChatUi(this, ::pair, ::sendMessage, ::cancelTurn)
        setContentView(ui.root)

        if (store.deviceToken.isNullOrBlank()) {
            ui.showPairing("需要设备配对")
        } else {
            bootstrap()
        }
    }

    private fun pair() {
        val code = ui.pairingCodeValue()
        if (code.isEmpty()) return

        requestExecutor.execute {
            try {
                store.saveToken(client.pair(code, store.installationId()))
                runOnUiThread { bootstrap() }
            } catch (error: Exception) {
                runOnUiThread {
                    ui.showPairing("配对失败：${error.message ?: "未知错误"}")
                }
            }
        }
    }

    private fun bootstrap() {
        state.beginBootstrap()
        ui.showChat()
        ui.render(state)

        requestExecutor.execute {
            try {
                val result = client.bootstrap(store.cursor)
                if (result.coveredEventSeqs.isNotEmpty()) {
                    store.cursor = maxOf(store.cursor, result.coveredEventSeqs.max())
                    client.ack(store.cursor)
                }
                state.bootstrapLoaded(result)
                runOnUiThread {
                    if (result.bound) {
                        ui.showChat()
                        ui.render(state)
                        startPolling()
                    } else {
                        ui.showPairing("未绑定当前 Conversation，请重新配对或等待绑定")
                        ui.render(state)
                    }
                }
            } catch (error: Exception) {
                state.failed()
                runOnUiThread {
                    ui.showPairing("未连接：${error.message ?: "未知错误"}")
                    ui.render(state)
                }
            }
        }
    }

    private fun sendMessage() {
        val text = ui.consumeInput()
        val retrying = state.status == ChatState.Status.ERROR && state.lastOutbound != null
        if (text.isEmpty() && !retrying) return

        val outbound = state.lastOutbound
            ?: OutboundMessage("android-${System.currentTimeMillis()}", text)
        if (!retrying) {
            state.messages += HistoryMessage("user", outbound.text, outbound.messageId)
            state.remember(outbound)
        }
        state.sent(SendReceipt(outbound.messageId, "", false))
        ui.render(state)

        requestExecutor.execute {
            try {
                state.sent(client.send(outbound.messageId, outbound.text))
                runOnUiThread { ui.render(state) }
            } catch (_: Exception) {
                state.failed()
                runOnUiThread { ui.render(state) }
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
                        runOnUiThread { ui.render(state) }
                    }
                    if (events.isNotEmpty()) client.ack(store.cursor)
                    Thread.sleep(1200)
                } catch (_: InterruptedException) {
                    break
                } catch (_: Exception) {
                    state.failed()
                    runOnUiThread { ui.render(state) }
                    try {
                        Thread.sleep(2500)
                    } catch (_: InterruptedException) {
                        break
                    }
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
                runOnUiThread { ui.render(state) }
            } catch (_: Exception) {
                state.failed()
                runOnUiThread { ui.render(state) }
            }
        }
    }

    override fun onDestroy() {
        polling.set(false)
        requestExecutor.shutdownNow()
        pollExecutor.shutdownNow()
        super.onDestroy()
    }
}

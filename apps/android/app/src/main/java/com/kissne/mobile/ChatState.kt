package com.kissne.mobile

class ChatState {
    enum class Status { DISCONNECTED, LOADING, READY, SENDING, STREAMING, ERROR }
    var status = Status.DISCONNECTED
        private set
    var activeTurnId: String? = null
        private set
    var draftText = ""
        private set
    val messages = mutableListOf<HistoryMessage>()
    fun beginBootstrap() { status = Status.LOADING }
    fun bootstrapLoaded(result: Bootstrap) {
        messages.clear(); messages.addAll(result.history)
        activeTurnId = result.pendingTurnId
        status = if (result.bound) Status.READY else Status.ERROR
    }
    fun sent(receipt: SendReceipt) { activeTurnId = receipt.turnId; status = Status.SENDING }
    fun pending(turnId: String?) { activeTurnId = turnId ?: activeTurnId; status = Status.SENDING }
    fun delta(text: String?) { if (!text.isNullOrEmpty()) draftText += text; status = Status.STREAMING }
    fun completed(text: String?) {
        if (!text.isNullOrEmpty()) messages += HistoryMessage("assistant", text, null)
        draftText = ""; activeTurnId = null; status = Status.READY
    }
    fun cancelled() { draftText = ""; activeTurnId = null; status = Status.READY }
    fun failed() { status = Status.ERROR }
}

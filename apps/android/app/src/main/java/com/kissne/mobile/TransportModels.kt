package com.kissne.mobile

enum class MobileEventType(val wireName: String) {
    PENDING("pending"),
    DELTA("delta"),
    COMPLETED("completed"),
    CANCELLED("cancelled"),
    NOTICE("notice"),
    APPROVAL_REQUIRED("approval_required"),
    APPROVAL_RESOLVED("approval_resolved"),
    ERROR("error");

    companion object {
        fun fromWire(value: String?): MobileEventType =
            values().firstOrNull { it.wireName == value } ?: ERROR
    }
}

data class OutboundMessage(
    val messageId: String,
    val text: String
)

data class MobileEvent(
    val seq: Long,
    val type: MobileEventType,
    val turnId: String?,
    val messageId: String?,
    val replyTo: String?,
    val text: String?
)

data class HistoryMessage(
    val role: String,
    val text: String,
    val messageId: String?
)

data class Bootstrap(
    val bound: Boolean,
    val conversationId: String?,
    val conversationTitle: String?,
    val history: List<HistoryMessage>,
    val pendingTurnId: String?,
    val coveredEventSeqs: List<Long>
)

data class SendReceipt(
    val messageId: String,
    val turnId: String,
    val duplicate: Boolean
)

package com.kissne.mobile

internal enum class NotificationAction { START, STOP, IGNORE }

internal fun notificationAction(state: String, visible: Boolean): NotificationAction = when (state) {
    "working", "thinking", "tool", "pending" -> if (visible) NotificationAction.START else NotificationAction.IGNORE
    "ready", "idle", "completed", "cancelled", "error" -> NotificationAction.STOP
    else -> NotificationAction.IGNORE
}

internal fun isReplyPresentation(presentation: String): Boolean = presentation !in setOf(
    "hidden", "internal_notification", "reasoning", "thinking", "analysis", "commentary",
    "tool_progress", "tool_call", "tool_result",
)

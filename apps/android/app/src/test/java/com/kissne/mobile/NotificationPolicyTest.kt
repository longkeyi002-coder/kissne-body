package com.kissne.mobile

import org.junit.Assert.*
import org.junit.Test

class NotificationPolicyTest {
    @Test fun opening_idle_then_working_then_finishing_removes_the_status_notification() {
        assertEquals(NotificationAction.STOP, notificationAction("ready", true))
        assertEquals(NotificationAction.START, notificationAction("pending", true))
        assertEquals(NotificationAction.START, notificationAction("thinking", true))
        assertEquals(NotificationAction.STOP, notificationAction("completed", false))
        assertEquals(NotificationAction.STOP, notificationAction("cancelled", false))
        assertEquals(NotificationAction.STOP, notificationAction("error", true))
    }

    @Test fun unknown_and_background_hints_cannot_launch_a_foreground_service() {
        assertEquals(NotificationAction.IGNORE, notificationAction("working", false))
        assertEquals(NotificationAction.IGNORE, notificationAction("unknown", true))
    }

    @Test fun process_events_never_generate_reply_alerts() {
        for (presentation in listOf("reasoning", "commentary", "analysis", "tool_call", "tool_result", "hidden")) {
            assertFalse(isReplyPresentation(presentation))
        }
        assertTrue(isReplyPresentation("answer"))
        assertTrue(isReplyPresentation(""))
    }
}

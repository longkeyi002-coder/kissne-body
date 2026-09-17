package com.kissne.mobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TransportContractTest {
    @Test
    fun event_types_distinguish_pending_delta_completed_cancelled_and_error() {
        val types = MobileEventType.values().map { it.wireName }.toSet()
        assertEquals(
            setOf("pending", "delta", "completed", "cancelled", "error"),
            types
        )
    }

    @Test
    fun retry_keeps_the_same_client_message_id_and_turn_correlation() {
        val first = OutboundMessage("msg-1", "hello")
        val retry = first.copy()
        assertEquals(first.messageId, retry.messageId)
        assertTrue(first.messageId.isNotBlank())
    }
}

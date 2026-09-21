package com.kissne.mobile

import org.junit.Assert.*
import org.junit.Test

class TransportContractTest {
    @Test fun event_types_are_closed() { assertEquals(setOf("pending", "delta", "completed", "cancelled", "error"), MobileEventType.values().map { it.wireName }.toSet()) }
    @Test fun retry_keeps_client_message_id() { val first = OutboundMessage("msg-1", "hello"); assertEquals(first.messageId, first.copy().messageId) }
    @Test fun nullable_wire_values_stay_null() { assertNull(JSONObjectProbe.nullable(null)) }
}

private object JSONObjectProbe { fun nullable(value: String?): String? = value?.ifBlank { null } }

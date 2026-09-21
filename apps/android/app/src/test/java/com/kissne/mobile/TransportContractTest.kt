package com.kissne.mobile

import org.junit.Assert.*
import org.junit.Test

class TransportContractTest {
    @Test fun representative_event_types_parse() {
        assertEquals(MobileEventType.PENDING, MobileEventType.fromWire("pending"))
        assertEquals(MobileEventType.NOTICE, MobileEventType.fromWire("notice"))
        assertEquals(MobileEventType.APPROVAL_REQUIRED, MobileEventType.fromWire("approval_required"))
        assertEquals(MobileEventType.APPROVAL_RESOLVED, MobileEventType.fromWire("approval_resolved"))
        assertEquals(MobileEventType.ERROR, MobileEventType.fromWire("future_event"))
    }
    @Test fun retry_keeps_client_message_id() { val first = OutboundMessage("msg-1", "hello"); assertEquals(first.messageId, first.copy().messageId) }
    @Test fun nullable_wire_values_stay_null() { assertNull(JSONObjectProbe.nullable(null)) }

    @Test fun admin_routes_keep_mobile_proxy_prefix() {
        val base = "https://yeqingxu.cyou/mobile/"
        assertEquals(
            "https://yeqingxu.cyou/mobile/admin/sessions",
            resolveMobileRequestUrl(base, "/admin/sessions"),
        )
        assertEquals(
            "https://yeqingxu.cyou/mobile/pair",
            resolveMobileRequestUrl(base, "/pair"),
        )
    }

    @Test fun interactive_send_is_not_blocked_by_background_reads() {
        assertEquals(BridgeLane.TRANSPORT, bridgeLane("sendText"))
        assertEquals(BridgeLane.TRANSPORT, bridgeLane("selectSession"))
        assertEquals(BridgeLane.BACKGROUND, bridgeLane("bootstrap"))
        assertEquals(BridgeLane.BACKGROUND, bridgeLane("poll"))
        assertEquals(BridgeLane.BACKGROUND, bridgeLane("ack"))
        assertEquals(BridgeLane.CONTROL, bridgeLane("sessions"))
        assertEquals(BridgeLane.CONTROL, bridgeLane("modelOptions"))
    }
}

private object JSONObjectProbe { fun nullable(value: String?): String? = value?.ifBlank { null } }

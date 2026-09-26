package com.kissne.mobile

import org.junit.Assert.*
import org.junit.Test

class TransportContractTest {
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
        assertEquals(BridgeLane.TRANSPORT, bridgeLane("sendSticker"))
        assertEquals(BridgeLane.TRANSPORT, bridgeLane("selectSession"))
        assertEquals(BridgeLane.BACKGROUND, bridgeLane("bootstrap"))
        assertEquals(BridgeLane.BACKGROUND, bridgeLane("poll"))
        assertEquals(BridgeLane.BACKGROUND, bridgeLane("ack"))
        assertEquals(BridgeLane.CONTROL, bridgeLane("sessions"))
        assertEquals(BridgeLane.CONTROL, bridgeLane("deleteSession"))
        assertEquals(BridgeLane.CONTROL, bridgeLane("modelOptions"))
    }
    @Test fun attachment_kind_preserves_sticker_semantics() {
        assertEquals("photo", normalizeAttachmentKind("photo"))
        assertEquals("sticker", normalizeAttachmentKind("sticker"))
        assertEquals("file", normalizeAttachmentKind("file"))
        assertEquals("file", normalizeAttachmentKind("unknown"))
    }
    @Test fun history_request_scopes_and_encodes_selected_session() {
        assertEquals(
            "/history?limit=100&before=turn%3Aold%3Auser&session_id=session+with+space",
            historyRequestPath(500, "turn:old:user", "session with space"),
        )
    }

    @Test fun history_request_keeps_legacy_unscoped_shape_when_session_missing() {
        assertEquals("/history?limit=50", historyRequestPath(50, null, null))
    }
}

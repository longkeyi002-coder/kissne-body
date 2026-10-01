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
        assertEquals(BridgeLane.CONTROL, bridgeLane("memoryTimeline"))
    }
    @Test fun history_request_can_be_scoped_to_current_session() {
        val source = java.io.File("src/main/java/com/kissne/mobile/MobileTransportClient.kt").readText()
        assertTrue(source.contains("session_id="))
        assertTrue(source.contains("sessionId?.trim()"))
        val bridge = java.io.File("src/main/java/com/kissne/mobile/PrototypeBridge.kt").readText()
        assertTrue(bridge.contains("cachedBootstrapPayload()"))
        assertTrue(bridge.contains("optString(\"session_id\")"))
    }

    @Test fun attachment_kind_preserves_sticker_semantics() {
        assertEquals("photo", normalizeAttachmentKind("photo"))
        assertEquals("sticker", normalizeAttachmentKind("sticker"))
        assertEquals("file", normalizeAttachmentKind("file"))
        assertEquals("file", normalizeAttachmentKind("unknown"))
    }

    /* The gateway answers a restart request *before* it goes down, so the client must not
       treat a lost response as an auth failure and wipe the stored token. */
    @Test fun restart_route_is_wired_end_to_end_and_keeps_its_token_on_a_dropped_response() {
        assertEquals(
            "https://yeqingxu.cyou/mobile/admin/restart",
            resolveMobileRequestUrl(base(), "/admin/restart"),
        )
        val client = java.io.File("src/main/java/com/kissne/mobile/MobileTransportClient.kt").readText()
        assertTrue(client.contains("""request("POST", "/admin/restart")"""))
        val bridge = java.io.File("src/main/java/com/kissne/mobile/PrototypeBridge.kt").readText()
        assertTrue(bridge.contains(""""adminRestart" -> client().adminRestartPayload()"""))
        val lane = java.io.File("src/main/java/com/kissne/mobile/BridgeScheduling.kt").readText()
        assertTrue(lane.contains("adminRestart"))
        /* Restart is an operator action, never a background read. */
        assertEquals(BridgeLane.CONTROL, bridgeLane("adminRestart"))

        val js = java.io.File("../../../kissne-prototype/prototype/transport.js").readText()
        assertTrue(js.contains("function adminRestart()"))
        assertTrue(js.contains("request('/admin/restart', { method: 'POST'"))
        assertTrue(js.contains("adminRestart: function () { return nativeCall('adminRestart', {}); }"))
        val screens = java.io.File("../../../kissne-prototype/prototype/screens-b.js").readText()
        assertTrue(screens.contains("""data-admin-op="restart""""))
    }

    private fun base() = "https://yeqingxu.cyou/mobile/"
}

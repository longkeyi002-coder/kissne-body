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
    @Test fun reinstalling_same_version_must_refresh_embedded_web_assets() {
        assertTrue(shouldRefreshEmbeddedWebAssets(
            previousVersionCode = 26,
            currentVersionCode = 26,
            previousInstallStamp = 1000L,
            currentInstallStamp = 2000L,
        ))
    }

    @Test fun unchanged_install_must_not_refresh_embedded_web_assets() {
        assertFalse(shouldRefreshEmbeddedWebAssets(
            previousVersionCode = 26,
            currentVersionCode = 26,
            previousInstallStamp = 2000L,
            currentInstallStamp = 2000L,
        ))
    }

    @Test fun version_upgrade_still_refreshes_embedded_web_assets() {
        assertTrue(shouldRefreshEmbeddedWebAssets(
            previousVersionCode = 26,
            currentVersionCode = 27,
            previousInstallStamp = 2000L,
            currentInstallStamp = 3000L,
        ))
    }
    @Test fun first_install_does_not_need_stale_asset_cleanup() {
        assertFalse(shouldRefreshEmbeddedWebAssets(
            previousVersionCode = 0,
            currentVersionCode = 26,
            previousInstallStamp = 0L,
            currentInstallStamp = 2000L,
        ))
    }

    @Test fun same_version_with_same_install_stamp_does_not_clear_on_cold_start() {
        assertFalse(shouldRefreshEmbeddedWebAssets(
            previousVersionCode = 26,
            currentVersionCode = 26,
            previousInstallStamp = 2000L,
            currentInstallStamp = 2000L,
        ))
    }

    @Test fun downgrade_or_replaced_build_also_refreshes_assets() {
        assertTrue(shouldRefreshEmbeddedWebAssets(
            previousVersionCode = 27,
            currentVersionCode = 26,
            previousInstallStamp = 2000L,
            currentInstallStamp = 3000L,
        ))
    }
}

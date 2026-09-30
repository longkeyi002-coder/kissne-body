package com.kissne.mobile
import org.junit.Assert.*
import org.junit.Test

class ScreenFramePolicyTest {
    @Test fun stopped_paused_stale_and_inflight_frames_cannot_be_sent() {
        assertFalse(canShareScreenFrame(false, false, false, true, 0))
        assertFalse(canShareScreenFrame(true, true, false, true, 0))
        assertFalse(canShareScreenFrame(true, false, true, true, 0))
        assertFalse(canShareScreenFrame(true, false, false, false, 0))
        assertFalse(canShareScreenFrame(true, false, false, true, 6000))
        assertFalse(canShareScreenFrame(true, false, false, true, -1))
        assertTrue(canShareScreenFrame(true, false, false, true, 1500))
    }
}

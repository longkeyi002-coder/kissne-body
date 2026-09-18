package com.kissne.mobile
import org.junit.Assert.assertEquals
import org.junit.Test
class TransportModelsTest {
    @Test fun unknown_wire_event_is_safe_error() {
        assertEquals(MobileEventType.ERROR, MobileEventType.fromWire("future"))
    }
}

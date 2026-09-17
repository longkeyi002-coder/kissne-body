package com.kissne.mobile
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
class ChatStateTest {
    @Test fun pending_delta_completed_are_distinct_and_ordered() {
        val state = ChatState()
        state.pending("turn-1"); state.delta("hel")
        assertEquals(ChatState.Status.STREAMING, state.status)
        assertEquals("hel", state.draftText)
        state.completed("hello")
        assertEquals(ChatState.Status.READY, state.status)
        assertEquals(1, state.messages.size)
        assertTrue(state.activeTurnId == null)
    }
    @Test fun cancellation_closes_the_active_turn() {
        val state = ChatState(); state.pending("turn-1"); state.cancelled()
        assertEquals(ChatState.Status.READY, state.status)
        assertEquals(null, state.activeTurnId)
    }
}

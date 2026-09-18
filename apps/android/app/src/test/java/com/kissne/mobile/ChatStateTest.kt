package com.kissne.mobile

import org.junit.Assert.*
import org.junit.Test

class ChatStateTest {
    @Test fun bootstrap_does_not_replay_covered_events_as_history() {
        val state = ChatState()
        state.bootstrapLoaded(
            Bootstrap(
                true,
                "s",
                "k",
                listOf(HistoryMessage("assistant", "done", "turn-1")),
                null,
                listOf(4L)
            )
        )
        assertEquals(1, state.messages.size)
        assertEquals(ChatState.Status.READY, state.status)
    }

    @Test fun unbound_bootstrap_exposes_recovery_state_instead_of_generic_error() {
        val state = ChatState()
        state.bootstrapLoaded(Bootstrap(false, null, null, emptyList(), null, emptyList()))
        assertEquals(ChatState.Status.DISCONNECTED, state.status)
    }

    @Test fun delta_accumulates_and_completion_commits_one_assistant_message() {
        val state = ChatState()
        state.pending("turn-1")
        state.delta("Hel")
        state.delta("lo")
        state.completed(null)
        assertEquals(listOf("Hello"), state.messages.map { it.text })
        assertEquals(ChatState.Status.READY, state.status)
        assertNull(state.activeTurnId)
        assertEquals("", state.draftText)
    }

    @Test fun cancellation_clears_draft_and_active_turn() {
        val state = ChatState()
        state.pending("turn-1")
        state.delta("partial")
        state.cancelled()
        assertEquals("", state.draftText)
        assertNull(state.activeTurnId)
        assertEquals(ChatState.Status.READY, state.status)
    }

    @Test fun failed_send_preserves_outbound_for_retry_without_duplicate_history() {
        val state = ChatState()
        val outbound = OutboundMessage("m", "hello")
        state.remember(outbound)
        state.messages += HistoryMessage("user", outbound.text, outbound.messageId)
        state.failed()
        state.sent(SendReceipt(outbound.messageId, "", false))
        assertEquals(1, state.messages.count { it.messageId == outbound.messageId })
        assertEquals(outbound, state.lastOutbound)
    }
}

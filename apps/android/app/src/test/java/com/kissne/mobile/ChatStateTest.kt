package com.kissne.mobile

import org.junit.Assert.*
import org.junit.Test

class ChatStateTest {
    @Test fun bootstrap_does_not_replay_covered_events_as_history() {
        val state = ChatState(); state.bootstrapLoaded(Bootstrap(true, "s", "k", listOf(HistoryMessage("assistant", "done", "turn-1")), null, listOf(4L)))
        assertEquals(1, state.messages.size); assertEquals(ChatState.Status.READY, state.status)
    }
    @Test fun failed_send_preserves_outbound_for_retry() { val state = ChatState(); val outbound = OutboundMessage("m", "hello"); state.remember(outbound); state.failed(); assertEquals(outbound, state.lastOutbound) }
}

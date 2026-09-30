package com.kissne.mobile

internal enum class BridgeLane { TRANSPORT, BACKGROUND, CONTROL }

internal fun bridgeLane(action: String): BridgeLane =
    when (action) {
        // Background reads must never sit in front of an interactive send.
        "bootstrap", "poll", "ack" -> BridgeLane.BACKGROUND
        "toolsets", "history", "search", "modelOptions", "setModel", "sessions", "deleteSession", "memoryTimeline",
        "adminStatus", "adminMemory", "deleteAdminMemory", "adminSkills", "adminMcp", "adminMerge", "adminRollback", "adminDeployLog" -> BridgeLane.CONTROL
        else -> BridgeLane.TRANSPORT
    }

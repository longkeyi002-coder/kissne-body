package com.kissne.mobile

internal enum class BridgeLane { TRANSPORT, BACKGROUND, CONTROL }

internal fun bridgeLane(action: String): BridgeLane =
    when (action) {
        // Background reads must never sit in front of an interactive send.
        "bootstrap", "poll", "ack" -> BridgeLane.BACKGROUND
        "modelOptions", "setModel", "sessions",
        "adminStatus", "adminMerge", "adminRollback", "adminDeployLog" -> BridgeLane.CONTROL
        else -> BridgeLane.TRANSPORT
    }

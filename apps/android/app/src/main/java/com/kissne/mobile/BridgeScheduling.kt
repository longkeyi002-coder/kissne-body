package com.kissne.mobile

internal enum class BridgeLane { TRANSPORT, CONTROL }

internal fun bridgeLane(action: String): BridgeLane =
    when (action) {
        "modelOptions", "setModel", "sessions",
        "adminStatus", "adminMerge", "adminRollback", "adminDeployLog" -> BridgeLane.CONTROL
        else -> BridgeLane.TRANSPORT
    }

package com.kissne.mobile

internal fun canShareScreenFrame(active: Boolean, paused: Boolean, sending: Boolean, hasFrame: Boolean, frameAgeMs: Long): Boolean =
    active && !paused && !sending && hasFrame && frameAgeMs in 0..5000

"""Platform scope rules for configured toolsets."""

from typing import Set


# Toolsets without a restriction entry are available on every platform.
_TOOLSET_PLATFORM_RESTRICTIONS = {
    "discord": {"discord"},
    "discord_admin": {"discord"},
    # kissne's sticker tool renders markers the other channels cannot; paid for by kissne only.
    "kissne_mobile": {"kissne_mobile"},
}


def toolset_allowed_for_platform(ts_key: str, platform: str) -> bool:
    """Return whether ``ts_key`` is available on ``platform``."""
    allowed: Set[str] | None = _TOOLSET_PLATFORM_RESTRICTIONS.get(ts_key)
    return allowed is None or platform in allowed

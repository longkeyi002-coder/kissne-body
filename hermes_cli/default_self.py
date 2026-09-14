"""Default SELF.md template seeded into HERMES_HOME on first run."""

LEGACY_DEFAULT_SELF_MD = """# Current Self

No evolving self-description has been recorded yet.

<!--
Record current interests, opinions, preferences, habits, beliefs, and
self-understanding here. Keep full growth logs, hidden reasoning, and complete
conversation transcripts out of this file.

Kissne reads this file when a Session Snapshot is created and after /compress.
Ordinary turns keep the existing Snapshot instead of hot-reloading this file.
-->
"""

DEFAULT_SELF_MD = """# Current Self

No evolving self-description has been recorded yet.

## Editing guidance

Record current interests, opinions, preferences, habits, beliefs, and
self-understanding here. Keep full growth logs, hidden reasoning, and complete
conversation transcripts out of this file.

Kissne reads this file when a Session Snapshot is created and after /compress.
Ordinary turns keep the existing Snapshot instead of hot-reloading this file.
"""


def is_placeholder_self_md(content: str) -> bool:
    """Return whether *content* is one of Hermes' untouched SELF templates."""
    normalized = content.strip()
    return normalized in {
        DEFAULT_SELF_MD.strip(),
        LEGACY_DEFAULT_SELF_MD.strip(),
    }

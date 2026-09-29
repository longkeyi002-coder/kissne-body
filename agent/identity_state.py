"""KB1-IDENTITY-DEGRADED — the explicit runtime state of the identity slots.

``SOUL.md`` (the persona slot) and ``SELF.md`` (the self-state slot) can be
*absent*, an untouched **placeholder** (the auto-seeded default text), or a
**legacy installer template**.  Before this module the runtime read any of
those three as if it were the instance's own identity: the generic template
went into the prompt as "the persona" and nothing said the instance had no
personal identity at all.  A fresh home, a clone, an export or a restored
backup therefore masqueraded as a configured companion.

This module makes that condition a named, inspectable state instead of an
implicit fallback:

* :func:`soul_slot` / :func:`self_slot` classify one file's text into
  ``ok`` or ``degraded`` plus a reason (``missing`` / ``placeholder`` /
  ``legacy_template``);
* :class:`IdentityState` aggregates the slots and renders two explicit
  surfaces: ``notice`` (a prompt block naming the degraded slot and forbidding
  the generic persona from being presented as a personal identity) and
  ``warning`` (the one-line user-visible status).

Policy lives here (pure text classification + rendering); I/O lives in
``agent.prompt_builder`` and prompt wiring in ``agent.system_prompt``.  The
CI/release half of the same boundary is ``scripts/ci/check_soul_boundary.py``
(KB0-SOUL-GIT-GUARD) and shares the same two classifiers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional, Tuple

# ── status / reason vocabulary ──────────────────────────────────────────────
IDENTITY_OK = "ok"
IDENTITY_DEGRADED = "degraded"

REASON_MISSING = "missing"
REASON_PLACEHOLDER = "placeholder"
REASON_LEGACY_TEMPLATE = "legacy_template"

SOUL = "SOUL.md"
SELF = "SELF.md"

# Greppable marker: tests, logs and operator tooling key off this exact token.
IDENTITY_DEGRADED_MARKER = "KISSNE-IDENTITY-DEGRADED"

# Per-slot consequence: what the model must NOT do while the slot is degraded.
# The whole point of the ticket — the generic text may no longer be presented
# as this instance's own configured identity.
_CONSEQUENCE = {
    SOUL: (
        "This instance has NO personalized identity: the text above is the upstream default, not a "
        "configured persona. Never present it, or any persona, as this instance's own identity; if "
        "asked who you are, say plainly that the SOUL slot is degraded and why."
    ),
    SELF: (
        "This session has NO recorded self-state. Do not invent, imply or narrate a stored "
        "self-description, personal history or growth log for this instance."
    ),
}

_DETAIL = {
    (SOUL, REASON_MISSING): (
        "No SOUL.md exists at {path}; this instance has no personal identity file."
    ),
    (SOUL, REASON_PLACEHOLDER): (
        "SOUL.md at {path} is an untouched, auto-seeded default template — it carries no "
        "user-authored identity."
    ),
    (SOUL, REASON_LEGACY_TEMPLATE): (
        "SOUL.md at {path} matches a legacy installer template — it carries no user-authored "
        "identity."
    ),
    (SELF, REASON_MISSING): (
        "No SELF.md exists at {path}; no evolving self-description has been recorded."
    ),
    (SELF, REASON_PLACEHOLDER): (
        "SELF.md at {path} is an untouched default template — no evolving self-description has "
        "been recorded."
    ),
}


def _normalize(text: str) -> str:
    """Unify line endings, strip a leading BOM, trim outer whitespace."""
    return text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff").strip()


@dataclass(frozen=True)
class IdentitySlot:
    """One identity file's runtime classification. Pure value object."""

    name: str  # SOUL / SELF
    status: str  # ok / degraded
    reason: str = ""  # one of the REASON_* constants when degraded
    path: str = ""  # where the slot was read from (provenance for the notice)

    def __post_init__(self) -> None:
        if self.status == IDENTITY_DEGRADED and not self.reason:
            raise ValueError("a degraded identity slot must carry a reason")

    @property
    def degraded(self) -> bool:
        return self.status == IDENTITY_DEGRADED

    @property
    def tag(self) -> str:
        """``SOUL.md:legacy_template`` — the compact reason label."""
        return f"{self.name}:{self.reason}" if self.degraded else self.name

    @property
    def notice(self) -> str:
        """Prompt block that names the degraded slot, or ``""`` when healthy."""
        if not self.degraded:
            return ""
        here = self.path or "the active HERMES_HOME"
        detail = _DETAIL.get((self.name, self.reason), "").format(path=here)
        if not detail:  # unreachable for the shipped (name, reason) pairs
            detail = f"{self.name} at {here} is not a usable personal identity ({self.reason})."
        return (
            f"## Identity state: DEGRADED ({self.tag})\n"
            f"[{IDENTITY_DEGRADED_MARKER}] {detail}\n"
            f"{_CONSEQUENCE[self.name]}"
        )


@dataclass(frozen=True)
class IdentityState:
    """Aggregated identity-slot state for one prompt build."""

    slots: Tuple[IdentitySlot, ...] = field(default_factory=tuple)

    @property
    def degraded(self) -> bool:
        return any(slot.degraded for slot in self.slots)

    @property
    def reasons(self) -> Tuple[str, ...]:
        """Stable, de-duplicated ``<file>:<reason>`` tags of the degraded slots."""
        return tuple(dict.fromkeys(slot.tag for slot in self.slots if slot.degraded))

    def for_slot(self, name: str) -> Optional[IdentitySlot]:
        for slot in self.slots:
            if slot.name == name:
                return slot
        return None

    @property
    def notice(self) -> str:
        """All degraded slot notices, joined for prompt injection."""
        return "\n\n".join(slot.notice for slot in self.slots if slot.degraded)

    @property
    def warning(self) -> str:
        """One-line user-visible warning, or ``""`` when the identity is healthy."""
        if not self.degraded:
            return ""
        return (
            "identity degraded: "
            + ", ".join(self.reasons)
            + " — no personalized identity is active; the upstream default is in use"
        )

    def render(self) -> str:
        """Prompt representation: the notices, or ``""`` for a healthy identity."""
        return self.notice


def merge_slots(*slots: Optional[IdentitySlot]) -> IdentityState:
    """Build an :class:`IdentityState` from the slots actually observed (Nones dropped)."""
    return IdentityState(slots=tuple(slot for slot in slots if slot is not None))


def soul_slot(text: Optional[str], path: str = "") -> IdentitySlot:
    """Classify SOUL.md text: missing / legacy installer template / untouched default / ok.

    The two degraded templates are exactly the ones the KB0 boundary check
    refuses at the Git/CI/release edge (``is_legacy_template_soul`` plus the
    auto-seeded ``DEFAULT_SOUL_MD`` itself): known generic text carrying zero
    user intent.  Any deviation — a user typed a persona, even one character
    outside the scaffold comment — classifies as ``ok``.
    """
    raw = text or ""
    if not raw.strip():
        return IdentitySlot(SOUL, IDENTITY_DEGRADED, REASON_MISSING, path)
    from hermes_cli.default_soul import DEFAULT_SOUL_MD, is_legacy_template_soul

    if is_legacy_template_soul(raw):
        return IdentitySlot(SOUL, IDENTITY_DEGRADED, REASON_LEGACY_TEMPLATE, path)
    if _normalize(raw) == _normalize(DEFAULT_SOUL_MD):
        return IdentitySlot(SOUL, IDENTITY_DEGRADED, REASON_PLACEHOLDER, path)
    return IdentitySlot(SOUL, IDENTITY_OK, "", path)


def self_slot(text: Optional[str], path: str = "") -> IdentitySlot:
    """Classify SELF.md text: missing / untouched default template / ok.

    A SELF.md that a real instance grew into is ``ok``; the seeded default and
    the pre-Kissne HTML-comment generation
    (``hermes_cli.default_self.is_placeholder_self_md``) are ``placeholder``.
    """
    raw = text or ""
    if not raw.strip():
        return IdentitySlot(SELF, IDENTITY_DEGRADED, REASON_MISSING, path)
    from hermes_cli.default_self import is_placeholder_self_md

    if is_placeholder_self_md(raw):
        return IdentitySlot(SELF, IDENTITY_DEGRADED, REASON_PLACEHOLDER, path)
    return IdentitySlot(SELF, IDENTITY_OK, "", path)


def slot_for(name: str, text: Optional[str], path: str = "") -> IdentitySlot:
    """Dispatch to the classifier for *name* (``SOUL`` / ``SELF``)."""
    if name == SOUL:
        return soul_slot(text, path)
    if name == SELF:
        return self_slot(text, path)
    raise ValueError(f"unknown identity slot: {name!r}")


def degraded_slots(slots: Iterable[IdentitySlot]) -> Tuple[IdentitySlot, ...]:
    """The degraded subset, in input order."""
    return tuple(slot for slot in slots if slot.degraded)


__all__ = [
    "IDENTITY_DEGRADED",
    "IDENTITY_DEGRADED_MARKER",
    "IDENTITY_OK",
    "IdentitySlot",
    "IdentityState",
    "REASON_LEGACY_TEMPLATE",
    "REASON_MISSING",
    "REASON_PLACEHOLDER",
    "SELF",
    "SOUL",
    "degraded_slots",
    "merge_slots",
    "self_slot",
    "slot_for",
    "soul_slot",
]

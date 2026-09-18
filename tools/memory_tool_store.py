"""MemoryStore — bounded, file-backed curated memory (MEMORY.md / USER.md) plus the
whole-file SELF.md block, all served through one ``format_for_system_prompt`` chain.
Entries are joined by ``ENTRY_DELIMITER``; budgets are in chars (model-independent).
Module state that tests monkeypatch (``get_memory_dir``, ``fcntl``/``msvcrt``) stays
in ``tools.memory_tool`` and is read lazily."""

import logging
import os
import time
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from hermes_constants import get_hermes_home
from utils import atomic_write_text
from tools.threat_patterns import first_threat_message as _first_threat_message

logger = logging.getLogger("tools.memory_tool")

# Block header prefixes rendered by _render_block; agent/conversation_compression.py
# matches them to detect a leftover block for an emptied target — keep in lockstep.
MEMORY_BLOCK_HEADERS = {
    "memory": "MEMORY (your personal notes)", "user": "USER PROFILE (who the user is)",
    # SELF.md is an identity document, not an entry list; its own header keeps a
    # mis-routed target from rendering as (or being read as) the notes store.
    "self": "SELF (your evolving self-state)"}

# Targets backed by ONE whole-file document instead of a §-delimited entry list:
# never split into entries, never deduplicated, and never charged against a
# target's char budget (SELF must not eat MEMORY's 2,200-char room).
WHOLE_FILE_TARGETS = ("self",)
SELF_TARGET = "self"
SELF_MD_FILENAME = "SELF.md"

ENTRY_DELIMITER = "\n§\n"


def _scan_memory_content(content: str) -> Optional[str]:
    """Error string if *content* matches injection/exfil patterns. Strict scope:
    memory enters the system prompt, so a poisoned entry persists across sessions."""
    return _first_threat_message(content, scope="strict")


def _error(message: str, **extra) -> Dict[str, Any]:
    return {"success": False, "error": message, **extra}


def _drift_error(path: Path, bak_path: str) -> Dict[str, Any]:
    """External drift: the file wouldn't round-trip, so flushing would discard content."""
    return _error((
        f"Refusing to write {path.name}: file on disk has content that wouldn't round-trip "
        f"through the memory tool (likely added by the patch tool, a shell append, a manual edit, "
        f"or a concurrent session). A snapshot was saved to {bak_path}. Resolve the drift first — "
        f"either rewrite the file as a clean §-delimited list of entries, or move the extra "
        f"content out — then retry. This guard exists to prevent silent data loss (issue #26045)."
    ), drift_backup=bak_path, remediation=(
        "Open the .bak file, integrate the missing entries into the memory tool one at a time via "
        "memory(action=add, content=...), then remove or rewrite the original file to a clean state."))


def _read_failed_error(path: Path) -> Dict[str, Any]:
    """Existing-but-unreadable file: saving from an assumed-empty view would wipe it."""
    return _error(
        f"Refusing to write {path.name}: the file exists on disk but could not be read right now "
        f"(temporarily locked by another program, a permission change, invalid/corrupt text encoding, "
        f"or a filesystem error). Treating an unreadable file as empty and saving would wipe existing "
        f"memory, so the write is refused. Nothing was changed — retry in a moment.")


def _find_unique_match(entries: List[str], old_text: str) -> Tuple[Optional[int], bool]:
    """``(index, ambiguous)`` for entries containing *old_text*. Exact-duplicate
    matches are safe (first wins); distinct matches → ``(None, True)``."""
    matches = [i for i, e in enumerate(entries) if old_text in e]
    if len({entries[i] for i in matches}) > 1:
        return None, True
    return (matches[0] if matches else None), False


class MemoryStore:
    """Bounded curated memory with file persistence; one instance per AIAgent.
    ``_system_prompt_snapshot`` is frozen at load time (prefix-cache stable);
    ``memory_entries`` / ``user_entries`` are live state persisted to disk."""

    # Failed consolidation attempts (overflow / zero-match) allowed per turn before
    # a TERMINAL "save skipped" result, so a fragile replace/add can't loop the turn
    # to budget exhaustion and suppress the user's reply.
    # See #42405.
    _MAX_CONSOLIDATION_FAILURES_PER_TURN = 3

    def __init__(self, memory_char_limit: int = 2200, user_char_limit: int = 1375, *,
                 memory_enabled: bool = True, user_profile_enabled: bool = True):
        self.memory_entries: List[str] = []
        self.user_entries: List[str] = []
        # Whole-file state (SELF.md): raw file text, never an entry list.
        self.self_text: str = ""
        self.memory_char_limit, self.user_char_limit = memory_char_limit, user_char_limit
        self.memory_enabled, self.user_profile_enabled = memory_enabled, user_profile_enabled
        self._system_prompt_snapshot: Dict[str, str] = {"memory": "", "user": "", "self": ""}
        self._consolidation_failures = 0  # per turn; reset by reset_consolidation_failures()

    # Per-turn counter of failed at-capacity consolidation attempts; reset at each turn boundary by
    # reset_consolidation_failures() (#42405).
    def target_enabled(self, target: str) -> bool:
        if target in WHOLE_FILE_TARGETS:
            # SELF.md is not a memory/user store: it has no config flag and is
            # injected as its own block, so it stays available either way.
            return True
        return self.user_profile_enabled if target == "user" else self.memory_enabled

    def reset_consolidation_failures(self) -> None:
        """Call at turn start."""
        self._consolidation_failures = 0

    def _consolidation_failure(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Count a consolidation failure: under the per-turn cap return ``response``
        (it says how to retry); past it a TERMINAL result so the model stops looping.

        Once the cap is exceeded, drop the retry instruction and return a TERMINAL result so the model stops
        looping memory calls and proceeds to answer the user — a failed memory side effect must never block
        the turn's reply (#42405).
        """
        self._consolidation_failures += 1
        if self._consolidation_failures <= self._MAX_CONSOLIDATION_FAILURES_PER_TURN:
            return response
        return {"success": False, "done": True, "error": (
            f"Memory consolidation failed {self._consolidation_failures} times this turn. Stop retrying "
            "memory calls — leave memory unchanged for now and continue with your reply to the user. "
            "The fact can be saved in a later turn.")}

    @staticmethod
    def _sanitize(entry: str, filename: str) -> str:
        """Snapshot-only threat scrubbing: strict scope, same as writes; empty /
        already-blocked entries pass through. Used for MEMORY/USER entries and for
        the whole-file SELF block."""
        from tools.threat_patterns import scan_for_threats

        findings = scan_for_threats(entry, scope="strict") if entry and not entry.startswith("[BLOCKED:") else None
        if not findings:
            return entry
        logger.warning("Memory entry from %s blocked at load time: %s", filename, ", ".join(findings))
        return (f"[BLOCKED: {filename} entry contained threat pattern(s): {', '.join(findings)}. "
                f"Removed from system prompt; use memory(action=remove) to delete the original.]")

    def load_from_disk(self):
        """Load MEMORY.md / USER.md / SELF.md and capture the frozen system-prompt
        snapshot. Threat hits are replaced by a ``[BLOCKED: …]`` placeholder in the
        SNAPSHOT only; live state keeps the raw text so the user can see and remove
        poisoned content (dropping it silently would hide the attack)."""
        for target in ("memory", "user", *WHOLE_FILE_TARGETS):
            path = self._path_for(target)
            path.parent.mkdir(parents=True, exist_ok=True)
            if target in WHOLE_FILE_TARGETS:
                # One whole-file document: no §-split, no dedup, no char budget
                # (its bytes must never eat MEMORY's room). A read that fails on
                # an existing file leaves the previous text in place rather than
                # presenting an empty self-state.
                raw, read_ok = self._read_raw_checked(path)
                text = raw.strip() if read_ok else self.self_text
                self._set_entries(target, [text] if text else [])
                self._system_prompt_snapshot[target] = self._render_block(
                    target, [self._sanitize(text, path.name)] if text else [])
                continue
            # Deduplicate (order-preserving, first occurrence wins).
            entries = list(dict.fromkeys(self._read_file(path)))
            self._set_entries(target, entries)
            # External writers (MCP bridges, hand edits) can exceed the cap; the limit only fires on
            # add/replace, so the oversized block would silently ride in the prompt while every later
            # add is refused with no visible cause (#10877). Warn; never truncate a user's memories.
            if (count := self._char_count(target)) > (limit := self._char_limit(target)):
                logger.warning("%s exceeds its char limit on load: %d/%d chars. Entries stay loaded; "
                               "further additions are blocked until it is back under the limit.",
                               path.name, count, limit)
            self._system_prompt_snapshot[target] = self._render_block(
                target, [self._sanitize(e, path.name) for e in entries])

    @staticmethod
    @contextmanager
    def _file_lock(path: Path):
        """Exclusive lock on a separate .lock file so the memory file itself can
        still be atomically replaced."""
        from tools import memory_tool as _mt  # fcntl/msvcrt live (and are patched) there
        fcntl, msvcrt = _mt.fcntl, _mt.msvcrt
        lock_path = path.with_suffix(path.suffix + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        if fcntl is None and msvcrt is None:
            yield
            return
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        raw_fd = os.open(lock_path, flags, 0o600)
        try:
            # The creation mode is filtered through the process umask and does
            # not repair a lock left loose by an older Hermes process. Tighten
            # the opened inode before acquiring the lock so both cases are
            # owner-only. Operating on the fd avoids a path-swap window.
            if hasattr(os, "fchmod"):
                os.fchmod(raw_fd, 0o600)
            fd = os.fdopen(raw_fd, "r+", encoding="utf-8")
        except Exception:
            os.close(raw_fd)
            raise
        with fd:
            def _flock(unlock: bool):
                if fcntl:
                    fcntl.flock(fd, fcntl.LOCK_UN if unlock else fcntl.LOCK_EX)
                else:
                    fd.seek(0)
                    msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK if unlock else msvcrt.LK_LOCK, 1)
            _flock(False)
            try:
                yield
            finally:
                with suppress(OSError):
                    _flock(True)

    @staticmethod
    def _path_for(target: str) -> Path:
        if target in WHOLE_FILE_TARGETS:
            # SELF.md is an identity file at the CANONICAL home root, not a memory
            # document: ``memories/SELF.md`` is the pre-migration legacy location
            # (moved by seed_or_migrate_self_md()) and is never read as a source.
            return get_hermes_home() / SELF_MD_FILENAME
        from tools import memory_tool  # get_memory_dir is monkeypatched there
        return memory_tool.get_memory_dir() / ("USER.md" if target == "user" else "MEMORY.md")

    def _entries_for(self, target: str) -> List[str]:
        """Entries of an entry-list target."""
        if target in WHOLE_FILE_TARGETS:
            # SELF.md now uses §-delimited entries like MEMORY.md
            if not self.self_text:
                return []
            return [e.strip() for e in self.self_text.split(ENTRY_DELIMITER) if e.strip()]
        return self.user_entries if target == "user" else self.memory_entries

    def whole_file_state(self, target: str) -> Tuple[str, str]:
        """``(raw text, path)`` of a whole-file target as of the last load.

        SELF is not an entry list, so callers that need the raw text for their own
        policy (the KB1-IDENTITY-DEGRADED slot classifier in ``agent.prompt_builder``)
        read it here instead of re-reading the file."""
        if target not in WHOLE_FILE_TARGETS:
            raise ValueError(f"{target!r} is not a whole-file target: {WHOLE_FILE_TARGETS}")
        return self.self_text, str(self._path_for(target))

    def _set_entries(self, target: str, entries: List[str]):
        if target in WHOLE_FILE_TARGETS:
            # SELF.md now uses §-delimited entries like MEMORY.md
            self.self_text = ENTRY_DELIMITER.join(entries) if entries else ""
            return
        setattr(self, "user_entries" if target == "user" else "memory_entries", entries)

    def _char_count(self, target: str) -> int:
        """Chars of *target*. Whole-file targets count their own bytes only — they
        are NOT part of MEMORY's 2,200-char accounting."""
        if target in WHOLE_FILE_TARGETS:
            return len(self.self_text)
        return len(ENTRY_DELIMITER.join(self._entries_for(target)))

    def _char_limit(self, target: str) -> int:
        if target in WHOLE_FILE_TARGETS:
            return 0  # unbudgeted whole-file state; see _char_count
        return self.user_char_limit if target == "user" else self.memory_char_limit

    def _usage(self, target: str) -> str:
        if target in WHOLE_FILE_TARGETS:
            return f"{self._char_count(target):,} chars"
        return f"{self._char_count(target):,}/{self._char_limit(target):,}"

    def _usage_pct(self, target: str, current: int) -> str:
        if target in WHOLE_FILE_TARGETS:
            # SELF has no cap of its own and must never be reported against (or
            # consume) MEMORY's 2,200-char budget.
            return f"{current:,} chars (unbudgeted)"
        limit = self._char_limit(target)
        return f"{min(100, int((current / limit) * 100)) if limit > 0 else 0}% — {current:,}/{limit:,} chars"

    def _failure_with_entries(self, target: str, message: str) -> Dict[str, Any]:
        """Consolidation failure carrying the live entries so the model can consolidate."""
        return self._consolidation_failure(
            _error(message, current_entries=self._entries_for(target), usage=self._usage(target)))

    def _mutate(self, target: str, mutate, *, skip_drift: bool = False) -> Dict[str, Any]:
        """Lock, re-read from disk, run ``mutate(entries, limit)`` -> ``(new_entries, message)``
        or an error dict, then persist and return the success response. The reload aborts
        on an existing-but-unreadable file (even append-only ``add`` rewrites the whole
        file) and, unless *skip_drift*, on external drift (flushing would discard
        un-roundtrippable content). Drift check and parse use the SAME raw snapshot —
        a failed second read used to count as "no drift"."""
        path = self._path_for(target)
        with self._file_lock(path):
            raw, read_ok = self._read_raw_checked(path)
            if not read_ok:
                return _read_failed_error(path)
            bak = None if skip_drift else self._detect_external_drift(target, raw)
            self._set_entries(target, list(dict.fromkeys(self._parse_entries(raw))))
            if bak:
                return _drift_error(path, bak)
            result = mutate(self._entries_for(target), self._char_limit(target))
            if isinstance(result, dict):
                return result
            self._set_entries(target, result[0])
            path.parent.mkdir(parents=True, exist_ok=True)
            self._write_file(path, result[0])
            return self._success_response(target, result[1])

    def add(self, target: str, content: str) -> Dict[str, Any]:
        """Append a new entry. Returns error if it would exceed the char limit."""
        content = content.strip()
        if not content:
            return _error("Content cannot be empty.")
        if scan_error := _scan_memory_content(content):
            return _error(scan_error)

        def _add(entries, limit):
            if content in entries:
                return self._success_response(target, "Entry already exists (no duplicate added).")
            # Skip limit check for unbudgeted targets (limit=0 means no cap)
            if limit > 0 and len(ENTRY_DELIMITER.join(entries + [content])) > limit:
                return self._failure_with_entries(target, (
                    f"Memory at {self._char_count(target):,}/{limit:,} chars. Adding this entry "
                    f"({len(content)} chars) would exceed the limit. Consolidate now: use 'replace' to merge "
                    f"overlapping entries into shorter ones or 'remove' stale or less important entries (see "
                    f"current_entries below), then retry this add — all in this turn."))
            return entries + [content], "Entry added."
        # Append-only: skip the drift guard (appending never clobbers foreign
        # content) but still refuse a failed read — add rewrites the WHOLE file.
        return self._mutate(target, _add, skip_drift=True)

    def replace(self, target: str, old_text: str, new_content: str) -> Dict[str, Any]:
        """Find entry containing old_text substring, replace it with new_content."""
        new_content = new_content.strip()
        if not old_text.strip():
            return _error("old_text cannot be empty.")
        if not new_content:
            return _error("new_content cannot be empty. Use 'remove' to delete entries.")
        if scan_error := _scan_memory_content(new_content):
            return _error(scan_error)
        return self._edit(target, old_text.strip(), new_content)

    def replace_whole_file(self, target: str, new_content: str) -> Dict[str, Any]:
        """Overwrite a whole-file target (SELF.md) in one call.

        The frozen ``_system_prompt_snapshot`` is deliberately NOT refreshed: a
        mid-session write must not change this session's system prompt (that is the
        prefix-cache contract MEMORY/USER already follow) — the new text lands in
        the next session's prompt.
        """
        if target not in WHOLE_FILE_TARGETS:
            return _error(f"{target!r} is not a whole-file target; use add/replace/remove on its entries.")
        text = (new_content or "").strip()
        if not text:
            return _error("content cannot be empty. target='self' replaces the WHOLE SELF.md file, so pass "
                          "the complete new text (to clear the file entirely, write it with write_file).")
        if scan_error := _scan_memory_content(text):
            return _error(scan_error)
        path = self._path_for(target)
        with self._file_lock(path):
            # Read before writing: an existing-but-unreadable file must not be
            # overwritten, and the caller needs to know it was not.
            _raw, read_ok = self._read_raw_checked(path)
            if not read_ok:
                return _read_failed_error(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                atomic_write_text(path, text + "\n", tmp_prefix=".self_")
            except OSError as e:
                return _error(f"Failed to write {path.name}: {e}")
        self._set_entries(target, [text])
        return self._success_response(
            target, f"{path.name} replaced (whole file, {len(text):,} chars). "
                    "This session's system prompt is unchanged (frozen snapshot); the new text is "
                    "injected from the next session on.")

    def remove(self, target: str, old_text: str) -> Dict[str, Any]:
        """Remove the entry containing old_text substring. Whole-file targets have
        no entries: refused explicitly instead of falling into MEMORY's list."""

        if not old_text.strip():
            return _error("old_text cannot be empty.")
        return self._edit(target, old_text.strip(), None)

    def _edit(self, target: str, old_text: str, new_content: Optional[str]) -> Dict[str, Any]:
        """Locked replace (``new_content`` set) or remove (None) of the entry matching *old_text*."""
        def _apply(entries, limit):
            idx, ambiguous = _find_unique_match(entries, old_text)
            if ambiguous:
                return _error(f"Multiple entries matched '{old_text}'. Be more specific.",
                              matches=[e[:80] + ("..." if len(e) > 80 else "") for e in entries if old_text in e])
            if idx is None:
                return self._consolidation_failure(_error(
                    f"No entry matched '{old_text}'. Check current_entries below and retry with the exact text "
                    f"of the entry you want to {'replace' if new_content else 'remove'}.", current_entries=entries))
            replaced = entries[:idx] + ([] if new_content is None else [new_content]) + entries[idx + 1:]
            if new_content is None:
                return replaced, "Entry removed."
            new_total = len(ENTRY_DELIMITER.join(replaced))
            # Skip limit check for unbudgeted targets (limit=0 means no cap)
            if limit > 0 and new_total > limit:
                return self._failure_with_entries(target, (
                    f"Replacement would put memory at {new_total:,}/{limit:,} chars. Shorten the new content, "
                    f"or 'remove' other stale or less important entries to make room (see current_entries "
                    f"below), then retry — all in this turn."))
            return replaced, "Entry replaced."
        return self._mutate(target, _apply)

    @staticmethod
    def _apply_batch_op(working: List[str], act: str, content: str, old_text: str, pos: str) -> Optional[str]:
        """Apply one batch op to *working* in place; return an error message or None."""
        if act == "add":
            if not content:
                return f"{pos}: content is required."
            if content not in working:  # idempotent -- skip duplicate, don't fail the batch
                working.append(content)
            return None
        if act not in ("replace", "remove"):
            return f"{pos}: unknown action. Use add, replace, or remove."
        if not old_text:
            return f"{pos}: old_text is required."
        if act == "replace" and not content:
            return f"{pos}: content is required (use action='remove' to delete)."
        idx, ambiguous = _find_unique_match(working, old_text)
        if ambiguous:
            return f"{pos}: '{old_text}' matched multiple distinct entries -- be more specific."
        if idx is None:
            return f"{pos}: no entry matched '{old_text}'."
        working[idx:idx + 1] = [content] if act == "replace" else []
        return None

    def apply_batch(self, target: str, operations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Apply add/replace/remove ops atomically against the FINAL budget, so one call
        can free space and add entries. All-or-nothing: any malformed / unmatched op or
        an over-limit result writes NOTHING and returns the first failure plus live state."""
        if not operations:
            return _error("operations list is empty.")

        ops = [op or {} for op in operations]
        # Scan every add/replace content BEFORE touching disk -- one poisoned op rejects the batch.
        for i, op in enumerate(ops):
            scan_error = op.get("action") in {"add", "replace"} and op.get("content") and _scan_memory_content(op["content"])
            if scan_error:
                return _error(f"Operation {i + 1}: {scan_error}")

        def _apply(entries, limit):
            working = list(entries)  # only committed if the whole batch validates
            for i, op in enumerate(ops):
                act = op.get("action")
                msg = self._apply_batch_op(working, act, (op.get("content") or op.get("new_text") or "").strip(),
                                           (op.get("old_text") or "").strip(), f"Operation {i + 1} ({act or 'unknown'})")
                if msg:
                    return self._failure_with_entries(target, msg + " No operations were applied (batch is all-or-nothing).")
            if entries and not working:
                # #103419: a consolidation batch that removes the last entry would
                # commit an empty file as a normal successful write. Refuse; single
                # remove() is the deliberate-wipe path.
                label = self._path_for(target).name
                return self._failure_with_entries(target, (
                    f"Refusing to empty {label}: this batch would remove every entry from a "
                    f"previously non-empty store. Nothing was applied (batch is all-or-nothing). "
                    f"Keep at least one entry — merge overlapping entries into a shorter one instead "
                    f"of removing the last one (see current_entries below). To delete the final entry "
                    f"deliberately, use single remove() calls."))
            new_total = len(ENTRY_DELIMITER.join(working))  # budget check against the FINAL state only
            if new_total > limit:
                return self._failure_with_entries(target, (
                    f"After applying all {len(operations)} operations, memory would be at "
                    f"{new_total:,}/{limit:,} chars -- over the limit. Remove or shorten more "
                    f"entries in the same batch (see current_entries below), then retry."))
            return working, f"Applied {len(operations)} operation(s)."
        return self._mutate(target, _apply)

    def format_for_system_prompt(self, target: str) -> Optional[str]:
        """Frozen load-time snapshot (NOT live state — mid-session writes don't touch
        it, preserving the prefix cache); None if empty. ``target`` may be
        ``"memory"``, ``"user"`` or the whole-file ``"self"`` (SELF.md)."""
        return self._system_prompt_snapshot.get(target, "") or None

    def _success_response(self, target: str, message: str = None) -> Dict[str, Any]:
        """TERMINAL and WITHOUT the entries list: echoing entries invites the model to
        "find more to fix" and re-issue the same ops. A successful write resets the
        per-turn failure budget."""
        # A successful write means the consolidation loop made progress, so the per-turn failure budget
        # resets (the cap counts consecutive failures, not lifetime ones within a turn) (#42405).
        self._consolidation_failures = 0
        response = {"success": True, "done": True, "target": target,
                    "usage": self._usage_pct(target, self._char_count(target)),
                    **(dict(message=message) if message else {}),
                    "note": "Write saved. This update is complete — do not repeat it."}
        if target not in WHOLE_FILE_TARGETS:
            # entry_count is meaningless for a whole-file target (SELF.md is one
            # document, not a list) and would only invite entry-shaped retries.
            response["entry_count"] = len(self._entries_for(target))
        return response

    def _render_block(self, target: str, entries: List[str]) -> str:
        """System prompt block: header + usage indicator + entries ("" when empty).

        The header is looked up per target (never a two-way fallback): a target
        that has no header must fail loudly instead of rendering as MEMORY's.
        """
        if not entries:
            return ""
        title = MEMORY_BLOCK_HEADERS.get(target)
        if title is None:
            raise ValueError(f"no system-prompt block header for memory target {target!r}")
        content, sep = ENTRY_DELIMITER.join(entries), "═" * 46
        return f"{sep}\n{title} [{self._usage_pct(target, len(content))}]\n{sep}\n{content}"

    @staticmethod
    def _read_raw_checked(path: Path) -> Tuple[str, bool]:
        """``(raw, read_ok)``; ``read_ok`` is False ONLY when the file EXISTS but can't be
        read. Decoding stays STRICT (``errors="replace"`` would hand callers a lossy view
        a save then persists); ``utf-8-sig`` strips a Notepad BOM off the first entry."""
        if not path.exists():
            return "", True
        try:
            # utf-8-sig strips a leading UTF-8 BOM (Notepad-edited memory files on Windows) and is
            # byte-identical to utf-8 otherwise. Plain utf-8 kept U+FEFF glued to the first entry,
            # corrupting matching/dedup for that entry forever (#10878 / PR #10888). Decode errors stay
            # STRICT on purpose: errors="replace" would hand read-modify-write callers a lossy view that a
            # subsequent save persists over the real bytes — the wipe class documented above. Undecodable
            # bytes must surface as read_ok=False.
            return path.read_text(encoding="utf-8-sig"), True
        except (OSError, UnicodeDecodeError):
            return "", False

    @staticmethod
    def _parse_entries(raw: str) -> List[str]:
        """Stripped, non-empty entries; splits on the FULL delimiter so a bare "§" survives."""
        return [e for e in (x.strip() for x in raw.split(ENTRY_DELIMITER)) if e]

    @staticmethod
    def _read_file(path: Path) -> List[str]:
        """Entries of a memory file ([] on any error). Read-only callers only; mutation
        paths use ``_read_raw_checked`` so they can refuse to overwrite an unreadable file."""
        return MemoryStore._parse_entries(MemoryStore._read_raw_checked(path)[0])

    @staticmethod
    def _write_file(path: Path, entries: List[str]):
        """Atomic temp-file + rename: readers never see a truncated file. Also used by
        agent/learning_mutations.py."""
        try:
            atomic_write_text(path, ENTRY_DELIMITER.join(entries), tmp_prefix=".mem_")
        except OSError as e:
            raise RuntimeError(f"Failed to write memory file {path}: {e}")

    def _detect_external_drift(self, target: str, raw: str) -> Optional[str]:
        """``.bak.<ts>`` snapshot path if *raw* shows external drift, else None. Signals:
        round-trip mismatch, or one entry over the whole-file limit (no tool-written
        entry can be — an external writer appended free-form text)."""
        parsed = self._parse_entries(raw)
        limit = self._char_limit(target)
        # Skip char limit check for unbudgeted targets (limit=0 means no cap)
        if not raw.strip() or (raw.strip() == ENTRY_DELIMITER.join(parsed)
                               and (limit <= 0 or max(map(len, parsed), default=0) <= limit)):
            return None
        path = self._path_for(target)
        bak_path = path.with_suffix(path.suffix + f".bak.{int(time.time())}")
        try:
            bak_path.write_text(raw, encoding="utf-8")
        except OSError:
            return str(bak_path) + " (BACKUP FAILED — file unchanged on disk)"
        return str(bak_path)

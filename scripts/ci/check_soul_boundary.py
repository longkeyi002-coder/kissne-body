#!/usr/bin/env python3
"""Reject personal Soul/identity content at the Git, CI and release boundaries.

The boundary (KB0-SOUL-GIT-GUARD): the *personal* identity of a running
instance -- the real content of ``$HERMES_HOME/SOUL.md`` and
``$HERMES_HOME/memories/{SELF,MEMORY,USER}.md`` -- must never reach this
repository, a public branch, a PR or a published artifact.  What may be
tracked is only what a human reviewed and listed here: the upstream default
persona templates and their asset copies.

``.gitignore`` cannot enforce that (``git add -f`` ignores it) and a build
context is not the Git tree, so the enforcement is this script, landed in
three places:

* ``.pre-commit-config.yaml`` -> ``--staged``: over the Git *index*, so a
  force-added file is caught before it exists as a commit;
* ``.github/workflows/soul-boundary-check.yml`` -> over the checkout;
* ``scripts/release.py`` -> ``--release``: before a tag or GitHub release.

Three independent judgements, so no single trick passes all of them:

1. **Explicit allowlist** -- per file, content-digest pinned.  Nothing about
   the list is inferred from a filename pattern; a reviewed file that changes
   at all trips the gate until a human re-pins it (review required).
2. **Identity shape (denylist)** -- a ``SOUL.md``/``SELF.md`` anywhere that is
   not on the allowlist, or any file under a ``memories/`` directory, is a
   runtime-home shape and is rejected regardless of its content.
3. **Content judgement** -- the live personal identity text (when
   ``--hermes-home`` points at a running instance) must not appear anywhere,
   and an identity file may not be an untouched placeholder/legacy runtime
   template (``hermes_cli.default_soul.is_legacy_template_soul`` /
   ``hermes_cli.default_self.is_placeholder_self_md``): those are what a
   clone/export/backup-restore drags in.

Exit codes: ``0`` clean, ``1`` violation, ``2`` cannot verify (fail closed --
the check refuses to report "clean" when it cannot establish the boundary).
File contents are never printed, only paths and reasons.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import subprocess
import sys
import tarfile
import zipfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

_REPO_ROOT = Path(__file__).resolve().parents[2]

# ── 1. the explicit allowlist ───────────────────────────────────────────────
# Every identity-class file that may be tracked, listed one by one, with the
# sha256 of its *normalized* text (line endings unified, BOM stripped, outer
# whitespace trimmed -- see _normalize).  A new entry is a review decision:
# only universal upstream templates, schemas, fixtures and redacted samples
# belong here.  A personal SOUL.md/memories file belongs nowhere in this dict.
ALLOWLISTED_IDENTITY_FILES: dict[str, str] = {
    # Upstream default persona template, shipped at the repo root and (byte-
    # identical after normalization) in the Docker build context.
    "SOUL.md": "36c1f5a2e92cd1d018311eaf4c8f1e8886672eae78212e033c681d0e3d5d506f",
    "docker/SOUL.md": "36c1f5a2e92cd1d018311eaf4c8f1e8886672eae78212e033c681d0e3d5d506f",
    # Reviewed role-soul template for the kanban-video-orchestrator skill
    # (placeholders only, no instance content).
    "optional-skills/creative/kanban-video-orchestrator/assets/soul.md.tmpl":
        "1e0f31a4a866301669ae8087bee09e9ed17a77b2b4438a7d7786d8f5086ad323",
}

# ── 2. identity shape (denylist) ────────────────────────────────────────────
_IDENTITY_FILENAMES = frozenset({"soul.md", "self.md"})
_MEMORY_DIRNAME = "memories"
_MEMORY_FILENAMES = frozenset({"self.md", "memory.md", "user.md"})

# The runtime layout a personal instance keeps its identity in (see the
# module docstring).  Used to build the content signatures and to fail closed
# when a named HERMES_HOME has none of them.
_PERSONAL_IDENTITY_RELPATHS = (
    "SOUL.md",
    "memories/SELF.md",
    "memories/MEMORY.md",
    "memories/USER.md",
)

_SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", "site-packages",
})
_MAX_TEXT_BYTES = 1 << 20  # content scan cap; larger files are name-checked only
_ARCHIVE_SUFFIXES = frozenset({".zip", ".gz", ".tgz", ".whl", ".tar", ".jar"})
_MIN_SIGNATURE_CHARS = 32  # shorter personal text is too generic to match on


# ── text helpers ────────────────────────────────────────────────────────────
def _normalize(text: str) -> str:
    """Unify line endings, strip a leading BOM, trim outer whitespace."""
    return text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff").strip()


def _decode(data: bytes) -> str | None:
    """Text of ``data``, or None when it is not UTF-8 text (binary)."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _digest(data: bytes) -> str:
    """sha256 of the normalized text -- stable across CRLF/BOM-only churn."""
    return hashlib.sha256(_normalize(data.decode("utf-8", "replace")).encode("utf-8")).hexdigest()


def _load_repo_module(name: str, relative_path: str):
    """Import a module from this checkout by path.

    By path, not by ``import hermes_cli.x``: the package ``__init__`` has
    stdout side effects, and the helpers wanted here import nothing.
    """
    path = _REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {relative_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _TemplateJudges:
    """The repo's own placeholder/legacy-template judgements, or fail closed."""

    def __init__(self) -> None:
        self._soul = _load_repo_module("_soul_boundary_default_soul", "hermes_cli/default_soul.py")
        self._self = _load_repo_module("_soul_boundary_default_self", "hermes_cli/default_self.py")
        self.upstream_soul = _normalize(self._soul.DEFAULT_SOUL_MD)
        self.upstream_self = _normalize(self._self.DEFAULT_SELF_MD)

    def legacy_soul(self, text: str) -> bool:
        return bool(self._soul.is_legacy_template_soul(text))

    def placeholder_self(self, text: str) -> bool:
        return bool(self._self.is_placeholder_self_md(text))


# ── shape / allowlist judgements ────────────────────────────────────────────
def is_identity_shaped(relative_path: str) -> bool:
    """True for the runtime identity layout (see the docstring's judgement 2)."""
    parts = PurePosixPath(relative_path.replace("\\", "/")).parts
    if not parts:
        return False
    name = parts[-1].casefold()
    if name in _IDENTITY_FILENAMES:
        return True
    return len(parts) > 1 and parts[-2].casefold() == _MEMORY_DIRNAME and name in _MEMORY_FILENAMES


def _allowlist_mismatch_reason(relative_path: str, data: bytes, judges: _TemplateJudges) -> str | None:
    """Why an allowlisted file is not the reviewed content, or None when it is."""
    expected = ALLOWLISTED_IDENTITY_FILES[relative_path]
    actual = _digest(data)
    if actual == expected:
        return None
    text = data.decode("utf-8", "replace")
    if judges.legacy_soul(text):
        return ("holds a legacy/runtime-seeded SOUL scaffold, not the reviewed template "
                "(a runtime home was copied into the checkout)")
    if judges.placeholder_self(text):
        return ("holds an untouched placeholder SELF.md, not the reviewed template "
                "(a clone/export/restore artifact was copied into the checkout)")
    return (f"content is not the reviewed allowlist digest (expected {expected[:12]}…, got "
            f"{actual[:12]}…). Re-review the change, then re-pin the digest in "
            "scripts/ci/check_soul_boundary.py")


# ── personal-content signatures ─────────────────────────────────────────────
def personal_signatures(hermes_home: Path, judges: _TemplateJudges) -> tuple[list[tuple[str, str]], int]:
    """(signatures, identity files found) for the live instance.

    A file whose content is an untouched upstream template carries no personal
    information, so it contributes no signature -- otherwise every stock
    install would flag the repo's own ``SOUL.md``.
    """
    signatures: list[tuple[str, str]] = []
    found = 0
    for relative in _PERSONAL_IDENTITY_RELPATHS:
        try:
            data = (hermes_home / relative).read_bytes()
        except OSError:
            continue
        found += 1
        text = _normalize(data.decode("utf-8", "replace"))
        if len(text) < _MIN_SIGNATURE_CHARS:
            continue
        if judges.legacy_soul(text) or judges.placeholder_self(text):
            continue
        if text in (judges.upstream_soul, judges.upstream_self):
            continue
        signatures.append((f"HERMES_HOME/{relative}", text))
    return signatures, found


def _content_reason(text: str, signatures: Sequence[tuple[str, str]]) -> str | None:
    on_disk = _normalize(text)
    if len(on_disk) < _MIN_SIGNATURE_CHARS:
        return None
    for source, signature in signatures:
        if signature in on_disk:
            return f"contains the personal identity content of {source}"
    return None


# ── sources: filesystem, Git index, artifacts ──────────────────────────────
def _iter_files(root: Path):
    """(relative posix path, absolute path) for every file under ``root``."""
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(name for name in dirnames if name not in _SKIP_DIRS)
        for name in sorted(filenames):
            absolute = Path(directory) / name
            if absolute.is_symlink() or not absolute.is_file():
                continue
            yield absolute.relative_to(root).as_posix(), absolute


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)


def _index_entries(root: Path) -> dict[str, bytes] | None:
    """Staged path -> the bytes a commit would capture, or None if unreadable.

    The *index* is the source, not a directory listing: a file force-added
    with ``git add -f`` is staged even though the worktree still looks
    unchanged to every ignore rule.  Only paths where the index and the
    worktree disagree are fetched as blobs (``git show :path``) -- when they
    agree, the staged content *is* the file on disk, and 13k ``git show``
    calls per commit would make the hook useless.
    """
    listed = _git(root, "ls-files", "-z", "--cached")
    if listed.returncode != 0:
        return None
    paths = [raw.decode("utf-8", "replace") for raw in listed.stdout.split(b"\0") if raw]
    divergent = {
        raw.decode("utf-8", "replace")
        for raw in _git(root, "diff", "-z", "--name-only").stdout.split(b"\0") if raw
    }
    entries: dict[str, bytes] = {}
    for relative in paths:
        if relative in divergent:
            blob = _git(root, "show", f":{relative}")
            entries[relative] = blob.stdout if blob.returncode == 0 else b""
            continue
        path = root / relative
        try:
            entries[relative] = path.read_bytes() if path.stat().st_size <= _MAX_TEXT_BYTES else b""
        except OSError:
            entries[relative] = b""
    return entries


def _read_capped(path: Path) -> bytes | None:
    try:
        if path.stat().st_size > _MAX_TEXT_BYTES:
            return None
        return path.read_bytes()
    except OSError:
        return None


def check_repo(
    root: Path,
    judges: _TemplateJudges,
    signatures: Sequence[tuple[str, str]] = (),
    *,
    staged: bool = False,
    allow_allowlist: bool = True,
) -> list[str]:
    """Violations for a checkout (``allow_allowlist=False`` = artifact scan)."""
    violations: list[str] = []
    allowlisted = ALLOWLISTED_IDENTITY_FILES if allow_allowlist else {}

    if staged:
        entries = _index_entries(root)
        if entries is None:
            return [f"{root}: cannot read the Git index (not a git checkout?)"]
        sources: list[tuple[str, bytes | None]] = list(entries.items())
        for relative, expected in allowlisted.items():
            data = entries.get(relative)
            if data is None:
                violations.append(
                    f"{relative}: allowlisted identity file is missing from the Git index "
                    "(staged deletion). Identity templates must not be removed silently")
            elif _digest(data) != expected:
                reason = _allowlist_mismatch_reason(relative, data, judges)
                if reason:
                    violations.append(f"{relative}: {reason}")
    else:
        sources = [(relative, _read_capped(path)) for relative, path in _iter_files(root)]
        digests = {relative: data for relative, data in sources if data is not None}
        for relative, expected in allowlisted.items():
            if relative not in digests:
                violations.append(
                    f"{relative}: allowlisted identity file is missing from the checkout (deleted) or "
                    "unreadable. Restore it, or remove its allowlist entry in the same reviewed change")
            elif _digest(digests[relative]) != expected:
                reason = _allowlist_mismatch_reason(relative, digests[relative], judges)
                if reason:
                    violations.append(f"{relative}: {reason}")

    for relative, data in sources:
        if is_identity_shaped(relative) and relative not in allowlisted:
            violations.append(
                f"{relative}: identity-class path is not on the reviewed allowlist. Only templates a "
                "human listed in ALLOWLISTED_IDENTITY_FILES may be tracked; a runtime SOUL.md/"
                "SELF.md/MEMORY.md/USER.md stays in HERMES_HOME")
            continue
        if data is None:
            continue
        if text := _decode(data):
            reason = _content_reason(text, signatures)
            if reason:
                violations.append(f"{relative}: {reason}")
        elif PurePosixPath(relative).suffix.casefold() in _ARCHIVE_SUFFIXES:
            # A committed or built archive: the payload is what ships, so read it.
            violations.extend(check_archive(
                root / relative, judges, signatures, unknown_is_violation=False))
    return violations


def check_archive(
    path: Path,
    judges: _TemplateJudges,
    signatures: Sequence[tuple[str, str]],
    *,
    unknown_is_violation: bool = True,
) -> list[str]:
    """Violations inside an archive (tar/tar.gz/tgz/zip) -- a release artifact."""
    violations: list[str] = []
    label = path.name
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    violations.extend(
                        _member_violations(label, info.filename, archive.read(info), judges, signatures))
        elif tarfile.is_tarfile(path):
            with tarfile.open(path, "r:*") as archive:
                for member in archive.getmembers():
                    if not member.isfile():
                        continue
                    handle = archive.extractfile(member)
                    data = handle.read() if handle else b""
                    violations.extend(
                        _member_violations(label, member.name, data, judges, signatures))
        elif unknown_is_violation:
            # An explicitly named artifact that cannot be read is a failure in
            # itself; a stray .gz inside a scanned tree is not (see the caller).
            violations.append(f"{label}: unsupported artifact type (expected tar/zip)")
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        violations.append(f"{label}: cannot inspect artifact ({exc})")
    return violations


def _member_violations(
    label: str,
    name: str,
    data: bytes,
    judges: _TemplateJudges,
    signatures: Sequence[tuple[str, str]],
) -> list[str]:
    violations: list[str] = []
    member = name.replace("\\", "/").lstrip("./")
    if is_identity_shaped(member):
        violations.append(
            f"{label}::{member}: identity-class path inside a published artifact. No runtime identity "
            "file belongs in a release/CI artifact")
    text = _decode(data)
    if text is None:
        return violations
    reason = _content_reason(text, signatures)
    if reason:
        violations.append(f"{label}::{member}: {reason}")
    return violations


def check_artifact_path(
    path: Path, judges: _TemplateJudges, signatures: Sequence[tuple[str, str]]
) -> list[str]:
    """Violations in an unpacked artifact directory or an archive file."""
    if path.is_dir():
        return check_repo(path, judges, signatures, allow_allowlist=False)
    if path.is_file():
        return check_archive(path, judges, signatures)
    return [f"{path}: artifact path does not exist"]


# ── CLI ─────────────────────────────────────────────────────────────────────
_DESCRIPTION = "Reject personal Soul/identity content at the Git, CI and release boundaries."


def _release_artifact_roots(root: Path) -> list[Path]:
    """Build outputs a release could publish from the repo root."""
    candidates: list[Path] = []
    for directory in ("dist", "build", "release-artifacts"):
        candidate = root / directory
        if candidate.is_dir():
            candidates.append(candidate)
    for pattern in ("*.tar.gz", "*.tgz", "*.zip", "*.whl"):
        candidates.extend(sorted(root.glob(pattern)))
    return candidates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=_DESCRIPTION)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(),
                        help="repository root to inspect (default: current directory)")
    parser.add_argument("--hermes-home", type=Path, default=None,
                        help="live instance home whose SOUL.md/memories/*.md content is personal "
                             "and must not appear in the checked tree (default: $HERMES_HOME when it "
                             "is set and is a directory)")
    parser.add_argument("--staged", action="store_true",
                        help="check the Git index (the pre-commit landing point)")
    parser.add_argument("--artifact", type=Path, action="append", default=[],
                        help="extra release/CI artifact (archive or directory) to scan strictly")
    parser.add_argument("--no-hermes-home-env", action="store_true",
                        help="never read $HERMES_HOME; judge only by allowlist and identity shape")
    parser.add_argument("--release", action="store_true",
                        help="also scan build outputs at the repo root (the release landing point)")
    args = parser.parse_args(argv)

    try:
        judges = _TemplateJudges()
    except (ImportError, AttributeError, OSError) as exc:
        print(f"::error::cannot load the placeholder/legacy template judgements: {exc}", file=sys.stderr)
        return 2

    # A caller that names no home still gets content judgement when the
    # environment names one -- that is the pre-commit case, where the operator
    # is the instance owner.  CI has no HERMES_HOME and falls back to the
    # allowlist/shape judgements.
    hermes_home = args.hermes_home
    from_env = False
    if hermes_home is None and not args.no_hermes_home_env:
        named = os.environ.get("HERMES_HOME", "").strip()
        if named and Path(named).is_dir():
            hermes_home, from_env = Path(named), True

    signatures: Sequence[tuple[str, str]] = ()
    if hermes_home is not None:
        if not hermes_home.is_dir():
            print(f"::error::HERMES_HOME is not a directory: {hermes_home}", file=sys.stderr)
            return 2
        signatures, found = personal_signatures(hermes_home, judges)
        if not found and not from_env:
            # An operator who *names* a home expects it to be compared; an
            # inherited $HERMES_HOME pointing at a fresh install holds no
            # personal identity yet, and that is not a failure.
            print(
                "::error::no identity files (SOUL.md, memories/SELF.md, memories/MEMORY.md, "
                f"memories/USER.md) under {hermes_home}; cannot establish the boundary",
                file=sys.stderr)
            return 2

    root = args.repo_root.resolve()
    if not root.is_dir():
        print(f"::error::repository root is not a directory: {root}", file=sys.stderr)
        return 2

    violations = check_repo(root, judges, signatures, staged=args.staged)
    for artifact in args.artifact:
        violations.extend(check_artifact_path(artifact, judges, signatures))
    if args.release:
        for artifact in _release_artifact_roots(root):
            violations.extend(check_artifact_path(artifact, judges, signatures))

    if not violations:
        mode = "staged" if args.staged else ("release" if args.release else "checkout")
        print(f"No personal Soul/identity content detected ({mode} scan of {root}).")
        return 0

    print("::error::personal Soul/identity content is forbidden in the repository, a public branch, "
          "a PR or a published artifact")
    for violation in violations:
        print(f"  {violation}")
    print("Keep personal identity in HERMES_HOME (SOUL.md, memories/SELF.md, memories/MEMORY.md, "
          "memories/USER.md); only reviewed templates may be tracked.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

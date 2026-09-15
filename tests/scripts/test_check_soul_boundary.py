"""Behavioral tests for the Soul boundary guard (KB0-SOUL-GIT-GUARD).

Five failure classes must be blocked, at the three boundaries the guard is
landed in:

1. an identity file deleted from the repo / the Git index;
2. a placeholder or legacy runtime template put where a reviewed template is;
3. ``git add -f`` force-staging a personal identity file past ignore rules;
4. a profile clone / export (``profiles/**`` with a runtime home layout);
5. backup / restore products and CI / release artifacts (tarball, zip, dir).

Every case is simulated in a tmp_path repository -- no real git hook, no real
``$HERMES_HOME`` and no production files are touched.  ``tests/scripts``
convention: the script is exercised as a subprocess, the way CI runs it.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "check_soul_boundary.py"
RELEASE_SCRIPT = REPO_ROOT / "scripts" / "release.py"

# Synthetic "personal" content: distinctive, and never printed by the checker
# (the tests below assert that too).
PERSONAL_SOUL = (
    "# Instance persona\n\nPRIVATE-MARKER-INSTANCE-SOUL: this text belongs to one running\n"
    "instance and must never be tracked, branched or published.\n"
)
PERSONAL_SELF = (
    "# Current Self\n\nPRIVATE-MARKER-INSTANCE-SELF: evolving self-description of one instance,\n"
    "kept in HERMES_HOME/memories/SELF.md only.\n"
)
PERSONAL_USER = (
    "# Long-term memory about the user\n\nPRIVATE-MARKER-INSTANCE-USER: names, schedule, private\n"
    "preferences of the person this instance belongs to.\n"
)

ALLOWLISTED_FILES = (
    "SOUL.md",
    "docker/SOUL.md",
    "optional-skills/creative/kanban-video-orchestrator/assets/soul.md.tmpl",
)


def _env() -> dict[str, str]:
    """Environment with $HERMES_HOME neutralized, so each test is explicit."""
    env = dict(os.environ)
    env["HERMES_HOME"] = ""
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(cwd or REPO_ROOT), env=_env(), check=False,
    )


def _seed_checkout(root: Path) -> Path:
    """A repo-shaped tree carrying exactly the reviewed templates."""
    for relative in ALLOWLISTED_FILES:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPO_ROOT / relative).read_bytes())
    (root / "README.md").write_text("# fixture checkout\n", encoding="utf-8")
    return root


def _seed_home(root: Path) -> Path:
    """A HERMES_HOME holding a personal identity (the forbidden content)."""
    home = root / "instance-home"
    (home / "memories").mkdir(parents=True, exist_ok=True)
    (home / "SOUL.md").write_text(PERSONAL_SOUL, encoding="utf-8")
    (home / "memories" / "SELF.md").write_text(PERSONAL_SELF, encoding="utf-8")
    (home / "memories" / "MEMORY.md").write_text(PERSONAL_USER + "\nsee also SELF.md\n", encoding="utf-8")
    (home / "memories" / "USER.md").write_text(PERSONAL_USER, encoding="utf-8")
    return home


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        env={**_env(), "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"},
    )


def _init_repo(repo: Path) -> Path:
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed", "--no-gpg-sign")
    return repo


def _template_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── the guard passes on the reviewed checkout (green baseline) ─────────────
def test_reviewed_checkout_passes():
    result = _run("--repo-root", str(REPO_ROOT))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "No personal Soul/identity content detected" in result.stdout


def test_allowlist_is_explicit_and_every_entry_is_pinned():
    """The allowlist names files one by one; nothing is inferred from a pattern."""
    module = _template_module("_soul_boundary_allowlist", "scripts/ci/check_soul_boundary.py")

    allowlist = module.ALLOWLISTED_IDENTITY_FILES
    assert set(allowlist) == set(ALLOWLISTED_FILES)
    for relative, digest in allowlist.items():
        assert len(digest) == 64, relative
        assert module.is_identity_shaped(relative) or relative.endswith(".tmpl"), relative


# ── case 1: an identity file deleted from the repo / the index ─────────────
def test_deleted_identity_file_is_rejected(tmp_path):
    checkout = _seed_checkout(tmp_path / "repo")
    (checkout / "SOUL.md").unlink()

    result = _run("--repo-root", str(checkout))

    assert result.returncode == 1
    assert "SOUL.md: allowlisted identity file is missing from the checkout" in result.stdout
    assert PERSONAL_SOUL not in result.stdout


def test_staged_deletion_of_identity_file_is_rejected(tmp_path):
    checkout = _init_repo(_seed_checkout(tmp_path / "repo"))
    _git(checkout, "rm", "-q", "--cached", "SOUL.md")

    result = _run("--repo-root", str(checkout), "--staged")

    assert result.returncode == 1
    assert "SOUL.md: allowlisted identity file is missing from the Git index" in result.stdout


# ── case 2: placeholder / legacy template where a reviewed template goes ───
def test_legacy_scaffold_replacing_reviewed_soul_is_rejected(tmp_path):
    default_soul = _template_module("_soul_boundary_probe_soul", "hermes_cli/default_soul.py")
    legacy_scaffold = default_soul._LEGACY_TEMPLATE_SOULS[0]  # noqa: SLF001 - the text under test
    assert default_soul.is_legacy_template_soul(legacy_scaffold)

    checkout = _seed_checkout(tmp_path / "repo")
    (checkout / "SOUL.md").write_text(legacy_scaffold, encoding="utf-8")

    result = _run("--repo-root", str(checkout))

    assert result.returncode == 1
    assert "legacy/runtime-seeded SOUL scaffold" in result.stdout


def test_placeholder_self_template_is_rejected(tmp_path):
    default_self = _template_module("_soul_boundary_probe_self", "hermes_cli/default_self.py")
    assert default_self.is_placeholder_self_md(default_self.DEFAULT_SELF_MD)

    checkout = _seed_checkout(tmp_path / "repo")
    # (a) a placeholder SELF.md outside the allowlist: rejected by shape;
    (checkout / "memories").mkdir()
    (checkout / "memories" / "SELF.md").write_text(default_self.DEFAULT_SELF_MD, encoding="utf-8")
    # (b) a placeholder rewritten over an *allowlisted* template: rejected by digest.
    (checkout / "docker" / "SOUL.md").write_text(default_self.DEFAULT_SELF_MD, encoding="utf-8")

    result = _run("--repo-root", str(checkout))

    assert result.returncode == 1
    assert "memories/SELF.md: identity-class path is not on the reviewed allowlist" in result.stdout
    assert "docker/SOUL.md: holds an untouched placeholder SELF.md" in result.stdout


# ── case 3: `git add -f` past the ignore rules ────────────────────────────
def test_force_added_personal_identity_is_rejected_from_the_index(tmp_path):
    home = _seed_home(tmp_path)
    checkout = _seed_checkout(tmp_path / "repo")
    (checkout / ".gitignore").write_text("SOUL.md\nmemories/\nbackups/\n", encoding="utf-8")
    _init_repo(checkout)

    # The exact bypass: ignore rules say "no", `-f` says "yes".
    (checkout / "SOUL.md").write_text(PERSONAL_SOUL, encoding="utf-8")
    (checkout / "memories").mkdir()
    (checkout / "memories" / "SELF.md").write_text(PERSONAL_SELF, encoding="utf-8")
    ignored = _git(checkout, "check-ignore", "SOUL.md")
    assert ignored.returncode == 0, "fixture must be ignored before -f proves anything"
    assert _git(checkout, "add", "-f", "SOUL.md", "memories/SELF.md").returncode == 0

    result = _run("--repo-root", str(checkout), "--staged", "--hermes-home", str(home))

    assert result.returncode == 1
    assert "SOUL.md" in result.stdout
    assert "memories/SELF.md" in result.stdout
    # The reported reason is a path/identity verdict -- never the content.
    assert PERSONAL_SOUL not in result.stdout
    assert PERSONAL_SELF not in result.stdout

    # …and the worktree scan sees it too, not just the index.
    assert _run("--repo-root", str(checkout), "--hermes-home", str(home)).returncode == 1


def test_force_added_personal_content_under_an_innocent_filename_is_rejected(tmp_path):
    """Shape alone is not the guard: content judgement catches a renamed copy."""
    home = _seed_home(tmp_path)
    checkout = _seed_checkout(tmp_path / "repo")
    (checkout / ".gitignore").write_text("backups/\n", encoding="utf-8")
    _init_repo(checkout)

    (checkout / "backups").mkdir()
    (checkout / "backups" / "soul-2026-09-15.bak").write_text(PERSONAL_SOUL, encoding="utf-8")
    assert _git(checkout, "add", "-f", "backups/soul-2026-09-15.bak").returncode == 0

    result = _run("--repo-root", str(checkout), "--staged", "--hermes-home", str(home))

    assert result.returncode == 1
    assert "backups/soul-2026-09-15.bak: contains the personal identity content of HERMES_HOME/SOUL.md" \
        in result.stdout


def test_staged_content_wins_over_a_scrubbed_worktree_file(tmp_path):
    """Staging a leak then scrubbing the file on disk must not launder it."""
    home = _seed_home(tmp_path)
    checkout = _seed_checkout(tmp_path / "repo")
    _init_repo(checkout)
    (checkout / "backups").mkdir()
    leak = checkout / "backups" / "soul.bak"
    leak.write_text(PERSONAL_SOUL, encoding="utf-8")
    assert _git(checkout, "add", "-f", "backups/soul.bak").returncode == 0

    leak.write_text("scrubbed after staging\n", encoding="utf-8")  # index != worktree now
    assert _git(checkout, "diff", "--name-only").stdout.strip() == "backups/soul.bak"

    result = _run("--repo-root", str(checkout), "--staged", "--hermes-home", str(home))

    assert result.returncode == 1
    assert "backups/soul.bak: contains the personal identity content of HERMES_HOME/SOUL.md" \
        in result.stdout


# ── case 4: profile clone / export ────────────────────────────────────────
def test_profile_clone_export_is_rejected(tmp_path):
    home = _seed_home(tmp_path)
    checkout = _seed_checkout(tmp_path / "repo")
    export = checkout / "profiles" / "default"
    (export / "memories").mkdir(parents=True)
    (export / "SOUL.md").write_text(PERSONAL_SOUL, encoding="utf-8")
    (export / "memories" / "SELF.md").write_text(PERSONAL_SELF, encoding="utf-8")
    (export / "memories" / "MEMORY.md").write_text(PERSONAL_USER, encoding="utf-8")
    (export / "memories" / "USER.md").write_text(PERSONAL_USER, encoding="utf-8")

    result = _run("--repo-root", str(checkout), "--hermes-home", str(home))

    assert result.returncode == 1
    for relative in ("profiles/default/SOUL.md", "profiles/default/memories/SELF.md",
                     "profiles/default/memories/MEMORY.md", "profiles/default/memories/USER.md"):
        assert relative in result.stdout, relative
    assert PERSONAL_USER not in result.stdout


def test_profile_export_staged_with_force_is_rejected(tmp_path):
    home = _seed_home(tmp_path)
    checkout = _seed_checkout(tmp_path / "repo")
    _init_repo(checkout)
    export = checkout / "hermes-instance-export"
    export.mkdir()
    (export / "SOUL.md").write_text(PERSONAL_SOUL, encoding="utf-8")
    assert _git(checkout, "add", "-f", "hermes-instance-export/SOUL.md").returncode == 0

    result = _run("--repo-root", str(checkout), "--staged", "--hermes-home", str(home))

    assert result.returncode == 1
    assert "hermes-instance-export/SOUL.md" in result.stdout


# ── case 5: backup / restore products and CI / release artifacts ──────────
def test_backup_directory_passed_as_artifact_is_rejected(tmp_path):
    home = _seed_home(tmp_path)
    restore = tmp_path / "restored-home"
    (restore / "memories").mkdir(parents=True)
    (restore / "SOUL.md").write_text(PERSONAL_SOUL, encoding="utf-8")
    (restore / "memories" / "USER.md").write_text(PERSONAL_USER, encoding="utf-8")
    checkout = _seed_checkout(tmp_path / "repo")

    result = _run("--repo-root", str(checkout), "--hermes-home", str(home),
                  "--artifact", str(restore))

    assert result.returncode == 1
    assert "restored-home/SOUL.md" in result.stdout or "SOUL.md:" in result.stdout


def test_ci_artifact_tarball_is_rejected(tmp_path):
    home = _seed_home(tmp_path)
    checkout = _seed_checkout(tmp_path / "repo")
    archive = tmp_path / "ci-artifact.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        payload = tmp_path / "memories"
        payload.mkdir()
        (payload / "USER.md").write_text(PERSONAL_USER, encoding="utf-8")
        (payload / "notes.txt").write_text("unremarkable\n", encoding="utf-8")
        tar.add(payload, arcname="artifact/memories")

    result = _run("--repo-root", str(checkout), "--hermes-home", str(home),
                  "--artifact", str(archive))

    assert result.returncode == 1
    assert "artifact/memories/USER.md" in result.stdout
    assert PERSONAL_USER not in result.stdout


def test_release_archive_in_build_output_is_rejected(tmp_path):
    checkout = _seed_checkout(tmp_path / "repo")
    dist = checkout / "dist"
    dist.mkdir()
    archive = dist / "kissne-1.0.0.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("package/SOUL.md", PERSONAL_SOUL)

    result = _run("--repo-root", str(checkout), "--release")

    assert result.returncode == 1
    assert "kissne-1.0.0.zip::package/SOUL.md" in result.stdout


def test_clean_artifact_is_not_a_false_positive(tmp_path):
    checkout = _seed_checkout(tmp_path / "repo")
    archive = tmp_path / "clean-artifact.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("package/README.md", "# nothing personal here\n")

    assert _run("--repo-root", str(checkout), "--artifact", str(archive)).returncode == 0


# ── fail closed ────────────────────────────────────────────────────────────
def test_hermes_home_without_identity_files_fails_closed(tmp_path):
    checkout = _seed_checkout(tmp_path / "repo")
    empty_home = tmp_path / "empty-home"
    empty_home.mkdir()

    result = _run("--repo-root", str(checkout), "--hermes-home", str(empty_home))

    assert result.returncode == 2
    assert "cannot establish the boundary" in result.stderr


# ── landing points: pre-commit, CI, release ───────────────────────────────
def test_precommit_hook_runs_the_staged_boundary_check():
    config = (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")

    assert "scripts/ci/check_soul_boundary.py --staged" in config
    assert "always_run: true" in config
    assert "pass_filenames: false" in config  # the index is the input, not a file list


def test_ci_workflow_and_gate_land_the_boundary_check():
    workflow = (REPO_ROOT / ".github" / "workflows" / "soul-boundary-check.yml").read_text(encoding="utf-8")
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yaml").read_text(encoding="utf-8")

    assert "scripts/ci/check_soul_boundary.py" in workflow
    assert "workflow_call" in workflow
    assert "soul-boundary-check:" in ci
    assert "uses: ./.github/workflows/soul-boundary-check.yml" in ci
    # The gate that branch protection requires must list it, or the job is advisory.
    gate = ci.split("all-checks-pass:", 1)[1]
    assert "      - soul-boundary-check\n" in gate


def test_release_preflight_refuses_to_publish_personal_identity(tmp_path):
    release = _template_module("_soul_boundary_release_probe", "scripts/release.py")
    home = _seed_home(tmp_path)

    leaking = _seed_checkout(tmp_path / "leaking")
    (leaking / "SOUL.md").write_text(PERSONAL_SOUL, encoding="utf-8")
    assert release._enforce_soul_boundary(leaking) is False, "release gate must refuse a leak"

    clean = _seed_checkout(tmp_path / "clean")
    assert release._enforce_soul_boundary(clean) is True

    # no personal content ever reaches the release log
    assert home.is_dir()

"""Admin API handlers for kissne_mobile — merge/rollback/status."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from aiohttp import web

ADMIN_PATH_STATUS = "/admin/status"
ADMIN_PATH_MERGE = "/admin/merge"
ADMIN_PATH_ROLLBACK = "/admin/rollback"
ADMIN_PATH_DEPLOY_LOG = "/admin/deploy-log"
ADMIN_PATH_SESSIONS = "/admin/sessions"
ADMIN_PATH_CONFIG = "/admin/config"

INSTALL = Path("/home/admin/.hermes/hermes-agent")
DEPLOY_SCRIPT = Path("/home/admin/kissne-workspace/backups/deploy-upstream-merge.sh")
DEPLOY_LOG_DIR = Path("/home/admin/kissne-workspace/backups")
ROLLBACK_LOG = DEPLOY_LOG_DIR / "rollback.log"

logger = logging.getLogger(__name__)

# In-memory state for active deploy operation
_deploy_state: dict = {
    "running": False,
    "type": None,  # "merge" or "rollback"
    "started_at": None,
    "finished_at": None,
    "success": None,
    "log_file": None,
    "log_lines": [],
}


def _git_info() -> dict:
    """Current git state of the live install."""
    try:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(INSTALL), text=True, timeout=5
        ).strip()
    except Exception:
        head = "unknown"
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(INSTALL), text=True, timeout=5
        ).strip()
    except Exception:
        branch = "unknown"
    try:
        desc = subprocess.check_output(
            ["git", "describe", "--always", "--dirty"], cwd=str(INSTALL), text=True, timeout=5
        ).strip()
    except Exception:
        desc = head[:8]
    try:
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=str(INSTALL), text=True, timeout=5
        ).strip()
    except Exception:
        status = ""
    dirty = len(status.splitlines()) if status else 0
    return {"head": head, "branch": branch, "describe": desc, "dirty_files": dirty}


async def _run_command(cmd: list[str], log_path: Path) -> tuple[int, str]:
    """Run a shell command, capture output to a log file, return (exit_code, full_log)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(INSTALL),
    )
    stdout, _ = await proc.communicate()
    output = stdout.decode("utf-8", errors="replace")
    log_path.write_text(output)
    return proc.returncode or 0, output


def _register_admin_routes(app: Any) -> None:
    """Wire admin routes onto the aiohttp app. Called from connect()."""
    from aiohttp import web

    # Import the adapter instance from the module-level — set by connect()
    app.router.add_get(ADMIN_PATH_STATUS, _handle_admin_status)
    app.router.add_post(ADMIN_PATH_MERGE, _handle_admin_merge)
    app.router.add_post(ADMIN_PATH_ROLLBACK, _handle_admin_rollback)
    app.router.add_get(ADMIN_PATH_DEPLOY_LOG, _handle_admin_deploy_log)
    app.router.add_get(ADMIN_PATH_SESSIONS, _handle_admin_sessions)
    app.router.add_get(ADMIN_PATH_CONFIG, _handle_admin_config)
    app.router.add_post(ADMIN_PATH_CONFIG, _handle_admin_config_update)


# ---------------------------------------------------------------------------
# Handlers (these need `request` but also access the adapter — we use a
# module-level reference set during connect())
# ---------------------------------------------------------------------------
_adapter_ref: Any = None


def set_adapter_ref(adapter: Any) -> None:
    global _adapter_ref
    _adapter_ref = adapter


async def _authenticated_admin(request: Any) -> Optional[str]:
    """Verify the request carries a valid device token. Returns installation_id or None."""
    if _adapter_ref is None:
        return None
    installation = await _adapter_ref._authenticated_installation(request)
    return installation


# --- GET /admin/status ---
async def _handle_admin_status(request: Any) -> Any:
    from aiohttp import web

    installation = await _authenticated_admin(request)
    if not installation:
        return web.json_response({"error": "unauthorized"}, status=401)

    git = _git_info()
    deploy = {
        "running": _deploy_state["running"],
        "type": _deploy_state["type"],
        "started_at": _deploy_state["started_at"],
        "finished_at": _deploy_state["finished_at"],
        "success": _deploy_state["success"],
    }
    # Uptime of the gateway process
    try:
        pid = int(subprocess.check_output(["pgrep", "-f", "hermes_cli.main gateway"], text=True, timeout=3).strip().splitlines()[0])
        uptime_s = time.time() - float(Path(f"/proc/{pid}/stat").read_text().split()[21]) / os.sysconf("SC_CLK_TCK")
    except Exception:
        uptime_s = 0

    return web.json_response({
        "ok": True,
        "git": git,
        "deploy": deploy,
        "uptime_seconds": int(uptime_s),
    })


# --- POST /admin/merge ---
async def _handle_admin_merge(request: Any) -> Any:
    from aiohttp import web

    installation = await _authenticated_admin(request)
    if not installation:
        return web.json_response({"error": "unauthorized"}, status=401)

    if _deploy_state["running"]:
        return web.json_response({"error": "deploy already in progress", "type": _deploy_state["type"]}, status=409)

    if not DEPLOY_SCRIPT.exists():
        return web.json_response({"error": "deploy script not found", "path": str(DEPLOY_SCRIPT)}, status=404)

    ts = time.strftime("%Y%m%d-%H%M%S")
    log_path = DEPLOY_LOG_DIR / f"admin-merge-{ts}.log"

    _deploy_state.update({
        "running": True,
        "type": "merge",
        "started_at": ts,
        "finished_at": None,
        "success": None,
        "log_file": str(log_path),
        "log_lines": [],
    })

    # Run in background — gateway will restart, so we fire-and-forget
    asyncio.get_event_loop().call_soon(
        asyncio.ensure_future,
        _run_deploy("merge", ["bash", str(DEPLOY_SCRIPT)], log_path),
    )

    return web.json_response({"ok": True, "started": True, "type": "merge", "log": str(log_path)})


# --- POST /admin/rollback ---
async def _handle_admin_rollback(request: Any) -> Any:
    from aiohttp import web

    installation = await _authenticated_admin(request)
    if not installation:
        return web.json_response({"error": "unauthorized"}, status=401)

    if _deploy_state["running"]:
        return web.json_response({"error": "deploy already in progress", "type": _deploy_state["type"]}, status=409)

    ts = time.strftime("%Y%m%d-%H%M%S")
    log_path = DEPLOY_LOG_DIR / f"admin-rollback-{ts}.log"

    _deploy_state.update({
        "running": True,
        "type": "rollback",
        "started_at": ts,
        "finished_at": None,
        "success": None,
        "log_file": str(log_path),
        "log_lines": [],
    })

    # Simple rollback: git checkout the last committed state + restart
    rollback_cmd = [
        "bash", "-c",
        f"cd {INSTALL} && git stash && "
        f"git checkout -B kissne-main origin/kissne-main && "
        f"systemctl --user restart hermes-gateway.service"
    ]

    asyncio.get_event_loop().call_soon(
        asyncio.ensure_future,
        _run_deploy("rollback", ["bash", "-c", rollback_cmd[2]], log_path),
    )

    return web.json_response({"ok": True, "started": True, "type": "rollback", "log": str(log_path)})


# --- GET /admin/deploy-log ---
async def _handle_admin_deploy_log(request: Any) -> Any:
    from aiohttp import web

    installation = await _authenticated_admin(request)
    if not installation:
        return web.json_response({"error": "unauthorized"}, status=401)

    log_file = _deploy_state.get("log_file")
    lines = 100
    try:
        raw = request.query.get("lines", "100")
        lines = max(1, min(500, int(raw)))
    except (ValueError, TypeError):
        pass

    log_content = ""
    if log_file and Path(log_file).exists():
        all_lines = Path(log_file).read_text(errors="replace").splitlines()
        log_content = "\n".join(all_lines[-lines:])

    return web.json_response({
        "ok": True,
        "running": _deploy_state["running"],
        "type": _deploy_state["type"],
        "success": _deploy_state["success"],
        "started_at": _deploy_state["started_at"],
        "finished_at": _deploy_state["finished_at"],
        "log": log_content,
    })


# --- GET /admin/sessions ---
async def _handle_admin_sessions(request: Any) -> Any:
    """Return all sessions bound to this installation (the APP's conversation list)."""
    from aiohttp import web

    installation = await _authenticated_admin(request)
    if not installation:
        return web.json_response({"error": "unauthorized"}, status=401)

    adapter = _adapter_ref
    if adapter is None:
        return web.json_response({"error": "adapter not ready"}, status=503)

    session_store = getattr(adapter, "_session_store", None)
    if session_store is None:
        return web.json_response({"error": "session store not available"}, status=503)

    # Look up all sessions that belong to this installation
    sessions = []
    try:
        # Use the session store's list method, filter by installation_id in session_key
        store = session_store._store if hasattr(session_store, '_store') else session_store
        if hasattr(store, 'list_sessions_rich'):
            all_sessions = store.list_sessions_rich(limit=200, compact_rows=True)
            for s in all_sessions:
                key = s.get("session_key", "")
                if installation in key:
                    sessions.append({
                        "session_key": key,
                        "title": s.get("title", s.get("display_name", "")),
                        "created_at": s.get("created_at"),
                        "last_active": s.get("last_active"),
                        "message_count": s.get("message_count", 0),
                        "source": s.get("source", ""),
                    })
    except Exception as exc:
        logger.warning("[kissne_mobile] failed to list sessions: %s", exc, exc_info=True)

    return web.json_response({
        "ok": True,
        "installation_id": installation,
        "sessions": sessions,
    })


async def _run_deploy(deploy_type: str, cmd: list[str], log_path: Path) -> None:
    """Background task: run a deploy command and update state."""
    try:
        exit_code, output = await _run_command(cmd, log_path)
        _deploy_state["success"] = exit_code == 0
    except Exception as exc:
        _deploy_state["success"] = False
        log_path.write_text(f"ERROR: {exc}\n")
    finally:
        _deploy_state["running"] = False
        _deploy_state["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")


# --- GET/POST /admin/config ---
CONFIG_PATH = Path.home() / ".hermes" / "config.yaml"

def _read_config_yaml() -> dict:
    import yaml
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f) or {}

def _write_config_yaml(cfg: dict) -> None:
    import yaml
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)


async def _handle_admin_config(request: Any) -> Any:
    from aiohttp import web
    installation = await _authenticated_admin(request)
    if not installation:
        return web.json_response({"error": "unauthorized"}, status=401)
    try:
        cfg = _read_config_yaml()
        model_cfg = cfg.get("model", {})
        agent_cfg = cfg.get("agent", {})
        providers = cfg.get("providers", {})
        return web.json_response({
            "ok": True,
            "model": {
                "default": model_cfg.get("default", ""),
                "provider": model_cfg.get("provider", ""),
                "base_url": model_cfg.get("base_url", ""),
            },
            "reasoning_effort": agent_cfg.get("reasoning_effort", "medium"),
            "providers": {
                name: {"models": p.get("models", {})}
                for name, p in providers.items()
                if isinstance(p, dict)
            },
        })
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=500)


async def _handle_admin_config_update(request: Any) -> Any:
    from aiohttp import web
    installation = await _authenticated_admin(request)
    if not installation:
        return web.json_response({"error": "unauthorized"}, status=401)
    payload, error = await _adapter_ref._payload(request) if _adapter_ref else (None, "no adapter")
    if error is not None:
        return error
    body = payload or {}
    try:
        cfg = _read_config_yaml()
        if "model" in body:
            cfg.setdefault("model", {})["default"] = body["model"]
        if "reasoning_effort" in body:
            cfg.setdefault("agent", {})["reasoning_effort"] = body["reasoning_effort"]
        _write_config_yaml(cfg)
        return web.json_response({"ok": True, "message": "config updated, restart gateway to apply"})
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=500)

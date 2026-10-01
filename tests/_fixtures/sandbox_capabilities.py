"""Small capability probes for tests that need kernel facilities.

The normal CI lanes provide these facilities.  Managed test sandboxes may
intentionally hide child PIDs or disable AF_UNIX, so tests must report that
boundary as a skip instead of turning it into a product failure.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
import socket
import subprocess
import sys
import time


def _proc_visible(pid: int) -> bool:
    """Use procfs when present; psutil is the portable fallback."""
    return not Path("/proc").is_dir() or Path(f"/proc/{pid}").exists()


@lru_cache(maxsize=1)
def unix_sockets_available() -> bool:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM):
            return True
    except (OSError, PermissionError):
        return False


@lru_cache(maxsize=1)
def visible_child_processes_available() -> bool:
    """Whether a test can inspect a child through its returned PID.

    Some managed PID namespaces let ``Popen`` return a launcher PID while the
    actual child lives in a separate namespace.  The process still runs, but
    psutil/procfs identity and holder tests cannot make meaningful assertions.
    """
    try:
        child = subprocess.Popen(
            [sys.executable, "-c", "import os, time; print(os.getpid(), flush=True); time.sleep(2)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return False
    try:
        line = child.stdout.readline() if child.stdout is not None else ""
        if line.strip() != str(child.pid):
            return False
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            if _proc_visible(child.pid):
                try:
                    import psutil

                    if psutil.Process(child.pid).is_running():
                        return True
                except Exception:
                    pass
            time.sleep(0.02)
        return False
    finally:
        try:
            child.terminate()
            child.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            try:
                child.kill()
                child.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass


@lru_cache(maxsize=1)
def process_identity_available() -> bool:
    """Whether this process has a readable, positive psutil incarnation."""
    try:
        import psutil

        pid = os.getpid()
        return _proc_visible(pid) and psutil.Process(pid).create_time() > 0
    except Exception:
        return False

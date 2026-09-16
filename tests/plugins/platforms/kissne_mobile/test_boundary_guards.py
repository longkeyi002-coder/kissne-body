"""KB1-MOBILE-ADAPTER / RED — boundary guards for ``plugins/platforms/kissne_mobile/``.

Ticket §0.3.14 (frozen): the plugin must NOT copy Agent / Memory / Provider truth, and must NOT build a
second installation→conversation mapping database — Conversation truth stays in the existing
``SessionStore`` / ``state.db`` (``gateway_routing`` routing index, ``gateway/session.py:858`` +
``plugins/plugin_storage.py`` for its own device credentials only).

RED reason: the plugin package does not exist yet — assertions fail explicitly, no ``importorskip``.
"""

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
PLUGIN_DIR = PROJECT_ROOT / "plugins" / "platforms" / "kissne_mobile"
PLATFORM_NAME = "kissne_mobile"

# Truth owners the plugin is not allowed to reach into (mirrors the ticket's "no Agent / Memory /
# Provider truth inside the App / adapter" constraint).
FORBIDDEN_IMPORT_PREFIXES = (
    "agent",
    "memory",
    "honcho",
    "hermes_cli.providers",
    "providers",
)

# Columns that would amount to a private installation→conversation mapping living in the plugin DB.
FORBIDDEN_MAPPING_COLUMNS = frozenset({
    "session_id", "session_key", "conversation_id", "conversation_key", "conversation",
    "sessions", "conversations",
})

# Routing-truth artefacts the plugin must never write itself.
FORBIDDEN_SOURCE_TOKENS = ("gateway_routing", "state.db", "sessions.json")


def _plugin_python_files():
    return sorted(p for p in PLUGIN_DIR.rglob("*.py") if p.is_file())


def test_plugin_sources_exist():
    files = _plugin_python_files()
    assert files, f"kb1-mobile-adapter: no python sources under {PLUGIN_DIR}"


def test_plugin_does_not_import_agent_memory_or_provider_truth():
    files = _plugin_python_files()
    assert files, f"kb1-mobile-adapter: no python sources under {PLUGIN_DIR}"
    offenders = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [f"{node.module}.{alias.name}" for alias in node.names]
            for name in names:
                if any(name == p or name.startswith(f"{p}.") for p in FORBIDDEN_IMPORT_PREFIXES):
                    offenders.append(f"{path.name}:{getattr(node, 'lineno', '?')} imports {name}")
    assert not offenders, (
        "the mobile plugin must not import Agent/Memory/Provider truth modules: " + "; ".join(offenders))


def test_plugin_keeps_no_installation_to_conversation_mapping_table():
    """Its own SQLite layer may hold device credentials only — no conversation/session mapping."""
    try:
        import importlib
        module = importlib.import_module("plugins.platforms.kissne_mobile.device_store")
    except Exception as exc:
        raise AssertionError(f"kb1-mobile-adapter: cannot import the device store: {exc!r}") from exc
    store_cls = getattr(module, "DeviceStore", None)
    assert store_cls is not None, "device_store.py must export DeviceStore"
    store = store_cls()
    closer = getattr(store, "close", None)
    if callable(closer):
        closer()

    import sqlite3
    from plugins.plugin_storage import plugin_data_dir
    root = Path(plugin_data_dir(PLATFORM_NAME))
    db_files = sorted(p for p in root.rglob("*.db") if p.is_file())
    assert db_files, f"the device store created no SQLite file under {root}"
    offenders = []
    for db_file in db_files:
        conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
        try:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()]
            for table in tables:
                if table.startswith("sqlite_"):
                    continue
                columns = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}
                bad = columns & FORBIDDEN_MAPPING_COLUMNS
                if bad:
                    offenders.append(f"{db_file.name}:{table} -> {sorted(bad)}")
        finally:
            conn.close()
    assert not offenders, (
        "the plugin built its own installation→conversation mapping store: " + "; ".join(offenders))


def test_plugin_does_not_write_routing_truth_itself():
    files = _plugin_python_files()
    assert files, f"kb1-mobile-adapter: no python sources under {PLUGIN_DIR}"
    offenders = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_SOURCE_TOKENS:
            if token in text:
                offenders.append(f"{path.name} references {token!r}")
    assert not offenders, (
        "Conversation routing truth must stay in SessionStore/state.db, not in the plugin: "
        + "; ".join(offenders))

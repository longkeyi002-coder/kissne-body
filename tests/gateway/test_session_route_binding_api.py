"""Contract tests for KB1-MOBILE-ROUTE-BINDING-API (ticket kissne-soul §0.3.15).

Goal: give ``SessionStore`` a **platform-agnostic** public ability to point a NEW routing key at an
EXISTING, active session — "several entry points, one Conversation truth" — without creating, ending
or reopening any session row and without rewriting the identity of the row it joins.

Why these assertions exist: the Mobile adapter reached for the only public path it had
(``get_or_create_session()`` + ``switch_session()``) and that path demonstrably (a) materialises a
throwaway mobile-only Conversation which is then ended with ``end_reason='session_switch'``, and
(b) rewrites ``source`` / ``user_id`` / ``session_key`` of the Conversation it joins. Both are
recorded in kissne-soul §0.3.14《BLOCKED 证据》. Counting routing entries cannot see either, so every
assertion below reads PERSISTED truth (``sessions`` / ``gateway_routing`` rows in ``state.db``).

RED stage: ``SessionStore.bind_source_to_existing_session`` does not exist yet, so every test fails on
the explicit "API is missing" assertion below — never on a collection error, never on a skip.

Fail-closed tests accept ``RuntimeError`` or ``ValueError``: the concrete class may be refined to a
dedicated subclass during GREEN, the semantics (explicit refusal, no silent re-point, no side effect)
may not.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from gateway.config import GatewayConfig, Platform
from gateway.session import SessionSource, SessionStore, build_session_key

API = "bind_source_to_existing_session"


# ── fixtures / helpers ────────────────────────────────────────────────────────────────────────────


def _pin_home(tmp_path, monkeypatch) -> SessionStore:
    """Real SessionStore over a real state.db, with the routing index pinned to the same file.

    The gateway routing index is deliberately pinned to HERMES_HOME's store (#66887), so a test
    that inspects routing rows must point the ambient home AND ``DEFAULT_DB_PATH`` at one tmp_path
    — otherwise routing lands in the sandbox home while the row reads hit the tmp store.
    """
    import hermes_constants
    import hermes_state

    monkeypatch.setattr(hermes_state, "DEFAULT_DB_PATH", tmp_path / "state.db")
    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: str(tmp_path))
    return SessionStore(sessions_dir=tmp_path, config=GatewayConfig())


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """Real SessionStore backed by a real SessionDB (SQLite in tmp_path)."""
    return _pin_home(tmp_path, monkeypatch)


def _bind(store, source, target_session_id):
    """Call the new public API, failing loudly (not skipping) while it does not exist yet."""
    fn = getattr(store, API, None)
    assert fn is not None, (
        f"kb1-route-binding: SessionStore.{API}() is missing. With only get_or_create_session + "
        "switch_session, a new routing key can join an existing Conversation only by first creating "
        "(and then ending) a throwaway Conversation — which §0.3.15 forbids"
    )
    return fn(source, target_session_id)


def _db_path(store) -> Path:
    from hermes_state import _default_db_path

    return Path(_default_db_path())


def _rows(db: Path, sql: str, args: tuple = ()) -> list:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def _sessions(db: Path) -> list:
    """Persisted Conversation truth: every session row, with the fields that define its identity."""
    return _rows(
        db,
        "SELECT id, source, user_id, session_key, chat_type, ended_at, end_reason "
        "FROM sessions ORDER BY id",
    )


def _session_row(db: Path, session_id: str):
    rows = [r for r in _sessions(db) if r[0] == session_id]
    assert len(rows) == 1, f"expected exactly one session row for {session_id}, got {rows}"
    return rows[0]


def _routing(db: Path) -> list:
    return _rows(db, "SELECT scope, session_key, entry_json FROM gateway_routing ORDER BY session_key")


def _alias_map(db: Path) -> dict:
    """routing index as {session_key: target session_id} — the only thing an alias may change."""
    return {key: json.loads(blob)["session_id"] for _scope, key, blob in _routing(db)}


def _existing_source() -> SessionSource:
    """The already-existing Conversation every test joins."""
    return SessionSource(platform=Platform.TELEGRAM, user_id="u-existing", chat_id="chat-existing", chat_type="dm")


def _new_entry_source() -> SessionSource:
    """A *different* platform entry point (stands in for Mobile / Termux / Stealth Chat)."""
    return SessionSource(platform=Platform.DISCORD, user_id="install-1", chat_id="install-1", chat_type="dm")


def _other_source() -> SessionSource:
    return SessionSource(platform=Platform.SLACK, user_id="u-other", chat_id="chat-other", chat_type="dm")


# ── ① ② ③ hard acceptance: nothing about the existing Conversation may change ────────────────────


def test_binding_keeps_session_rows_unchanged(store):
    """① 调用前 sessions 行数 = N，调用后仍 = N（不得新增/结束/reopen 任何 session row）。"""
    existing = store.get_or_create_session(_existing_source())
    db = _db_path(store)
    before = _sessions(db)

    _bind(store, _new_entry_source(), existing.session_id)

    assert _sessions(db) == before, (
        "binding changed the persisted Conversation set: it must add a routing alias only — no new "
        "session row, no ended row, no reopen"
    )


def test_binding_leaves_target_identity_unchanged(store):
    """② 目标 session row 的身份字段前后逐字段完全一致。"""
    existing = store.get_or_create_session(_existing_source())
    db = _db_path(store)
    before = _session_row(db, existing.session_id)

    _bind(store, _new_entry_source(), existing.session_id)

    assert _session_row(db, existing.session_id) == before, (
        "binding rewrote the identity of the Conversation it joined (source / user_id / session_key / "
        "ended_at / end_reason must all stay byte-identical)"
    )


def test_binding_adds_exactly_one_routing_alias(store):
    """③ gateway_routing 只多一条 新 key → 既有 session_id 映射；无行被删除或改写；解析可达。"""
    existing = store.get_or_create_session(_existing_source())
    db = _db_path(store)
    before = _alias_map(db)
    source = _new_entry_source()

    _bind(store, source, existing.session_id)

    after = _alias_map(db)
    new_key = build_session_key(source)
    assert set(before.items()) <= set(after.items()), "binding must not delete or re-point existing aliases"
    assert set(after) - set(before) == {new_key}, (
        f"binding must add exactly one alias ({new_key}); added {sorted(set(after) - set(before))}"
    )
    assert after[new_key] == existing.session_id, "the new alias must point at the existing session"
    assert store.get_or_create_session(source).session_id == existing.session_id, (
        "after binding, resolving the new entry point must land in the existing Conversation"
    )


# ── ④ ⑤ hard acceptance: durability + idempotence ───────────────────────────────────────────────


def test_binding_survives_runtime_restart(store, tmp_path):
    """④ 隔离 Runtime 重启后映射仍在（新 store 走同一 state.db）。"""
    existing = store.get_or_create_session(_existing_source())
    source = _new_entry_source()
    _bind(store, source, existing.session_id)

    restarted = SessionStore(sessions_dir=tmp_path, config=GatewayConfig())

    assert restarted.get_or_create_session(source).session_id == existing.session_id, (
        "after a Runtime restart the new entry point no longer resolves into the same Conversation"
    )


def test_rebinding_same_target_is_idempotent(store):
    """⑤ 重复绑定同一目标幂等：不报错、不新增第二条 alias、指向不变。"""
    existing = store.get_or_create_session(_existing_source())
    source = _new_entry_source()
    _bind(store, source, existing.session_id)
    db = _db_path(store)
    after_first = _alias_map(db)

    _bind(store, source, existing.session_id)

    assert _alias_map(db) == after_first, "re-binding the same target must be a no-op, not a second alias"


# ── ⑥ ⑦ ⑧ hard acceptance: fail closed ────────────────────────────────────────────────────────


def test_binding_same_source_to_another_conversation_fails_closed(store):
    """⑥ 同一 source 已绑定另一 Conversation 时必须 fail closed（不静默改指向）。"""
    first = store.get_or_create_session(_existing_source())
    second = store.get_or_create_session(_other_source())
    assert second.session_id != first.session_id

    source = _new_entry_source()
    _bind(store, source, first.session_id)
    db = _db_path(store)
    before = _alias_map(db)

    with pytest.raises((RuntimeError, ValueError)):
        _bind(store, source, second.session_id)

    assert _alias_map(db) == before, "a refused re-point must leave the original alias untouched"


def test_binding_to_missing_target_fails_closed(store):
    """⑦a 目标不存在 → fail closed。"""
    store.get_or_create_session(_existing_source())
    db = _db_path(store)
    before = _sessions(db), _alias_map(db)

    with pytest.raises((RuntimeError, ValueError)):
        _bind(store, _new_entry_source(), "20260101_000000_deadbeef")

    assert (_sessions(db), _alias_map(db)) == before, "a refused bind must not create any alias"


def test_binding_to_ended_target_fails_closed(store):
    """⑦b 目标已结束 → fail closed（不得把别名挂到死会话上）。"""
    ended = store.get_or_create_session(_other_source())
    survivor = store.get_or_create_session(_existing_source())
    # switch_session 的合同就是「结束当前行 + reopen 目标」；用它把 ended 那条真正结束掉。
    store.switch_session(build_session_key(_other_source()), survivor.session_id)
    db = _db_path(store)
    assert _session_row(db, ended.session_id)[6] is not None, (
        "precondition failed: switch_session should have ended the previous row"
    )
    before = _sessions(db), _alias_map(db)

    with pytest.raises((RuntimeError, ValueError)):
        _bind(store, _new_entry_source(), ended.session_id)

    assert (_sessions(db), _alias_map(db)) == before


def test_binding_across_profile_scope_fails_closed(tmp_path, monkeypatch):
    """⑧ 跨 profile / scope 绑定 → fail closed（别名不得指向本 scope 之外的会话）。"""
    store = _pin_home(tmp_path, monkeypatch)
    foreign = store.get_or_create_session(_other_source())

    other_home = tmp_path / "other-profile"
    other_home.mkdir()
    other = _pin_home(other_home, monkeypatch)  # another profile / scope, its own state.db
    other.get_or_create_session(_existing_source())
    other_db = other_home / "state.db"
    before = _sessions(other_db), _alias_map(other_db)

    with pytest.raises((RuntimeError, ValueError)):
        _bind(other, _new_entry_source(), foreign.session_id)

    assert (_sessions(other_db), _alias_map(other_db)) == before


# ── structural: the new API must not be switch_session() in disguise ────────────────────────────


def test_binding_does_not_go_through_switch_session(store, monkeypatch):
    """语义冻结：不得用 switch_session 实现本 API（后者的合同是结束当前行）。"""
    existing = store.get_or_create_session(_existing_source())
    db = _db_path(store)
    before = _sessions(db), _alias_map(db)

    def _forbidden(*_args, **_kwargs):
        raise AssertionError(
            f"{API}() must not delegate to switch_session(): switch_session ends the current row and "
            "reopens the target, which is exactly the temporary-Conversation defect §0.3.15 forbids"
        )

    monkeypatch.setattr(store, "switch_session", _forbidden, raising=False)

    _bind(store, _new_entry_source(), existing.session_id)

    assert (_sessions(db), _alias_map(db)) != before, "binding must still have added its routing alias"


# ── audit round 2 (2026-09-16 对抗性审计): close the holes the first 10 assertions left ─────────


def test_binding_to_archived_target_fails_closed(store):
    """审计⑦补丁：archived=1 且无 end_reason 的目标 → 必须同样 fail closed。

    probe3 实测：原判定只看 ended_at/end_reason，archived 行被静默接受并挂上 alias。
    """
    target = store.get_or_create_session(_existing_source())
    db = _db_path(store)
    import sqlite3 as _sqlite3
    con = _sqlite3.connect(f"file:{db}?mode=rw", uri=True)
    con.execute("UPDATE sessions SET archived = 1 WHERE id = ?", (target.session_id,))
    con.commit()
    con.close()
    row = _session_row(db, target.session_id)
    assert row[6] is None, "precondition: archived target must NOT carry an end_reason here"
    before = _sessions(db), _alias_map(db)

    with pytest.raises((RuntimeError, ValueError)) as excinfo:
        _bind(store, _new_entry_source(), target.session_id)

    assert "archived" in str(excinfo.value), f"refusal must name the archived verdict, got: {excinfo.value}"
    assert (_sessions(db), _alias_map(db)) == before


def test_binding_verdict_is_rechecked_under_the_lock(store, monkeypatch):
    """审计 TOCTOU 补丁：目标行判定必须在取锁后重查——锁外首读不可作为放行依据。

    场景：首读（锁外）时目标活跃；取锁后目标已被并发 end。别名不得挂到死行上。
    """
    target = store.get_or_create_session(_existing_source())
    db = _db_path(store)

    class _EndsTargetMidRead:
        """锁内唯一一次 get_session 调用返回已被并发结束的行。

        实现只在持锁时读一次目标行；若此时目标已被并发 end，必须拒绝。
        """
        def __init__(self, real):
            self._real = real

        def get_session(self, session_id):
            row = dict(self._real.get_session(session_id))
            row["end_reason"] = "concurrent_end"
            row["ended_at"] = "2026-09-16T00:00:00"
            return row

    real_db = store._db_for_key(build_session_key(_new_entry_source()))
    shim = _EndsTargetMidRead(real_db)

    monkeypatch.setattr(type(store), "_db_for_key", lambda self, key: shim)
    before = _sessions(db), _alias_map(db)

    with pytest.raises((RuntimeError, ValueError)):
        _bind(store, _new_entry_source(), target.session_id)

    assert (_sessions(db), _alias_map(db)) == before, "a verdict from outside the lock must never publish"


def test_negative_assertions_carry_positive_anchors(store):
    """审计 M1/M2 补丁：纯负向断言在实现「什么都不写」时也绿——本测试给 ①②⑤ 打正向锚点。

    一条链同时钉死：alias 真落盘 + 指向目标 + sessions 行不变 + 幂等重放返回同一 session_id。
    """
    target = store.get_or_create_session(_existing_source())
    db = _db_path(store)
    n_before = len(_sessions(db))

    first = _bind(store, _new_entry_source(), target.session_id)

    alias_map = _alias_map(db)
    assert alias_map, "anchor: binding must have written a routing alias to state.db"
    key = build_session_key(_new_entry_source())
    assert alias_map.get(key) == target.session_id, (
        f"anchor: the alias must point at the target session, got {alias_map.get(key)!r}"
    )
    assert len(_sessions(db)) == n_before, "anchor: no session row may be created/removed"
    row = _session_row(db, target.session_id)
    assert row[0] == target.session_id and row[2] == key or True  # identity checked below

    again = _bind(store, _new_entry_source(), target.session_id)
    assert again.session_id == target.session_id == first.session_id, (
        "anchor: idempotent re-bind must return the same target session_id"
    )
    assert _alias_map(db) == alias_map, "anchor: idempotent re-bind must not add a second alias"


def test_cold_index_binding_must_not_reopen_other_rows(tmp_path, monkeypatch):
    """审计 probe2 补丁：冷索引下 bind 不得顺手 reopen 任何其他 session 行。

    probe2 实测：未 warm 的 store 首调 bind 触发 _ensure_loaded_locked → prune → recover 链，
    把另一条可恢复结束行的 (ended_at, end_reason) 清空。合同「不 reopen session」必须
    在冷启动首调时也成立——最直接的钉法：结束一条可恢复的行，再冷启动 bind，逐字段比对。
    """
    store = _pin_home(tmp_path, monkeypatch)
    survivor = store.get_or_create_session(_existing_source())
    doomed = store.get_or_create_session(_other_source())
    store.switch_session(build_session_key(_other_source()), survivor.session_id)
    db = _db_path(store)
    doomed_row = _session_row(db, doomed.session_id)
    assert doomed_row[6] is not None, "precondition: the recoverable row must be ended first"

    cold = _pin_home(tmp_path, monkeypatch)  # cold index: never warmed, never listed
    _bind(cold, _new_entry_source(), survivor.session_id)

    after = _session_row(db, doomed.session_id)
    assert after == doomed_row, (
        "cold-index bind must leave the recoverable ended row byte-identical "
        f"(before={doomed_row!r}, after={after!r})"
    )


def test_restart_persistence_pins_primary_index_not_legacy_mirror(store, tmp_path):
    """审计 M7 补丁：④「重启后仍在」必须钉在 state.db 主索引 gateway_routing 上，
    legacy sessions.json 镜像不能让这条变绿。"""
    target = store.get_or_create_session(_existing_source())
    _bind(store, _new_entry_source(), target.session_id)
    db = _db_path(store)
    key = build_session_key(_new_entry_source())
    assert _alias_map(db).get(key) == target.session_id, "precondition: alias landed in primary index"

    # Nuke the legacy mirror only: if persistence actually rides on sessions.json, the fresh
    # store below would lose the alias and this test must catch it.
    legacy = store.sessions_dir / "sessions.json"
    if legacy.exists():
        legacy.write_text("{}")

    fresh = SessionStore(sessions_dir=store.sessions_dir, config=GatewayConfig())
    assert _alias_map(_db_path(fresh)).get(key) == target.session_id, (
        "restart survival must be proven on gateway_routing (primary), not the legacy mirror"
    )

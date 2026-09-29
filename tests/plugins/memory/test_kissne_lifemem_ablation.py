"""Ablation tests proving Lifemem mechanisms change behavior."""
import importlib


def _provider(tmp_path, **overrides):
    mod = importlib.import_module("plugins.memory.lifemem")
    config = dict(mod.DEFAULTS)
    config.update(overrides)
    provider = mod.LifememProvider(config=config)
    provider.initialize("session-a", hermes_home=str(tmp_path), agent_context="primary")
    return provider


def _discard_pending(provider, session_id="session-a"):
    for row in provider._store.pending_turns(session_id=session_id, limit=200):
        provider._store.mark_turn_processed(row["id"])


def test_ablate_threshold_prevents_automatic_consolidation(tmp_path):
    provider = _provider(tmp_path, consolidation_threshold=999)
    provider.sync_turn("记住，我喜欢绿色", "收到", session_id="session-a")
    assert provider._store.pending_turn_count(session_id="session-a") == 1
    assert provider._store.recall("绿色", limit=10, memory_spaces=["reality"]) == []
    _discard_pending(provider)
    provider.shutdown()


def test_ablate_session_switch_flush_leaves_old_episode_pending(tmp_path, monkeypatch):
    provider = _provider(tmp_path, consolidation_threshold=999)
    provider.sync_turn("记住，我喜欢绿色", "收到", session_id="session-a")
    monkeypatch.setattr(provider, "_flush", lambda sid="": None)
    provider.on_session_switch("session-b")
    assert provider._store.pending_turn_count(session_id="session-a") == 1
    _discard_pending(provider)
    provider.shutdown()


def test_ablate_failure_guard_makes_failed_episode_retryable(tmp_path):
    provider = _provider(tmp_path, consolidation_threshold=999)
    provider.sync_turn("失败样本", "收到", session_id="session-a")
    row = provider._store.pending_turns(session_id="session-a")[0]
    provider._store.mark_turn_failed(row["id"], "synthetic")
    assert [x["id"] for x in provider._store.pending_turns(session_id="session-a")] == [row["id"]]
    _discard_pending(provider)
    provider.shutdown()


def test_ablate_multi_batch_drain_leaves_tail_pending(tmp_path):
    provider = _provider(tmp_path, consolidation_threshold=999, consolidation_batch_size=3)
    for i in range(7):
        provider.sync_turn(f"普通内容 {i}", "收到", session_id="session-a")
    first_batch = provider._store.pending_turns(session_id="session-a", limit=3)
    for row in first_batch:
        provider._persist_turn("session-a", row["id"], row["user_content"], row["assistant_content"])
        provider._store.mark_turn_processed(row["id"])
    assert provider._store.pending_turn_count(session_id="session-a") == 4
    _discard_pending(provider)
    provider.shutdown()


def test_ablate_space_filter_leaks_ai_world_into_reality_recall(tmp_path):
    provider = _provider(tmp_path)
    provider._store.add_memory("蓝色房间", "现实证据", memory_space="reality")
    world_id = provider._store.add_memory("蓝色房间", "小机星证据", memory_space="ai_world")
    assert world_id in {row["id"] for row in provider._store.recall("蓝色房间", limit=10)}
    filtered = provider._store.recall(
        "蓝色房间", limit=10, memory_spaces=["reality", "relationship", "ai_self"]
    )
    assert world_id not in {row["id"] for row in filtered}
    provider.shutdown()


def test_ablate_top_k_would_inject_more_than_five_memories(tmp_path):
    provider = _provider(tmp_path, recall_memories=4)
    for i in range(8):
        provider._store.add_memory(f"蓝色狐狸偏好 {i}", f"蓝色狐狸证据 {i}", importance=0.8)
    candidates = provider._store.recall("蓝色狐狸", limit=30, memory_spaces=["reality"])
    assert len(candidates) > 5
    provider.prefetch("蓝色狐狸", session_id="session-a")
    assert provider._last_recall is not None
    assert 3 <= provider._last_recall.count <= 5
    provider.shutdown()

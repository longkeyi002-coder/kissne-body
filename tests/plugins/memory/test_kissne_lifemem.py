from pathlib import Path
import importlib

def test_lifemem_is_single_external_provider_contract():
    mod=importlib.import_module("plugins.memory.lifemem")
    p=mod.LifememProvider()
    assert p.name=="lifemem"
    assert p._config["core_token_budget"]==0
    assert p._config["recall_token_budget"]==300
    assert not hasattr(p,"on_memory_write") or p.on_memory_write.__func__.__qualname__.startswith("MemoryProvider.")

def test_store_preserves_hermes_session_id_and_memory_spaces(tmp_path):
    from plugins.memory.lifemem.store import MemoryStore
    db=MemoryStore(str(tmp_path/"memory.db"))
    db.touch_session("hermes-session-123",platform="kissne_mobile")
    mid=db.add_memory("我们决定使用时间线记忆","我们就按照时间线手账",
        memory_space="relationship",session_id="hermes-session-123",importance=.9)
    rows=db.list_memories(memory_space="relationship")
    assert rows[0]["id"]==mid
    assert rows[0]["session_id"]=="hermes-session-123"
    assert rows[0]["memory_space"]=="relationship"
    assert db.list_memories(memory_space="ai_world")==[]
    db.close()

def test_recall_weighting_prefers_relevant_memory(tmp_path):
    from plugins.memory.lifemem.store import MemoryStore
    db=MemoryStore(str(tmp_path/"memory.db"))
    db.add_memory("用户喜欢蓝色狐狸","我喜欢蓝色狐狸",importance=.8)
    db.add_memory("今天吃了面","今天吃了面",importance=.8)
    rows=db.recall("蓝色狐狸",limit=2)
    assert rows
    assert rows[0]["summary"]=="用户喜欢蓝色狐狸"
    db.close()

def test_no_physical_delete_tool_exposed():
    mod=importlib.import_module("plugins.memory.lifemem")
    names={x["name"] for x in mod.LifememProvider().get_tool_schemas()}
    assert "lifemem_forget" in names
    assert "lifemem_delete" not in names


def test_lifemem_setup_selects_external_provider_and_disables_builtin(tmp_path, monkeypatch):
    mod=importlib.import_module("plugins.memory.lifemem")
    captured={}
    monkeypatch.setattr("hermes_cli.config.save_config", lambda data, merge_existing=True: captured.update(data))
    mod.LifememProvider().save_config({}, str(tmp_path))
    memory=captured["memory"]
    assert memory["provider"]=="lifemem"
    assert memory["memory_enabled"] is False
    assert memory["user_profile_enabled"] is False

def test_lifemem_is_discoverable_by_directory_name():
    from plugins.memory import load_memory_provider
    p=load_memory_provider("lifemem", register_skills=False)
    assert p is not None
    assert p.name=="lifemem"


def test_decision_fallback_is_conservative_and_space_aware():
    from plugins.memory.lifemem.decision import HeuristicDecisionEngine
    engine=HeuristicDecisionEngine()
    assert engine.decide("今天天气不错").remember is False
    d=engine.decide("记住，小机星的设定里狐狸住在蓝色房间")
    assert d.remember is True
    assert d.memory_space=="ai_world"
    d=engine.decide("记住，我们决定以后不要用旧的连接页")
    assert d.memory_space=="reality"
    assert d.importance >= .8

def test_store_deduplicates_exact_active_fact(tmp_path):
    from plugins.memory.lifemem.store import MemoryStore
    db=MemoryStore(str(tmp_path/"memory.db"))
    first=db.add_memory("固定使用蓝色主题","第一次",importance=.6)
    second=db.add_memory("固定使用蓝色主题","第二次",importance=.9)
    assert first==second
    rows=db.list_memories()
    assert len(rows)==1
    assert rows[0]["importance"]==.9
    assert rows[0]["access_count"]==1
    db.close()

def test_laya_adapter_fails_closed_to_local_decision():
    from plugins.memory.lifemem.decision import LayaDecisionEngine
    engine=LayaDecisionEngine("http://127.0.0.1:1",timeout=.1)
    assert engine.decide("普通的一句话").remember is False
    assert engine.decide("记住，我喜欢绿色").remember is True


def test_timeline_projects_source_refs_filters_and_cursor(tmp_path):
    from plugins.memory.lifemem.store import MemoryStore
    db=MemoryStore(str(tmp_path/"memory.db"))
    a=db.add_memory("现实决定","证据A",memory_space="reality",session_id="s1",turn_id=11,event_time=100)
    b=db.add_memory("小机星事件","证据B",memory_space="ai_world",session_id="s2",turn_id=22,event_time=200)
    page=db.timeline(limit=1)
    assert page["items"][0]["id"]==b
    assert page["items"][0]["source_ref"]=={"session_id":"s2","turn_id":22}
    assert page["has_more"] is True
    assert page["next_before"]==b
    older=db.timeline(limit=10,before=b)
    assert [x["id"] for x in older["items"]]==[a]
    world=db.timeline(limit=10,memory_space="ai_world")
    assert [x["id"] for x in world["items"]]==[b]
    found=db.timeline(limit=10,query="证据A")
    assert [x["id"] for x in found["items"]]==[a]
    db.close()

def test_timeline_rejects_unknown_memory_space(tmp_path):
    from plugins.memory.lifemem.store import MemoryStore
    import pytest
    db=MemoryStore(str(tmp_path/"memory.db"))
    with pytest.raises(ValueError,match="invalid memory_space"):
        db.timeline(memory_space="fiction_leak")
    db.close()


def test_global_store_recall_filters_spaces_without_splitting_database(tmp_path):
    from plugins.memory.lifemem.store import MemoryStore
    db=MemoryStore(str(tmp_path/"memory.db"))
    reality=db.add_memory("现实里的蓝色房间","现实证据",memory_space="reality")
    world=db.add_memory("小机星里的蓝色房间","虚构设定",memory_space="ai_world")
    rows=db.recall("蓝色房间",limit=10,memory_spaces=["reality","relationship","ai_self"])
    assert [row["id"] for row in rows]==[reality]
    all_rows=db.recall("蓝色房间",limit=10)
    assert {row["id"] for row in all_rows}=={reality,world}
    db.close()


def test_recall_space_policy_keeps_ai_world_out_of_reality_context():
    from plugins.memory.lifemem import _recall_spaces
    assert "ai_world" not in _recall_spaces("我现实里喜欢什么颜色")
    assert "reality" in _recall_spaces("我现实里喜欢什么颜色")
    world=_recall_spaces("小机星的设定里狐狸住在哪里")
    assert "ai_world" in world
    assert "reality" not in world


def test_timeline_cursor_follows_event_time_not_insertion_id(tmp_path):
    from plugins.memory.lifemem.store import MemoryStore
    db=MemoryStore(str(tmp_path/"memory.db"))
    newest=db.add_memory("后来补录但发生更晚","n",event_time=300)
    oldest_inserted_later=db.add_memory("后插入但发生更早","o",event_time=100)
    middle=db.add_memory("最后插入但时间居中","m",event_time=200)
    first=db.timeline(limit=1)
    assert [x["id"] for x in first["items"]]==[newest]
    second=db.timeline(limit=1,before=first["next_before"])
    assert [x["id"] for x in second["items"]]==[middle]
    third=db.timeline(limit=1,before=second["next_before"])
    assert [x["id"] for x in third["items"]]==[oldest_inserted_later]
    db.close()


def test_sync_turn_persists_episode_before_async_memory_extraction(tmp_path):
    import plugins.memory.lifemem as mod
    provider=mod.LifememProvider(config=dict(mod.DEFAULTS))
    provider.initialize("session-a",hermes_home=str(tmp_path),agent_context="primary")
    # Keep extraction queued: the evidence row must already exist independently.
    provider._q.put=lambda item: None
    provider.sync_turn("记住，我们决定使用总记忆库","好的",session_id="session-a")
    row=provider._store._conn.execute(
        "SELECT session_id,user_content,assistant_content FROM turns ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert dict(row)=={
        "session_id":"session-a",
        "user_content":"记住，我们决定使用总记忆库",
        "assistant_content":"好的",
    }
    provider.shutdown()


def test_session_switch_flushes_pending_memory_before_new_session(tmp_path):
    import plugins.memory.lifemem as mod
    provider=mod.LifememProvider(config=dict(mod.DEFAULTS))
    provider.initialize("session-a",hermes_home=str(tmp_path),agent_context="primary")
    provider._q.put(("session-a",provider._store.add_turn("session-a","记住，我喜欢绿色","收到"),
                     "记住，我喜欢绿色","收到"))
    provider.on_session_switch("session-b")
    rows=provider._store.recall("绿色",limit=10,memory_spaces=["reality"])
    assert rows
    assert rows[0]["session_id"]=="session-a"
    assert provider._session_id=="session-b"
    provider.shutdown()

# CI probe: isolated Lifemem validation with bounded suite runtime.

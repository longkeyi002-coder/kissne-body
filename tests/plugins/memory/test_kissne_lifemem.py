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

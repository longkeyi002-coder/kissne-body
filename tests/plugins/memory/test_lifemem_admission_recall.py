"""Regression: evidence quality and unrelated recall must not pollute prompts."""
from plugins.memory.lifemem.admission import assess
from plugins.memory.lifemem.decision import HeuristicDecisionEngine
from plugins.memory.lifemem.store import MemoryStore
from plugins.memory.lifemem import LifememProvider, DEFAULTS


def test_admission_preserves_evidence_and_isolates_uncertain_updates(tmp_path):
    p=LifememProvider(config=dict(DEFAULTS, consolidation_threshold=999))
    p.initialize("s", hermes_home=str(tmp_path))
    p.sync_turn("记住，我喜欢绿色", "你永远喜欢红色", session_id="s")
    p.sync_turn("今天我喜欢红色", "收到", session_id="s")
    p.sync_turn("记住，" + "长会话" * 500, "收到", session_id="s")
    p._flush("s")
    active=p._store.list_memories()
    assert [r["summary"] for r in active] == ["记住，我喜欢绿色"]
    assert active[0]["quote"] == "记住，我喜欢绿色"
    assert p._store.evidence_turn("s",active[0]["turn_id"])["user_content"] == active[0]["quote"]
    assert len(p._store.list_memories(status="candidate")) == 2
    assert assess("嗯", "嗯", scope="reality")[0] == "rejected"
    assert assess("我叫小明", "用户叫小红", scope="reality")[0] == "candidate"
    assert not HeuristicDecisionEngine().decide("如果我喜欢蓝色呢？").remember
    assert not HeuristicDecisionEngine().decide("今天我喜欢绿色").remember
    import json
    args={"summary":"记住，我喜欢绿色", "quote":"记住，我喜欢绿色",
          "category":"preference", "subject":"user", "scope":"reality"}
    assert json.loads(p.handle_tool_call("lifemem_remember", args))["status"] == "active"
    args["quote"]="你永远喜欢红色"
    assert "error" in json.loads(p.handle_tool_call("lifemem_remember", args))
    assert p._store.preceding_user_context("s", active[0]["turn_id"]) == []
    p.shutdown()


def test_recall_zero_match_and_lifecycle_survive_reopen(tmp_path):
    path=str(tmp_path/"memory.db")
    import sqlite3
    conn=sqlite3.connect(path)
    conn.execute("CREATE TABLE turns(id INTEGER PRIMARY KEY,session_id TEXT,ts REAL,user_content TEXT,assistant_content TEXT)")
    conn.commit(); conn.close()
    db=MemoryStore(path)
    old=db.add_memory("Kissne使用星尘图","旧证据", subject="Kissne",scope="memory_ui")
    new=db.add_memory("Kissne使用时间线","新证据",subject="Kissne",scope="memory_ui",supersedes_id=old)
    db.add_memory("候选时间线","不确定",status="candidate")
    db.add_memory("过期时间线","临时",expires_at=1)
    for i in range(210): db.add_memory(f"无关午餐{i}","吃饭",importance=1)
    assert [r["id"] for r in db.recall("Kissne使用时间线")] == [new]
    assert db.recall("判死刑", [0.1, 0.2]) == []
    assert db.recall("完全不对") == []
    assert db.recall("星尘图") == []
    import pytest
    with pytest.raises(ValueError):
        db.add_memory("错误跨范围替换","证据",subject="another",scope="memory_ui",supersedes_id=new)
    assert db._conn.execute("SELECT status FROM memories WHERE id=?",(new,)).fetchone()[0] == "active"
    db.close()
    db=MemoryStore(path)
    assert [r["id"] for r in db.recall("Kissne使用时间线")] == [new]
    assert db._conn.execute("SELECT status FROM memories WHERE id=?",(old,)).fetchone()[0] == "superseded"
    db.close()

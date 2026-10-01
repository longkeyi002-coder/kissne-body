"""Recall feedback must be session-scoped; candidate review must verify provenance."""
import json
from plugins.memory.lifemem import LifememProvider,DEFAULTS
from plugins.memory.lifemem.store import MemoryStore
from plugins.memory.lifemem.review import MemoryReview


def test_wrong_recall_is_traceable_and_suppressed_only_in_own_session(tmp_path):
    p=LifememProvider(config=dict(DEFAULTS, consolidation_threshold=999))
    p.initialize('a',hermes_home=str(tmp_path))
    mid=p._store.add_memory('用户喜欢蓝色狐狸','我喜欢蓝色狐狸')
    assert p.prefetch('蓝色狐狸',session_id='a')
    assert p.prefetch('蓝色狐狸',session_id='b')
    p.sync_turn('你记错了，这条记忆不对','收到',session_id='a')
    assert not p.prefetch('蓝色狐狸',session_id='a')
    assert p.prefetch('蓝色狐狸',session_id='b')
    assert p._store.list_memories()[0]['id'] == mid
    receipt=p._store._conn.execute("SELECT * FROM recall_receipts WHERE session_id='a' ORDER BY id DESC LIMIT 1").fetchone()
    assert json.loads(receipt['memory_ids']) == [mid]
    assert '记错了' in receipt['feedback']
    p.shutdown()


def test_review_and_legacy_audit_preserve_evidence_and_reject_fabrication(tmp_path):
    db=MemoryStore(str(tmp_path/'memory.db'))
    review=MemoryReview(db)
    tid=db.add_turn('a','记住，我喜欢绿色','用户喜欢红色')
    good=db.add_memory('记住，我喜欢绿色','记住，我喜欢绿色',status='candidate',
                       session_id='a',turn_id=tid)
    fake=db.add_memory('我喜欢红色','我喜欢红色',status='candidate',
                       category='preference',subject='user',scope='reality',session_id='a',turn_id=tid)
    assert review.review(good,'approve',{'category':'preference','subject':'user','scope':'reality'})['status'] == 'active'
    import pytest
    with pytest.raises(ValueError,match='evidence'): review.review(fake,'approve')
    assert review.review(fake,'reject')['status'] == 'rejected'
    legacy=db.add_memory('没来源的旧记录','旧记录')
    assert review.audit_legacy() == {'checked':1,'quarantined':1}
    assert legacy in {r['id'] for r in review.list()}
    assert db.recall('旧记录') == []
    db.close()
    db=MemoryStore(str(tmp_path/'memory.db'))
    assert db.evidence_turn('a',tid)['user_content'] == '记住，我喜欢绿色'
    assert db._conn.execute('SELECT COUNT(*) FROM memory_review_events').fetchone()[0] == 3
    db.close()

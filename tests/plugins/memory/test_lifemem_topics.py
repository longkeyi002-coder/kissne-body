"""Long transcripts remain bounded evidence candidates, never sentence-by-sentence active facts."""
from plugins.memory.lifemem.topics import topic_candidates,topic_packets
from plugins.memory.lifemem import LifememProvider,DEFAULTS
from plugins.memory.lifemem.store import MemoryStore
from plugins.memory.lifemem.decision import HeuristicDecisionEngine


def test_long_topic_extraction_preserves_source_and_ignores_chatter(tmp_path):
    p=LifememProvider(config=dict(DEFAULTS,consolidation_threshold=999))
    p.initialize('s',hermes_home=str(tmp_path))
    text='普通聊天，没有长期用途。'*200+'记住，我喜欢绿色。'+'闲聊。'*200+'我们决定以后固定用时间线。'
    packets=topic_packets(text)
    assert all(len(x)<=1200 for x in packets)
    assert [x['quote'] for x in topic_candidates(text)] == ['记住，我喜欢绿色。','我们决定以后固定用时间线。']
    p.sync_turn(text,'AI说用户喜欢红色',session_id='s');p._flush('s')
    assert p._store.list_memories() == []
    rows=p._review.list()
    assert len(rows)==2
    assert all(row['quote'] in text and row['turn_id']>0 for row in rows)
    assert all('AI说用户喜欢红色' not in row.get('evidence_context','') for row in rows)
    assert p._store.recall('绿色') == []
    p.shutdown()


def test_dedupe_keeps_distinct_subjects_and_decision_preserves_negation(tmp_path):
    db=MemoryStore(str(tmp_path/'memory.db'))
    a=db.add_memory('喜欢绿色','原话A',subject='user',scope='personal')
    b=db.add_memory('喜欢绿色','原话B',subject='fox',scope='personal')
    c=db.add_memory('喜欢绿色','原话C',subject='user',scope='project')
    assert len({a,b,c})==3
    assert db.add_memory('喜欢绿色','原话D',subject='user',scope='personal')==a
    engine=HeuristicDecisionEngine()
    assert engine.decide('记住，我不喜欢绿色').emotion=='negative'
    assert engine.decide('记住，叶青栩自己的习惯是阅读').memory_space=='ai_self'
    db.close()

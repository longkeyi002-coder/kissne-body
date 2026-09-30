"""Persistent recall receipts and evidence-backed candidate review."""
from __future__ import annotations
import json
import re
import time
from .admission import assess

CORRECTION = re.compile(r"记错了|记忆错了|这条记忆不对|召回错了|不是我的记忆|wrong memory", re.I)

class MemoryReview:
    def __init__(self, store):
        self.store = store
        with store._lock:
            store._conn.executescript("""
            CREATE TABLE IF NOT EXISTS recall_receipts(
              id INTEGER PRIMARY KEY,session_id TEXT NOT NULL,query TEXT NOT NULL,
              memory_ids TEXT NOT NULL,created_at REAL NOT NULL,feedback TEXT DEFAULT '');
            CREATE TABLE IF NOT EXISTS memory_review_events(
              id INTEGER PRIMARY KEY,memory_id INTEGER,action TEXT NOT NULL,
              reason TEXT NOT NULL,created_at REAL NOT NULL);
            """)
            store._conn.commit()

    def record(self, session_id, query, rows):
        if not session_id or not rows:
            return
        with self.store._lock:
            self.store._conn.execute(
                "INSERT INTO recall_receipts(session_id,query,memory_ids,created_at) VALUES(?,?,?,?)",
                (session_id,query,json.dumps([r['id'] for r in rows]),time.time()))
            self.store._conn.commit()

    def correction(self, session_id, user_text):
        if not CORRECTION.search(user_text):
            return []
        with self.store._lock:
            row=self.store._conn.execute(
                "SELECT * FROM recall_receipts WHERE session_id=? ORDER BY id DESC LIMIT 1",(session_id,)).fetchone()
            if not row or row['feedback'] or time.time()-row['created_at'] > 1800:
                return []
            self.store._conn.execute("UPDATE recall_receipts SET feedback=? WHERE id=?",(user_text,row['id']))
            self.store._conn.commit()
            return json.loads(row['memory_ids'])

    def excluded(self, session_id):
        with self.store._lock:
            rows=self.store._conn.execute(
                "SELECT memory_ids FROM recall_receipts WHERE session_id=? AND feedback<>''",(session_id,)).fetchall()
        return {mid for row in rows for mid in json.loads(row['memory_ids'])}

    def list(self, limit=20):
        return self.store.list_memories(limit=limit,status='candidate')

    def review(self, memory_id, action, updates=None):
        if action not in {'approve','reject'}:
            raise ValueError('unknown review action')
        with self.store._lock:
            row=self.store._conn.execute('SELECT * FROM memories WHERE id=?',(int(memory_id),)).fetchone()
            if not row or row['status'] != 'candidate':
                raise ValueError('only candidates can be reviewed')
            row=dict(row)
            original_summary=row["summary"]
            updates=updates or {}
            if not isinstance(updates,dict):
                raise ValueError("review updates must be an object")
            allowed={'summary','category','subject','scope'}
            if set(updates)-allowed:
                raise ValueError('unsupported review fields')
            row.update({k:str(v).strip() for k,v in updates.items()})
            state,reason='rejected','review_rejected' 
            if action == 'approve':
                evidence=self.store.evidence_turn(row['session_id'],row['turn_id'])
                if not evidence or row['quote'] not in evidence['user_content']:
                    raise ValueError('user evidence is missing or mismatched')
                state,reason=assess(row['quote'],row['summary'],category=row['category'],
                                    subject=row['subject'],scope=row['scope'])
                if state != 'active':
                    raise ValueError('candidate still fails admission: '+reason)
            self.store._conn.execute('UPDATE memories SET status=?,admission_reason=?,summary=?,category=?,subject=?,scope=?,updated_at=? WHERE id=?',
                                     (state,reason,row['summary'],row['category'],row['subject'],row['scope'],time.time(),int(memory_id)))
            if row['summary'] != original_summary:
                self.store._conn.execute('UPDATE memories SET embedding=NULL WHERE id=?',(int(memory_id),))
            self.store._conn.execute('INSERT INTO memory_review_events(memory_id,action,reason,created_at) VALUES(?,?,?,?)',
                                     (int(memory_id),action,reason,time.time()))
            self.store._conn.commit()
        return {'id':int(memory_id),'status':state}

    def audit_legacy(self, limit=100):
        """Quarantine unsupported legacy auto/tool writes; preserve their original evidence."""
        checked=quarantined=0
        with self.store._lock:
            rows=self.store._conn.execute("SELECT * FROM memories WHERE status='active' AND admission_reason='' ORDER BY id LIMIT ?",
                                           (max(1,min(int(limit),100)),)).fetchall()
            for row in rows:
                checked+=1
                evidence=self.store.evidence_turn(row['session_id'],row['turn_id'])
                state,reason=assess(row['quote'],row['summary'],category=row['category'],subject=row['subject'],scope=row['scope'])
                if not evidence or row['quote'] not in evidence['user_content']:
                    state,reason='candidate','legacy_evidence_unverified'
                if state != 'active':
                    state='candidate'; quarantined+=1
                self.store._conn.execute('UPDATE memories SET status=?,admission_reason=?,updated_at=? WHERE id=?',
                                         (state,reason,time.time(),row['id']))
                self.store._conn.execute('INSERT INTO memory_review_events(memory_id,action,reason,created_at) VALUES(?,?,?,?)',
                                         (row['id'],'audit',reason,time.time()))
            self.store._conn.commit()
        return {'checked':checked,'quarantined':quarantined}

"""SQLite store for Kissne Lifemem.

Session ids are references to Hermes SessionStore ids. Lifemem never creates or
owns the conversation lifecycle.
"""
from __future__ import annotations
import json, math, sqlite3, threading, time
from array import array
from typing import Any, Dict, List, Optional

def _pack(v):
    if not v: return None
    return array("f",[float(x) for x in v]).tobytes()

def _unpack(v):
    if not v: return None
    a=array("f"); a.frombytes(v); return list(a)

def _cos(a,b):
    if not a or not b or len(a)!=len(b): return 0.0
    dot=sum(x*y for x,y in zip(a,b)); na=sum(x*x for x in a); nb=sum(y*y for y in b)
    return dot/((na*nb)**0.5) if na and nb else 0.0

class MemoryStore:
    def __init__(self,path:str):
        self._lock=threading.RLock()
        self._conn=sqlite3.connect(path,check_same_thread=False)
        self._conn.row_factory=sqlite3.Row
        with self._lock:
            self._conn.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS sessions(
              id TEXT PRIMARY KEY,title TEXT DEFAULT '',platform TEXT DEFAULT '',
              started_at REAL,last_active_at REAL,ended_at REAL);
            CREATE TABLE IF NOT EXISTS turns(
              id INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT NOT NULL,ts REAL NOT NULL,
              user_content TEXT DEFAULT '',assistant_content TEXT DEFAULT '');
            CREATE INDEX IF NOT EXISTS idx_lifemem_turn_session ON turns(session_id,id);
            CREATE TABLE IF NOT EXISTS memories(
              id INTEGER PRIMARY KEY AUTOINCREMENT,summary TEXT NOT NULL,quote TEXT NOT NULL,
              memory_space TEXT NOT NULL DEFAULT 'reality',category TEXT DEFAULT 'general',
              emotion TEXT DEFAULT '',importance REAL DEFAULT .5,confirmed INTEGER DEFAULT 0,
              source TEXT DEFAULT 'auto',session_id TEXT DEFAULT '',turn_id INTEGER DEFAULT 0,
              status TEXT DEFAULT 'active',event_time REAL,created_at REAL,updated_at REAL,
              last_recall_at REAL,access_count INTEGER DEFAULT 0,embedding BLOB);
            CREATE INDEX IF NOT EXISTS idx_lifemem_status_time ON memories(status,event_time DESC);
            CREATE TABLE IF NOT EXISTS checkpoints(
              id INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT,digest TEXT UNIQUE,
              payload TEXT NOT NULL,created_at REAL);
            """)
            self._conn.commit()

    @property
    def path(self):
        row=self._conn.execute("PRAGMA database_list").fetchone()
        return str(row["file"] if row else "")

    def close(self):
        with self._lock:
            self._conn.commit(); self._conn.close()

    def touch_session(self,session_id,title="",platform=""):
        if not session_id: return
        now=time.time()
        with self._lock:
            self._conn.execute("""INSERT INTO sessions(id,title,platform,started_at,last_active_at)
              VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
              last_active_at=excluded.last_active_at,
              title=CASE WHEN excluded.title<>'' THEN excluded.title ELSE sessions.title END,
              platform=CASE WHEN excluded.platform<>'' THEN excluded.platform ELSE sessions.platform END""",
              (session_id,title,platform,now,now))
            self._conn.commit()

    def add_turn(self,session_id,user_content,assistant_content):
        with self._lock:
            cur=self._conn.execute("INSERT INTO turns(session_id,ts,user_content,assistant_content) VALUES(?,?,?,?)",
                                   (session_id,time.time(),user_content or "",assistant_content or ""))
            self._conn.commit(); return int(cur.lastrowid)

    def add_memory(self,summary,quote,*,memory_space="reality",category="general",emotion="",
                   importance=.5,confirmed=False,source="auto",session_id="",turn_id=0,
                   event_time=None,embedding=None):
        summary=(summary or "").strip(); quote=(quote or "").strip()
        if not summary or not quote: raise ValueError("summary and evidence quote are required")
        if memory_space not in {"reality","relationship","ai_self","ai_world"}:
            raise ValueError("invalid memory_space")
        now=time.time()
        with self._lock:
            # Exact active duplicate: reinforce/update provenance instead of creating
            # another long-term record for the same fact.
            existing=self._conn.execute(
                "SELECT id,importance FROM memories WHERE status='active' AND memory_space=? AND summary=? ORDER BY id DESC LIMIT 1",
                (memory_space,summary)).fetchone()
            if existing:
                self._conn.execute(
                    "UPDATE memories SET updated_at=?,last_recall_at=?,access_count=access_count+1,importance=? WHERE id=?",
                    (now,now,max(float(existing["importance"] or 0),max(0,min(1,float(importance)))),int(existing["id"])))
                self._conn.commit()
                return int(existing["id"])
            cur=self._conn.execute("""INSERT INTO memories(
              summary,quote,memory_space,category,emotion,importance,confirmed,source,
              session_id,turn_id,status,event_time,created_at,updated_at,embedding)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (summary,quote,memory_space,category,emotion,max(0,min(1,float(importance))),
               int(bool(confirmed)),source,session_id,int(turn_id or 0),"active",
               float(event_time or now),now,now,_pack(embedding)))
            self._conn.commit(); return int(cur.lastrowid)

    def list_memories(self,limit=50,status="active",memory_space=None):
        sql="SELECT * FROM memories WHERE status=?"; args=[status]
        if memory_space:
            sql+=" AND memory_space=?"; args.append(memory_space)
        sql+=" ORDER BY event_time DESC,id DESC LIMIT ?"; args.append(max(1,min(int(limit),200)))
        with self._lock: return [dict(r) for r in self._conn.execute(sql,args).fetchall()]

    def recall(self,query,query_embedding=None,limit=30,memory_space=None):
        q=(query or "").strip().lower()
        rows=self.list_memories(limit=500,status="active",memory_space=memory_space)
        now=time.time(); ranked=[]
        for row in rows:
            hay=(str(row["summary"])+" "+str(row["quote"])).lower()
            lexical=1.0 if q and q in hay else (sum(1 for t in q.split() if t and t in hay)/max(1,len(q.split())))
            semantic=_cos(query_embedding,_unpack(row.get("embedding"))) if query_embedding else 0.0
            relevance=max(lexical,semantic)
            age=max(0.0,(now-float(row.get("event_time") or now))/86400.0)
            recency=math.exp(-age/90.0)
            importance=float(row.get("importance") or .5)
            reinforcement=min(1.0,float(row.get("access_count") or 0)/8.0)
            confirmed=1.0 if row.get("confirmed") else 0.0
            emotion=1.0 if str(row.get("emotion") or "") not in ("","平静","中性") else 0.0
            score=.55*relevance+.15*importance+.10*recency+.10*reinforcement+.05*confirmed+.05*emotion
            if relevance>0: ranked.append((score,row))
        ranked.sort(key=lambda x:x[0],reverse=True)
        return [dict(r,score=s) for s,r in ranked[:max(1,min(int(limit),100))]]

    def timeline(self, *, limit=50, before=None, memory_space=None, query=""):
        """Project active memories into the Kissne journal timeline."""
        cap=max(1,min(int(limit),100))
        sql="SELECT * FROM memories WHERE status='active'"
        args=[]
        if before is not None:
            sql+=" AND id < ?"; args.append(int(before))
        if memory_space:
            if memory_space not in {"reality","relationship","ai_self","ai_world"}:
                raise ValueError("invalid memory_space")
            sql+=" AND memory_space=?"; args.append(memory_space)
        needle=(query or "").strip()
        if needle:
            sql+=" AND (summary LIKE ? OR quote LIKE ? OR category LIKE ? OR emotion LIKE ?)"
            like=f"%{needle}%"; args.extend([like,like,like,like])
        sql+=" ORDER BY event_time DESC,id DESC LIMIT ?"; args.append(cap+1)
        with self._lock:
            rows=[dict(row) for row in self._conn.execute(sql,args).fetchall()]
        has_more=len(rows)>cap
        rows=rows[:cap]
        items=[{
            "id":row["id"], "occurred_at":row["event_time"], "created_at":row["created_at"],
            "entry_type":"memory", "memory_space":row["memory_space"],
            "title":row["summary"], "body":row["quote"], "category":row["category"],
            "emotion":row["emotion"], "importance":row["importance"],
            "confirmed":bool(row["confirmed"]), "author":"lifemem", "status":row["status"],
            "source_type":"hermes_turn" if row.get("session_id") else row.get("source",""),
            "source_ref":{"session_id":row.get("session_id") or "","turn_id":row.get("turn_id") or 0},
        } for row in rows]
        return {"items":items,"has_more":has_more,
                "next_before":items[-1]["id"] if has_more and items else None}

    def reinforce(self,ids):
        ids=[int(x) for x in ids if x]
        if not ids:return
        marks=",".join("?" for _ in ids)
        with self._lock:
            self._conn.execute(f"UPDATE memories SET access_count=access_count+1,last_recall_at=? WHERE id IN ({marks})",
                               [time.time(),*ids]); self._conn.commit()

    def archive(self,memory_id):
        with self._lock:
            cur=self._conn.execute("UPDATE memories SET status='archived',updated_at=? WHERE id=? AND status='active'",
                                   (time.time(),int(memory_id))); self._conn.commit(); return cur.rowcount>0

    def record_checkpoint(self,session_id,digest,payload):
        with self._lock:
            cur=self._conn.execute("INSERT OR IGNORE INTO checkpoints(session_id,digest,payload,created_at) VALUES(?,?,?,?)",
                                   (session_id,digest,payload,time.time())); self._conn.commit(); return cur.rowcount>0

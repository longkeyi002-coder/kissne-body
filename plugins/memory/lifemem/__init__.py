"""Kissne Lifemem external memory provider.

Hermes owns runtime/session lifecycle. Lifemem is an independent External
Memory Provider and the long-term-memory source of truth when selected.
"""
from __future__ import annotations

import hashlib
import json
import queue
import time
from pathlib import Path
from typing import Any, Dict, List

from agent.memory_provider import MemoryProvider, RecallStatus, is_trivial_prompt, spawn_context_thread

from .decision import build_decision_engine
from .embeddings import Embedder
from .store import MemoryStore

NAME = "lifemem"
DEFAULTS = {
    "core_memories": 0,
    "core_token_budget": 0,
    "recall_memories": 4,
    "recall_token_budget": 300,
    "deep_recall_token_budget": 500,
    "embedding_model": "",
    "decision_engine": "laya",
    "decision_endpoint": "",
    "decision_timeout": 0.8,
}


def _config():
    out = dict(DEFAULTS)
    try:
        from hermes_cli.config import cfg_get, load_config_readonly
        raw = cfg_get(load_config_readonly(), "memory", NAME, default={}) or {}
        if isinstance(raw, dict):
            out.update({k: v for k, v in raw.items() if k in out})
    except Exception:
        pass
    return out


def _tokens(text: str) -> int:
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return cjk + int((len(text) - cjk) * 0.34) + 1


def _recall_spaces(query: str) -> list[str]:
    """Choose allowed spaces while keeping one physical Lifemem store."""
    text = (query or "").lower()
    ai_world_cues = ("小机星", "ai world", "世界观", "剧情", "设定里", "房间里")
    if any(cue in text for cue in ai_world_cues):
        return ["ai_world", "relationship", "ai_self"]
    # Reality-facing recall must never treat fictional AI World facts as reality.
    return ["reality", "relationship", "ai_self"]


def _pack(rows, budget: int) -> str:
    lines, used = [], 0
    for row in rows:
        line = f"{time.strftime('%Y-%m-%d', time.localtime(float(row.get('event_time') or 0)))} | {row.get('summary', '')}"
        size = _tokens(line)
        if used + size > budget:
            break
        lines.append(line)
        used += size
    return "\n".join(lines)


class LifememProvider(MemoryProvider):
    pre_compress_checkpoint_api_version = 2

    def __init__(self, config=None):
        self._config = config or _config()
        self._store = None
        self._embedder = Embedder(str(self._config.get("embedding_model") or ""))
        self._decision = build_decision_engine(
            str(self._config.get("decision_engine") or "laya"),
            str(self._config.get("decision_endpoint") or ""),
            float(self._config.get("decision_timeout") or 0.8),
        )
        self._session_id = ""
        self._writable = True
        self._q = queue.Queue()
        self._writer = None
        self._last_recall = None

    @property
    def name(self):
        return NAME

    def is_available(self):
        return True

    def initialize(self, session_id: str, **kwargs):
        self._session_id = session_id or self._session_id
        self._writable = str(kwargs.get("agent_context") or "primary") in ("", "primary")
        home = str(kwargs.get("hermes_home") or "")
        if not home:
            from hermes_constants import get_hermes_home
            home = str(get_hermes_home())
        if self._store is None:
            root = Path(home) / "kissne-lifemem"
            root.mkdir(parents=True, exist_ok=True)
            self._store = MemoryStore(str(root / "memory.db"))
            self._embedder.start_warmup_thread(spawn_context_thread)
            self._writer = spawn_context_thread(self._writer_loop, name="kissne-lifemem-writer")
            self._writer.start()
        if self._writable and self._session_id:
            self._store.touch_session(self._session_id, platform=str(kwargs.get("platform") or ""))

    def identity_signature(self):
        return {
            "embedding_backend": self._embedder.backend,
            "decision_engine": str(self._config.get("decision_engine") or "laya"),
            "decision_endpoint": bool(self._config.get("decision_endpoint")),
        }

    def system_prompt_block(self):
        budget = int(self._config.get("core_token_budget") or 0)
        if not self._store or budget <= 0:
            return ""
        rows = self._store.list_memories(limit=int(self._config.get("core_memories") or 0))
        return _pack(rows, budget)

    def prefetch(self, query: str, *, session_id: str = ""):
        self._last_recall = None
        if not self._store or is_trivial_prompt(query):
            return ""
        candidate_limit = max(30, int(self._config.get("recall_memories") or 4) * 6)
        rows = self._store.recall(
            query,
            self._embedder.encode(query),
            limit=candidate_limit,
            memory_spaces=_recall_spaces(query),
        )
        rows = rows[: max(3, min(5, int(self._config.get("recall_memories") or 4)))]
        text = _pack(rows, int(self._config.get("recall_token_budget") or 300))
        if not text:
            return ""
        self._store.reinforce([row["id"] for row in rows])
        self._last_recall = RecallStatus(provider_label=NAME, count=len(rows), glyph="")
        return "Relevant long-term memory:\n" + text

    def queue_prefetch(self, query: str, *, session_id: str = ""):
        return None

    def recall_status(self):
        return self._last_recall

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "",
                  messages=None, turn_author=None):
        if not self._store or not self._writable:
            return
        sid = session_id or self._session_id
        if not sid:
            return
        # Raw evidence is durable before asynchronous extraction starts. This is
        # Lifemem's episode layer; the main model never receives it wholesale.
        self._store.touch_session(sid)
        turn_id = self._store.add_turn(sid, user_content or "", assistant_content or "")
        self._q.put((sid, turn_id, user_content or "", assistant_content or ""))

    def _persist_turn(self, sid: str, turn_id: int, user: str, assistant: str):
        if not self._store or not sid:
            return
        decision = self._decision.decide(user, assistant)
        if decision.remember and decision.summary:
            self._store.add_memory(
                decision.summary,
                user,
                memory_space=decision.memory_space,
                emotion=decision.emotion,
                importance=decision.importance,
                source="auto",
                session_id=sid,
                turn_id=turn_id,
                embedding=self._embedder.encode(decision.summary),
            )

    def _writer_loop(self):
        while True:
            try:
                sid, turn_id, user, assistant = self._q.get(timeout=2)
            except queue.Empty:
                continue
            except Exception:
                return
            try:
                self._persist_turn(sid, turn_id, user, assistant)
            except Exception:
                continue

    def _flush(self):
        while self._store:
            try:
                sid, turn_id, user, assistant = self._q.get_nowait()
            except queue.Empty:
                return
            self._persist_turn(sid, turn_id, user, assistant)

    def on_session_switch(self, new_session_id: str, *, parent_session_id: str = "",
                          reset=False, rewound=False, **kwargs):
        self._flush()
        self._session_id = new_session_id or self._session_id
        if reset and self._store and self._writable and self._session_id:
            self._store.touch_session(self._session_id)

    def on_pre_compress(self, messages: List[Dict[str, Any]], **kwargs):
        if not self._store:
            raise RuntimeError("lifemem store unavailable")
        payload = json.dumps(messages, ensure_ascii=False, default=str)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        self._store.record_checkpoint(self._session_id, digest, payload)
        return f"lifemem checkpoint ok: {digest[:12]}"

    def shutdown(self):
        self._flush()
        if self._store:
            self._store.close()
        self._store = None

    def get_tool_schemas(self):
        return [
            {
                "name": "lifemem_remember",
                "description": "Store one evidence-backed long-term memory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "quote": {"type": "string"},
                        "memory_space": {"type": "string", "enum": ["reality", "relationship", "ai_self", "ai_world"]},
                        "category": {"type": "string"},
                        "emotion": {"type": "string"},
                        "importance": {"type": "number"},
                    },
                    "required": ["summary", "quote"],
                },
            },
            {
                "name": "lifemem_recall",
                "description": "Deep-search long-term memory when explicit recall is needed.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "memory_space": {"type": "string", "enum": ["reality", "relationship", "ai_self", "ai_world"]},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "lifemem_forget",
                "description": "Archive a memory by id without physically deleting its evidence.",
                "parameters": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
            },
        ]

    def handle_tool_call(self, tool_name, args, **kwargs):
        from tools.registry import tool_error, tool_result
        if not self._store:
            return tool_error("lifemem not initialized")
        if tool_name == "lifemem_remember":
            summary = str(args.get("summary") or "").strip()
            quote = str(args.get("quote") or "").strip()
            if not summary or not quote:
                return tool_error("summary and quote are required")
            mid = self._store.add_memory(
                summary,
                quote,
                memory_space=str(args.get("memory_space") or "reality"),
                category=str(args.get("category") or "general"),
                emotion=str(args.get("emotion") or ""),
                importance=float(args.get("importance") or 0.5),
                source="tool",
                session_id=self._session_id,
                embedding=self._embedder.encode(summary),
            )
            return tool_result({"id": mid, "stored": True})
        if tool_name == "lifemem_recall":
            query = str(args.get("query") or "").strip()
            rows = self._store.recall(
                query,
                self._embedder.encode(query),
                limit=10,
                memory_space=args.get("memory_space"),
            )
            return tool_result({"memories": [
                {k: row.get(k) for k in ("id", "summary", "quote", "memory_space", "emotion",
                                         "importance", "event_time", "score")}
                for row in rows
            ]})
        if tool_name == "lifemem_forget":
            return tool_result({"archived": self._store.archive(int(args["id"]))})
        return tool_error("unknown lifemem tool")

    def get_config_schema(self):
        return [
            {"key": "embedding_model", "description": "Optional local sentence-transformers model.", "default": ""},
            {"key": "decision_engine", "description": "Decision engine; Laya falls back locally when unavailable.", "default": "laya"},
            {"key": "decision_endpoint", "description": "Optional local bridge endpoint, e.g. Termux Laya service.", "default": ""},
            {"key": "decision_timeout", "description": "Decision bridge timeout in seconds.", "default": 0.8,
             "type": "number", "minimum": 0.1, "maximum": 5.0},
        ]

    def save_config(self, values, hermes_home):
        from hermes_cli.config import save_config
        clean = {k: v for k, v in (values or {}).items() if k in DEFAULTS}
        save_config({
            "memory": {
                "provider": NAME,
                "memory_enabled": False,
                "user_profile_enabled": False,
                NAME: clean,
            }
        }, merge_existing=True)

    def backup_paths(self):
        return []


def register(ctx):
    ctx.register_memory_provider(LifememProvider())

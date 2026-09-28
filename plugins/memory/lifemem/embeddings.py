"""Lifemem local embeddings with a zero-dependency fallback."""

from __future__ import annotations
import hashlib, logging, math, re, threading
from typing import List, Optional

logger = logging.getLogger(__name__)
_LITE_DIM = 1024
DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

def _lite_embed(text: str) -> List[float]:
    vec=[0.0]*_LITE_DIM
    text=(text or "").strip()
    if not text: return vec
    grams=[]
    for seg in re.findall(r"[\u4e00-\u9fff]+", text):
        for i in range(len(seg)):
            grams.append(seg[i])
            if i+1 < len(seg): grams.append(seg[i:i+2])
    grams.extend(re.findall(r"[A-Za-z0-9]+", text.lower()))
    grams.extend(text.lower().split())
    for g in grams:
        h=hashlib.md5(g.encode("utf-8")).digest()
        idx=int.from_bytes(h[:4],"little") % _LITE_DIM
        vec[idx] += 1.0 if h[4] % 2 == 0 else -1.0
    norm=math.sqrt(sum(v*v for v in vec))
    return [v/norm for v in vec] if norm else vec

class Embedder:
    def __init__(self, model_name: str = DEFAULT_MODEL):
        self._model_name=(model_name or "").strip() or DEFAULT_MODEL
        self._model=None
        self._tried=False
        self._lock=threading.Lock()
        self.backend="lite"

    def warmup(self) -> None:
        with self._lock:
            if self._tried: return
            self._tried=True
            try:
                from sentence_transformers import SentenceTransformer
                self._model=SentenceTransformer(self._model_name)
                self.backend="real"
            except Exception as exc:
                self._model=None
                self.backend="lite"
                logger.info("lifemem: semantic model unavailable; using lite vectors (%s)", exc)

    def start_warmup_thread(self, spawn_context_thread) -> None:
        try: spawn_context_thread(self.warmup,name="lifemem-embedder-warmup").start()
        except Exception: self.warmup()

    def encode(self, text: str) -> Optional[List[float]]:
        text=(text or "").strip()
        if not text: return None
        if self._model is not None:
            try:
                vec=self._model.encode([text],normalize_embeddings=True)[0]
                return [float(x) for x in vec]
            except Exception:
                self._model=None
                self.backend="lite"
        return _lite_embed(text)

    def describe(self) -> str:
        return f"semantic({self._model_name})" if self._model is not None else "lite(n-gram)"

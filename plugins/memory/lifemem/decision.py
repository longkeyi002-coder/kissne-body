"""Decision layer for Lifemem.

The provider owns the contract; Laya/Kev are optional implementations.  Failure
always falls back to conservative local rules so memory never depends on a
model service being online.
"""
from __future__ import annotations
from dataclasses import dataclass
import json, re, urllib.request
from typing import Optional
from .admission import assess, category_for

SPACES={"reality","relationship","ai_self","ai_world"}

@dataclass(frozen=True)
class MemoryDecision:
    remember: bool
    memory_space: str="reality"
    importance: float=.5
    emotion: str=""
    summary: str=""

class HeuristicDecisionEngine:
    """High-precision fallback. Prefer missing a memory over polluting the store."""
    _signals=(
      "记住","请记得","以后都","我喜欢","我不喜欢","我讨厌","我希望",
      "我们决定","决定用","固定用","不要再","永远不要","我的名字","我叫",
      "remember ","i prefer ","i like ","i dislike ","we decided ",
    )
    def decide(self,user_text:str,assistant_text:str="")->MemoryDecision:
        text=(user_text or "").strip()
        low=text.lower()
        remember=any(x in low for x in self._signals)
        if not remember:
            return MemoryDecision(False)
        space="reality"
        if any(x in text for x in ("小机星","AI World","ai world","世界观","剧情","设定里")):
            space="ai_world"
        elif any(x in text for x in ("你自己","叶青栩自己","你的习惯","你的性格")):
            space="ai_self"
        elif any(x in text for x in ("我们之间","叶青栩","哥哥","关系","相处")):
            space="relationship"
        importance=.85 if any(x in text for x in ("记住","固定","永远","不要再","决定")) else .65
        emotion=""
        if any(x in text for x in ("讨厌","生气","难过","不喜欢")): emotion="negative"
        elif any(x in text for x in ("喜欢","开心","高兴","爱")): emotion="positive"
        summary=re.sub(r"\s+"," ",text)
        state, _ = assess(text, summary, category=category_for(text), subject="user", scope=space)
        return MemoryDecision(state == "active",space,importance,emotion,summary)

class LayaDecisionEngine:
    """Optional local HTTP adapter. Expected response is Lifemem's tiny stable JSON contract.

    This adapter deliberately does not expose Laya to Hermes model/provider selection.
    A Termux-side bridge can translate the installed Laya version into this contract.
    """
    def __init__(self,endpoint:str,timeout:float=.8,fallback=None):
        self.endpoint=(endpoint or "").rstrip("/")
        self.timeout=max(.1,float(timeout))
        self.fallback=fallback or HeuristicDecisionEngine()

    def decide(self,user_text:str,assistant_text:str="")->MemoryDecision:
        return self.decide_with_context(user_text, [])

    def decide_with_context(self,user_text:str,context)->MemoryDecision:
        if not self.endpoint:
            return self.fallback.decide(user_text, "")
        payload=json.dumps({"task":"lifemem_write_gate","user_text":user_text or "",
                            "assistant_text":"", "context":list(context)[-2:],
                            "evidence_policy":"Only user_text is evidence; context resolves references, never adds facts."},ensure_ascii=False).encode()
        req=urllib.request.Request(self.endpoint+"/decide",data=payload,
            headers={"Content-Type":"application/json"},method="POST")
        try:
            with urllib.request.urlopen(req,timeout=self.timeout) as resp:
                data=json.loads(resp.read().decode("utf-8"))
            space=str(data.get("memory_space") or "reality")
            if space not in SPACES: space="reality"
            return MemoryDecision(data.get("remember") is True,space,
                max(0,min(1,float(data.get("importance",.5)))),
                str(data.get("emotion") or ""),str(data.get("summary") or "")[:240])
        except Exception:
            return self.fallback.decide(user_text, "")

def build_decision_engine(kind:str="laya",endpoint:str="",timeout:float=.8):
    fallback=HeuristicDecisionEngine()
    if (kind or "").lower()=="laya":
        return LayaDecisionEngine(endpoint,timeout,fallback)
    return fallback



"""Evidence gate shared by automatic extraction and explicit memory tools."""
from __future__ import annotations
import re

CATEGORIES = {"fact", "preference", "agreement", "event", "project", "relationship", "temporary"}
EXPLICIT = re.compile(r"记住|请记得|以后都|固定用|永远不要|不要再|我们决定|决定用|remember\b|we decided", re.I)
STABLE = re.compile(r"我的名字|我叫|我喜欢|我不喜欢|我讨厌|i prefer\b|i like\b|i dislike\b", re.I)
SENSITIVE = re.compile(r"密码|验证码|私钥|身份证|银行卡|病历|诊断|月经|password|secret key|access.token", re.I)
AMBIGUOUS = re.compile(r"^(?:啊|嗯|哦|不对|完全不对|这个|那个|这样|那样|它|他|她|好的|可以|继续)[\s，。！.!…]*$")

def assess(quote: str, summary: str, *, category="fact", subject="user", scope="", context=""):
    quote, summary = quote.strip(), summary.strip()
    if not quote or not summary:
        return "rejected", "missing_evidence"
    if len(quote) > 1200 or len(summary) > 400:
        return "candidate", "needs_topic_extraction"
    if category not in CATEGORIES or not subject or not scope:
        return "candidate", "missing_type_subject_scope"
    if AMBIGUOUS.fullmatch(quote) or "lifemem — recalled" in quote or "lifemem - recalled" in quote:
        return "rejected", "not_a_fact"
    if re.search(r"(?:记住|请记得)[，,:：\s]*(?:这个|那个|这样|那样|他|她|它)", quote):
        return "candidate", "unresolved_reference"
    if re.search(r"如果|假如|比如|例如|他说|她说|[?？]", quote):
        return "candidate", "hypothetical_or_reported"
    # Summary must remain extractive until a verified semantic admission path exists.
    if re.sub(r"\s+", "", summary) not in re.sub(r"\s+", "", quote):
        return "candidate", "summary_needs_review"
    if SENSITIVE.search(quote) and not EXPLICIT.search(quote):
        return "candidate", "sensitive_requires_explicit_request"
    if re.search(r"今天|现在|这次|暂时|today|right now", quote, re.I) and category != "temporary":
        return "candidate", "temporary_scope_required"
    if category == "temporary":
        return "candidate", "expiry_required"
    if EXPLICIT.search(quote) or (STABLE.search(quote) and not re.search(r"[?？]|如果|假如|比如|例如|他说|她说", quote)):
        return "active", "evidence_backed"
    return "candidate", "future_utility_uncertain"

def category_for(text: str):
    if re.search(r"今天|现在|暂时", text): return "temporary"
    if re.search(r"决定|固定|以后|不要再", text): return "agreement"
    if STABLE.search(text): return "preference"
    return "fact"

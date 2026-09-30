"""Bounded, extractive topic packets. Context is never promoted to evidence."""
from __future__ import annotations
import re
from .admission import EXPLICIT, STABLE


def topic_packets(text, *, max_chars=1200):
    """Keep sentences intact; oversized sentences remain for review, not truncation."""
    pieces=re.split(r'(?<=[。！？!?])|\n\s*\n', text or '')
    packets=[]; current=''
    for piece in pieces:
        if not piece.strip():
            continue
        if current and len(current)+len(piece)>max_chars:
            packets.append(current.strip());current=''
        if len(piece)>max_chars:
            if current:packets.append(current.strip());current=''
            packets.append(piece.strip())
        else:
            current+=piece
    if current:packets.append(current.strip())
    return packets


def topic_candidates(text):
    """Extract signal-bearing original sentences, not all sentences in a transcript."""
    packets=topic_packets(text)
    out=[];seen=set()
    for index,packet in enumerate(packets):
        for sentence in re.split(r'(?<=[。！？!?])|\n',packet):
            quote=sentence.strip()
            if not quote or not (EXPLICIT.search(quote) or STABLE.search(quote)):
                continue
            if quote in seen:continue
            seen.add(quote)
            # Preserve immediate surrounding original text for review, bounded separately.
            context=[p[-400:] for p in packets[max(0,index-1):index]]
            out.append({'quote':quote,'context':context,'oversized':len(quote)>1200})
    return out

"""Chunkers.  `fixed` is the naive baseline; `structured` respects Markdown sections, keeps code files whole
(up to a cap) and keeps short items (reviews, proposals) as single chunks."""
from __future__ import annotations

import re

from rag.types import Chunk, Item


def fixed(item: Item, size: int = 500, overlap: int = 80) -> list[Chunk]:
    t = item.text
    out, i, n = [], 0, 0
    while i < len(t):
        piece = t[i: i + size]
        out.append(Chunk(id=f"{item.id}#f{n}", item_id=item.id, text=piece, raw=piece))
        n += 1
        i += size - overlap
    return out or [Chunk(id=f"{item.id}#f0", item_id=item.id, text=t, raw=t)]


def structured(item: Item, max_chars: int = 900) -> list[Chunk]:
    if item.type in ("review", "past_proposal") or len(item.text) <= max_chars:
        return [Chunk(id=f"{item.id}#s0", item_id=item.id, text=item.text, raw=item.text)]
    if item.type == "code":
        parts = re.split(r"\n(?=# file: )", item.text)
    else:
        parts = re.split(r"\n(?=#{1,3} )", item.text)
    out, buf = [], ""
    for p in parts:
        if len(buf) + len(p) > max_chars and buf:
            out.append(buf)
            buf = ""
        buf += ("\n" if buf else "") + p
    if buf:
        out.append(buf)
    final = []
    for piece in out:
        while len(piece) > max_chars * 1.5:
            final.append(piece[:max_chars])
            piece = piece[max_chars - 100:]
        final.append(piece)
    return [Chunk(id=f"{item.id}#s{i}", item_id=item.id, text=c, raw=c) for i, c in enumerate(final)]


def header(item: Item) -> str:
    """Cheap deterministic context line (title/type/industry) - used when no LLM context is available."""
    bits = [item.type.replace("_", " "), item.title]
    if item.client_industry:
        bits.append(f"{item.client_industry} client")
    if item.project:
        bits.append(f"project {item.project}")
    return " | ".join(bits)

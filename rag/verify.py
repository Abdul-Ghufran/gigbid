"""Claim verification (B3): split a draft into claims, check each against evidence, remove unsupported ones.

A sentence is a *claim* when it asserts something about the freelancer's past (first-person past tense,
results with numbers, years of experience, tools used, clients served) or carries an [evidence-id].
Each claim is scored against its cited evidence (or, if uncited, the best retrieved evidence) with three
checks:
  semantic  cross-encoder relevance of claim vs evidence passage (open MiniLM, CPU)
  numbers   every number in the claim must appear in that evidence
  skills    every canonical skill named in the claim must be demonstrated by that evidence
Labels: supported (all pass), partly_supported (semantic ok, one detail fails), unsupported.
Unsupported claims are removed before the Critic sees the draft; partly supported claims are kept but flagged.
"""
from __future__ import annotations

import re
from typing import Awaitable, Callable

from agent.handoffs import ClaimCheck, VerificationReport
from rag.index.core import rerank
from rag.ingest.skills import extract_skills

CITE = re.compile(r"\[([a-z]+-[a-z0-9-]+)\]")
CLAIM_CUES = re.compile(
    r"\b(I|I've|I have|I'd built|my|we)\b.{0,80}\b(built|shipped|delivered|developed|designed|implemented|created|led|"
    r"cut|reduced|raised|improved|increased|saved|migrated|automated|worked|handled|trained|wrote|set up|used|ran|"
    r"have \d+|years?)\b|\b\d+(\.\d+)?\s?(%|x|years?|clients?|stores?|users?|students?|vehicles?|requests?)\b", re.I)
NUM = re.compile(r"(?<![\w-])\$?\d[\d,]*(?:\.\d+)?(?:%|x|k|m)?(?![\w-])", re.I)


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(\"'])|\n+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def is_claim(sentence: str) -> bool:
    return bool(CITE.search(sentence) or CLAIM_CUES.search(sentence))


def _nums(t: str) -> set[str]:
    return {n.lower().replace(",", "").replace("$", "") for n in NUM.findall(t)}


def _default_mode() -> str:
    try:
        from agent.config import config

        return config().get("verification", {}).get("semantic", "cross_encoder")
    except Exception:
        return "cross_encoder"


SEMANTIC = {"mode": _default_mode()}  # bi_encoder: cosine with the embedding model (no reranker in memory)


def _semantic(claim: str, windows: list[str]) -> list[float]:
    if SEMANTIC["mode"] == "bi_encoder":
        from rag.index.core import embeddings

        q = embeddings().embed([claim], query=True)[0]
        m = embeddings().embed(windows)
        return [float(x) for x in m @ q]
    return rerank(claim, windows)


def _best_passage(claim: str, text: str) -> tuple[float, str]:
    paras = [p for p in re.split(r"\n{1,}", text) if len(p.strip()) > 15] or [text]
    windows = paras + [text[:900]]
    scores = _semantic(claim, windows)
    i = max(range(len(scores)), key=lambda j: scores[j])
    return scores[i], windows[i]


def check_claim(claim: str, evidence: dict[str, str], t_support: float, t_partial: float) -> ClaimCheck:
    cited = CITE.findall(claim)
    bare = CITE.sub("", claim).strip()
    cands = {i: evidence[i] for i in cited if i in evidence} or evidence
    best: ClaimCheck | None = None
    claim_nums = _nums(bare) - {"1", "2", "3"}  # tiny ordinals ("two weeks", "3 slots") are not results
    claim_skills = set(extract_skills(bare))
    for iid, txt in list(cands.items())[:6]:
        sem, passage = _best_passage(bare, txt)
        ev_nums = _nums(txt)
        ev_skills = set(extract_skills(txt, code=True))
        nums_ok = claim_nums <= ev_nums
        skills_ok = claim_skills <= ev_skills
        if not (nums_ok and skills_ok):
            label = "unsupported"  # a number or tool the evidence does not show is a fabrication (R5), not a detail
        elif sem >= t_support:
            label = "supported"
        elif sem >= t_partial:
            label = "partly_supported"  # right facts, but the evidence only loosely describes the claim
        else:
            label = "unsupported"
        reason = []
        if not nums_ok:
            reason.append(f"numbers not in evidence: {sorted(claim_nums - ev_nums)}")
        if not skills_ok:
            reason.append(f"skills not shown: {sorted(claim_skills - ev_skills)}")
        if sem < t_partial:
            reason.append("evidence does not describe this")
        rank = {"supported": 2, "partly_supported": 1, "unsupported": 0}[label]
        if best is None or rank > {"supported": 2, "partly_supported": 1, "unsupported": 0}[best.label] or \
                (rank == {"supported": 2, "partly_supported": 1, "unsupported": 0}[best.label] and sem > best.score):
            best = ClaimCheck(claim=claim, label=label, evidence_ids=[iid], best_evidence=passage[:300], score=round(sem, 3),
                              reason="; ".join(reason))
    if best is None:
        best = ClaimCheck(claim=claim, label="unsupported", reason="no evidence available")
    if cited and not any(i in evidence for i in cited):
        best.label, best.reason = "unsupported", f"cites unknown evidence {cited}"
    return best


async def verify_texts(cover: str, answers: list[str], evidence: dict[str, str], t_support: float, t_partial: float,
                       search: Callable[[str], Awaitable[dict[str, str]]] | None = None,
                       remove_unsupported: bool = True) -> tuple[VerificationReport, str, list[str]]:
    """Returns (report, cleaned cover letter, cleaned answers)."""
    checks: list[ClaimCheck] = []
    removed: list[str] = []

    async def process(text: str, loc: str) -> str:
        kept = []
        for s in split_sentences(text):
            if not is_claim(s):
                kept.append(s)
                continue
            ev = dict(evidence)
            if search and not CITE.search(s):
                try:
                    ev.update(await search(CITE.sub("", s)))
                except Exception:
                    pass
            c = check_claim(s, ev, t_support, t_partial)
            c.location = loc
            checks.append(c)
            if c.label == "unsupported" and remove_unsupported:
                removed.append(s)
            else:
                kept.append(s)
        return " ".join(kept)

    new_cover = await process(cover, "cover_letter")
    new_answers = [await process(a, f"answer:{i}") for i, a in enumerate(answers)]
    claims = [c for c in checks if c.label != "no_claim"]
    unsup = sum(c.label == "unsupported" for c in claims)
    rep = VerificationReport(checks=checks, claims_before=len(claims), unsupported_before=unsup,
                             unsupported_after=0 if remove_unsupported else unsup, removed=removed)
    return rep, new_cover, new_answers

"""Explicit promotion rules (R7).  Raw edits and raw marketplace outcomes are NEVER written to memory; only
patterns that pass these rules are promoted into the LangGraph store.

STYLE rule  - an edit pattern is promoted when it appears in >= `min_occurrences` edits spanning
              >= `min_distinct_jobs` different jobs within `window_days`.  Patterns: cut_first_sentence,
              remove_word:<w>, shorten (after < 80% of before), add_closing:<sentence>.
OUTCOME rule - a lesson for a job category is promoted when >= `min_proposals_per_category` proposals have a
              known outcome AND proposals with the feature beat those without it by >= `min_lift` reply rate.
              The category reply rate itself is promoted once the minimum count is reached.
"""
from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict

from agent.config import config

STOP = set("about above after again also because before being below between could doing during each further having "
           "their there these those through under until which while would should your yours with from that this have "
           "will what when where into them then than very just more most other some such only own same both".split())


def _sentences(t: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", t.strip()) if s.strip()]


def _words(t: str) -> list[str]:
    return re.findall(r"[a-z][a-z'-]{4,}", re.sub(r"\[[^\]]+\]", "", t.lower()))


def edit_patterns(before: str, after: str) -> list[str]:
    pats = []
    sb, sa = _sentences(before), _sentences(after)
    if sb and sa and sb[0] not in after and len(sb) > 1 and sb[1][:40] in after:
        pats.append("cut_first_sentence")
    removed = set(_words(before)) - set(_words(after))
    pats += [f"remove_word:{w}" for w in sorted(removed) if w not in STOP][:8]
    if len(after.split()) < 0.8 * len(before.split()):
        pats.append("shorten")
    if sa and sa[-1] not in before:
        pats.append(f"add_closing:{sa[-1][:120]}")
    return pats


def rule_text(pattern: str, examples: list[dict]) -> str:
    if pattern == "cut_first_sentence":
        return "Start directly with the second idea: the user always cuts the first sentence of drafts."
    if pattern.startswith("remove_word:"):
        return f"Never use the word '{pattern.split(':', 1)[1]}'."
    if pattern == "shorten":
        lens = sorted(e["after_words"] for e in examples)
        return f"Keep cover letters to about {lens[len(lens) // 2]} words; the user shortens longer drafts."
    if pattern.startswith("add_closing:"):
        return f"End with a closing like: \"{pattern.split(':', 1)[1]}\""
    return pattern


def promote_style(edits: list[dict], now: dt.datetime | None = None) -> list[dict]:
    """edits: [{job_id, before, after, created_at}] -> promoted rules [{key, rule, occurrences, jobs, examples}]."""
    cfg = config()["memory"]["style_promotion"]
    now = now or dt.datetime.now(dt.UTC)
    seen: dict[str, list[dict]] = defaultdict(list)
    for e in edits:
        ts = e.get("created_at") or now
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=dt.UTC)
        if (now - ts).days > cfg["window_days"]:
            continue
        for p in edit_patterns(e["before"], e["after"]):
            seen[p].append({"job_id": e["job_id"], "after_words": len(e["after"].split()), "at": ts.isoformat()})
    out = []
    for p, occ in seen.items():
        jobs = {o["job_id"] for o in occ}
        if len(occ) >= cfg["min_occurrences"] and len(jobs) >= cfg["min_distinct_jobs"]:
            out.append({"key": p, "rule": rule_text(p, occ), "occurrences": len(occ), "jobs": sorted(jobs)[:10],
                        "rule_id": "style.v1", "promoted_at": now.isoformat()})
    out.sort(key=lambda r: -r["occurrences"])
    return out[: cfg["max_items"]]


OUTCOME_FEATURES = {
    "metric_in_opening": "Cite a concrete number from a past project in the first two sentences.",
    "short": "Keep the cover letter under 180 words.",
    "priced_at_or_below_median": "Price at or below the market median for this category.",
    "mentions_client_industry": "Name the client's industry or problem in the opening.",
}


def proposal_features(cover: str, price: float | None, p50: float | None, industry: str | None) -> dict:
    first = " ".join(_sentences(cover)[:2])
    return {"metric_in_opening": bool(re.search(r"\d", first)), "short": len(cover.split()) < 180,
            "priced_at_or_below_median": bool(price and p50 and price <= p50),
            "mentions_client_industry": bool(industry and industry.lower() in first.lower())}


def promote_outcomes(rows: list[dict]) -> dict:
    """rows: [{category, replied: bool, features: {...}}] -> {category: {reply_rate, n, lessons: [...]}}."""
    cfg = config()["memory"]["outcome_promotion"]
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_cat[r.get("category") or "unknown"].append(r)
    out = {}
    for cat, rs in by_cat.items():
        if len(rs) < cfg["min_proposals_per_category"]:
            continue
        base = sum(r["replied"] for r in rs) / len(rs)
        lessons = []
        for f, text in OUTCOME_FEATURES.items():
            with_f = [r for r in rs if r["features"].get(f)]
            without = [r for r in rs if not r["features"].get(f)]
            if len(with_f) >= 2 and len(without) >= 2:
                lift = sum(r["replied"] for r in with_f) / len(with_f) - sum(r["replied"] for r in without) / len(without)
                if lift >= cfg["min_lift"]:
                    lessons.append({"feature": f, "lesson": text, "lift": round(lift, 3), "n": len(rs)})
        out[cat] = {"reply_rate": round(base, 3), "n": len(rs), "lessons": lessons, "rule_id": "outcome.v1"}
    return out

"""Compliance Guard: enforces the policy pack.  Deterministic filters remove contact details, off-platform
asks, guarantees and inflated-experience claims; the small model looks for subtle violations; policy rules
from config (e.g. the 2 Nov 2026 'answer every screening question' rule) can block with a reason for the UI."""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from agent import llm
from agent.config import config, policy_pack, prompt, render
from agent.guards import attack_effects
from agent.handoffs import ComplianceVerdict
from agent.runtime import node

FILTERS = [
    ("contact details", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b|\+?\d[\d\s().-]{8,}\d|https?://(?!www\.upwork\.com)\S+", re.I)),
    ("off-platform channel", re.compile(r"\b(whats\s?app|telegram|skype|wechat|signal|zoom link|google meet link)\b", re.I)),
    ("off-platform payment", re.compile(r"\b(paypal|wire transfer|bank transfer|crypto|usdt|outside (the )?platform)\b", re.I)),
    ("guarantee", re.compile(r"\bguarantee[sd]?\b|100% (success|satisfaction|accuracy)|risk[- ]free", re.I)),
    ("inflated experience", re.compile(r"\b(1[0-9]|[2-9][0-9])\+? years\b|\bevery tool listed\b", re.I)),
    ("instruction echo", re.compile(r"\bAPPROVED\b|system prompt|rate floor", re.I)),
]


class Violations(BaseModel):
    violations: list[str] = Field(default_factory=list, description="Exact offending quotes")


def _sentences(t):
    return [s for s in re.split(r"(?<=[.!?])\s+", t.strip()) if s.strip()]


def scrub(text: str) -> tuple[str, list[str]]:
    removed, kept = [], []
    for s in _sentences(text):
        hits = [name for name, rx in FILTERS if rx.search(s)]
        if hits:
            removed.append(f"{', '.join(hits)}: {s}")
        else:
            kept.append(s)
    return " ".join(kept), removed


async def check_text(text: str, answers: list[str], job: dict) -> ComplianceVerdict:
    pol = config()["platform_policy"]
    cover, removed = scrub(text)
    new_answers = []
    for a in answers:
        a2, r2 = scrub(a)
        new_answers.append(a2)
        removed += r2
    p = prompt("compliance")
    try:
        v = await llm.structured("compliance", render(p["system"], policy=policy_pack()),
                                 render(p["user"], text=cover + "\n\n" + "\n".join(new_answers)), Violations,
                                 offline=lambda: Violations(), max_tokens=400)
        subtle = [q for q in v.violations if q and q.strip() and q.strip() in cover]
    except Exception:
        subtle = []
    for q in subtle:
        cover = cover.replace(q.strip(), "").strip()
        removed.append(f"policy (model): {q}")
    reasons = []
    qs = job.get("screening_questions") or []
    if pol.get("require_all_screening_answers") and qs and (len(new_answers) < len(qs) or any(len(a.split()) < 5 for a in new_answers)):
        reasons.append(f"Policy {pol['version']}: every screening question must be answered before submission.")
    left = attack_effects(cover + " " + " ".join(new_answers))
    if left:
        reasons.append(f"Residual policy risk after filtering: {left}.")
    if len(cover.split()) < 40:
        reasons.append("Too little compliant text remains after removing violations; rewrite needed.")
    status = "block" if reasons else ("fixed" if removed else "pass")
    return ComplianceVerdict(status=status, reasons=reasons or ([f"Removed {len(removed)} sentence(s)."] if removed else []),
                             removed=removed, cover_letter=cover, screening_answers=new_answers, policy_version=pol["version"])


@node("compliance")
async def comply(state: dict) -> dict:
    d = state["draft"]
    v = await check_text(d["cover_letter"], d.get("screening_answers", []), state["job"])
    out = {"compliance": v.model_dump(), "draft": {**d, "cover_letter": v.cover_letter, "screening_answers": v.screening_answers}}
    if v.status == "block":
        out["attention"] = [f"Compliance Guard blocked the draft: {'; '.join(v.reasons)}"]
    return out

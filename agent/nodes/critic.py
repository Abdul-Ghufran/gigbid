"""Critic: deterministic checks + strong-model review; sends a draft back with reasons at most twice."""
from __future__ import annotations

import re

from agent import llm
from agent.config import config, prompt, render
from agent.handoffs import Critique
from agent.runtime import node

GENERIC = re.compile(r"^(dear|hello|hi|greetings)\b|passionate|i have (read|gone through) your|perfect fit|to whom it may concern", re.I)


def deterministic_checks(draft: dict, job: dict, verification: dict) -> list[str]:
    t = config()["thresholds"]
    issues = []
    words = len(draft.get("cover_letter", "").split())
    if words > t["proposal_max_words"]:
        issues.append(f"Too long: {words} words (max {t['proposal_max_words']}).")
    if words < t["proposal_min_words"]:
        issues.append(f"Too short: {words} words (min {t['proposal_min_words']}).")
    first = re.split(r"(?<=[.!?])\s", draft.get("cover_letter", "").strip(), maxsplit=1)[0]
    if GENERIC.search(first):
        issues.append("Generic opening: start with the client's problem instead.")
    qs = job.get("screening_questions") or []
    empty = [i for i, a in enumerate(draft.get("screening_answers", [])) if len(a.split()) < 8]
    if qs and (len(draft.get("screening_answers", [])) < len(qs) or empty):
        issues.append(f"Screening answers missing or too thin for question(s) {[i + 1 for i in empty] or 'all'}.")
    if not re.search(r"\[[a-z]+-[a-z0-9-]+\]", draft.get("cover_letter", "")):
        issues.append("No evidence citations in the cover letter.")
    if verification.get("removed"):
        issues.append(f"{len(verification['removed'])} unsupported claim(s) were removed by verification; replace them with supported proof.")
    title_words = {w for w in re.findall(r"[a-z]{5,}", job.get("title", "").lower())} - {"expert", "needed", "developer", "build"}
    if title_words and not any(w in draft.get("cover_letter", "").lower() for w in title_words):
        issues.append("Not personalised: does not mention what this job is about.")
    return issues


@node("critic")
async def critique(state: dict) -> dict:
    draft, job = state["draft"], state["job"]
    checks = deterministic_checks(draft, job, state.get("verification", {}))
    t = config()["thresholds"]
    rev = state.get("revision", 1)

    def offline():
        score = max(0.0, 10 - 1.5 * len(checks))
        return Critique(score=score, passed=score >= t["critic_pass_score"], issues=checks, instructions=checks)

    p = prompt("critic")
    user = render(p["user"], job_spec=state["analyses"].get("job_spec", {}), revision=str(rev),
                  draft=f"{draft.get('cover_letter')}\n\nSCREENING ANSWERS:\n" + "\n".join(draft.get("screening_answers", [])),
                  checks=checks or ["all deterministic checks passed"],
                  verification={k: state.get("verification", {}).get(k) for k in ("claims_before", "unsupported_before", "removed")})
    c = await llm.structured("critic", render(p["system"], pass_score=str(t["critic_pass_score"])), user, Critique, offline=offline)
    hard = [i for i in checks if i.startswith(("Generic", "No evidence", "Too long", "Screening"))]
    c.issues = list(dict.fromkeys(checks + c.issues))
    c.passed = bool(c.passed and not hard and c.score >= t["critic_pass_score"])
    c.revision = rev
    return {"critiques": [c.model_dump()]}

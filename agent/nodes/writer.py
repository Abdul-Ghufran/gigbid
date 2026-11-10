"""Proposal Writer: cover letter + screening answers where every claim cites portfolio evidence."""
from __future__ import annotations

import re

from agent import llm
from agent.config import config, prompt, render
from agent.guards import delimit, strip_injection
from agent.handoffs import Claim, ProposalDraft
from agent.mcp_client import Toolbox
from agent.memory.store import outcome_lessons, style_rules
from agent.runtime import node, tool_tracer

CITE = re.compile(r"\[([a-z]+-[a-z0-9-]+)\]")


def evidence_block(fit: dict) -> tuple[str, list[str]]:
    lines, unsupported = [], []
    for m in fit.get("matrix", []):
        if not m["supported"]:
            unsupported.append(m["requirement"])
            continue
        lines.append(f"- Requirement: {m['requirement']}")
        for e in m["evidence"][:2]:
            snip = re.sub(r"\s+", " ", e["snippet"])[:500]
            lines.append(f"    [{e['item_id']}] ({e['type']}) {e['title']}: {snip}")
    return "\n".join(lines) or "(no evidence)", unsupported


def template_draft(job: dict, spec: dict, fit: dict, price: dict, version: int) -> ProposalDraft:
    """Deterministic grounded fallback used when no LLM is reachable (offline / outage)."""
    proofs = []
    for m in fit.get("matrix", []):
        if m["supported"] and m["evidence"]:
            e = m["evidence"][0]
            out = re.search(r"The work ([^.]+)\.", e["snippet"])
            if out and e["item_id"] not in {p[0] for p in proofs}:
                proofs.append((e["item_id"], f"In {e['title'].lower()}, the work {out.group(1)} [{e['item_id']}]."))
            elif e["item_id"] not in {p[0] for p in proofs}:
                proofs.append((e["item_id"], f"My {e['type'].replace('_', ' ')} \"{e['title']}\" covers {m['requirement'].lower().rstrip('.')} [{e['item_id']}]."))
    need = spec.get("summary") or job.get("title", "this project")
    opening = f"You need {need[0].lower() + need[1:] if need else 'help'}".rstrip(".") + ", and I have done close to this before."
    body = " ".join(p[1] for p in proofs[:3]) or "I would start with a short scoping call to confirm the details."
    approach = ("I would start by confirming the success criteria with you, ship a first working version early, "
                "and keep you updated at every milestone.")
    nxt = f"My bid is {price.get('amount')} USD ({price.get('bid_type')}). Shall we confirm the scope here on the platform?"
    answers = []
    for q in job.get("screening_questions") or []:
        a = proofs[0][1] if proofs else "I would approach this step by step and agree on checkpoints with you."
        answers.append(f"{a} For this job I would apply the same approach, adapted to your requirements.")
    text = f"{opening}\n\n{body}\n\n{approach} {nxt}"
    return ProposalDraft(job_id=job["job_id"], cover_letter=text, screening_answers=answers, version=version, strategy="template")


@node("writer")
async def write(state: dict) -> dict:
    job, an = state["job"], state["analyses"]
    spec, fit, price = an.get("job_spec", {}), an.get("fit", {}), state.get("price", {})
    version = (state.get("revision") or 0) + 1
    ev_text, unsupported = evidence_block(fit)
    tb = Toolbox("writer", state["user_id"], on_call=tool_tracer("writer"))
    extra_ev = {}
    # pull evidence for analyst requirements the fit matcher's heuristic split did not cover
    covered = " ".join(m["requirement"].lower() for m in fit.get("matrix", []))
    for req in (spec.get("requirements") or [])[:6]:
        if req.lower()[:25] not in covered:
            res = await tb.call("portfolio", "search_evidence", {"requirement": req, "k": 2})
            if res["supported"]:
                for it in res["items"]:
                    extra_ev[it["id"]] = {"item_id": it["id"], "title": it["title"], "type": it["type"], "snippet": it["snippet"],
                                          "score": it["score"], "source": it.get("source", "")}
                ev_text += f"\n- Requirement: {req}\n" + "\n".join(
                    f"    [{i['id']}] ({i['type']}) {i['title']}: {re.sub(r'\s+', ' ', i['snippet'])[:400]}" for i in res["items"])
            else:
                unsupported.append(req)
    style = await style_rules(state["user_id"])
    lessons = await outcome_lessons(state["user_id"], job.get("category"))
    examples = state.get("examples") or []
    crit = state.get("critiques") or []
    revision_notes = ""
    if crit and not crit[-1].get("passed"):
        revision_notes = "REVISION REQUEST from the critic (fix all of these):\n- " + "\n- ".join(
            crit[-1].get("instructions", []) + crit[-1].get("issues", []))
        if state.get("draft"):
            revision_notes += f"\n\nPREVIOUS DRAFT:\n{state['draft'].get('cover_letter', '')}"
    t = config()["thresholds"]
    clean, _ = strip_injection(job.get("description", ""))
    p = prompt("writer")
    sys = render(p["system"], min_words=str(t["proposal_min_words"]), max_words=str(t["proposal_max_words"]),
                 style_rules=("Learned style rules from this freelancer's edits (follow them):\n- " + "\n- ".join(r["rule"] for r in style)) if style else "")
    lesson_lines = [lx["lesson"] for lx in lessons.get("lessons", [])] + [f"Winning example ({e['outcome']}): {e['text'][:300]}" for e in examples]
    user = render(p["user"], job_spec=spec, evidence=ev_text, unsupported=unsupported or ["(none)"],
                  lessons=lesson_lines or ["(no promoted lessons yet)"], price=f"{price.get('amount')} USD {price.get('bid_type')}",
                  screening_questions=job.get("screening_questions") or ["(none)"], revision_notes=revision_notes,
                  job_post=delimit(f"{job.get('title', '')}\n\n{clean}"))
    draft = await llm.structured("writer", sys, user, ProposalDraft, max_tokens=1800,
                                 offline=lambda: template_draft(job, spec, fit, price, version))
    draft.job_id, draft.version = job["job_id"], version
    qs = job.get("screening_questions") or []
    draft.screening_answers = (draft.screening_answers + [""] * len(qs))[: len(qs)] if qs else []
    draft.claims = [Claim(text=s, evidence_ids=CITE.findall(s)) for s in re.split(r"(?<=[.!?])\s+", draft.cover_letter) if CITE.search(s)]
    return {"draft": draft.model_dump(), "revision": version, "evidence": extra_ev}

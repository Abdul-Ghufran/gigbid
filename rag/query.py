"""Query-side helpers: job text and requirement decomposition."""
from __future__ import annotations

import re

from rag.ingest.skills import extract_skills

CUES = re.compile(r"\b(experience|must|need|needs|needed|comfortable|involves|strong|ideally|familiar|knowledge|"
                  r"expert|build|implement|integrate|require|required|looking for|should|ability)\b", re.I)
INJECTION_HINT = re.compile(r"ignore (all )?(previous|prior)|system (message|prompt)|if you are an ai|ai (agents|assistants|proposal tools)|disregard", re.I)


def job_text(job: dict) -> str:
    return f"{job.get('title', '')}\n{job.get('description', '')}"


def decompose(job: dict, requirements: list[str] | None = None, max_reqs: int = 8) -> list[str]:
    """One query per requirement.  Uses the Job Analyst's extracted requirements when given, otherwise a
    deterministic sentence splitter that keeps requirement-like sentences (and drops injected text)."""
    if requirements:
        return [r for r in dict.fromkeys(r.strip() for r in requirements) if r][:max_reqs]
    desc = job.get("description", "")
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z<\[(\"'])|\n+", desc) if len(s.strip()) > 12]
    reqs = [s for s in sents if (CUES.search(s) or extract_skills(s)) and not INJECTION_HINT.search(s)]
    for sk in job.get("skills_listed") or []:
        if not any(sk.lower() in r.lower() for r in reqs):
            reqs.append(f"Experience with {sk}")
    if not reqs:
        reqs = [job.get("title", "")] + sents[:2]
    return list(dict.fromkeys(reqs))[:max_reqs]

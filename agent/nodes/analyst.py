"""Job Analyst: job post -> structured JobSpec (no MCP access)."""
from __future__ import annotations

from agent import llm
from agent.config import prompt, render
from agent.guards import delimit, strip_injection
from agent.handoffs import JobSpec
from agent.runtime import node
from rag.ingest.skills import extract_skills
from rag.query import decompose


def heuristic_spec(job: dict) -> JobSpec:
    """Deterministic fallback (offline / LLM outage)."""
    clean, _ = strip_injection(job.get("description", ""))
    reqs = decompose({**job, "description": clean})
    skills = sorted(set(extract_skills(job.get("title", "") + " " + clean)) | set(job.get("skills_listed") or []))
    b = job.get("budget") or {}
    dl = clean.split("Deliverables:")[-1].strip(" .\n").split(" and ") if "Deliverables:" in clean else []
    return JobSpec(job_id=job["job_id"], title=job.get("title", ""), category=job.get("category"),
                   summary=clean.split("\n")[0][:200], deliverables=[d.strip(" .") for d in dl], requirements=reqs,
                   required_skills=skills, budget_type=b.get("type", "unknown"), budget_min=b.get("min"), budget_max=b.get("max"),
                   timeline=f"{job.get('duration_weeks')} weeks" if job.get("duration_weeks") else None,
                   screening_questions=job.get("screening_questions") or [])


@node("analyst")
async def analyse(state: dict) -> dict:
    job = state["job"]
    clean, _spans = strip_injection(job.get("description", ""))
    p = prompt("analyst")
    user = render(p["user"], job_id=job["job_id"], category=job.get("category") or "unknown", budget=job.get("budget"),
                  skills_listed=job.get("skills_listed") or [], screening_questions=job.get("screening_questions") or [],
                  job_post=delimit(f"{job.get('title', '')}\n\n{clean}"))
    spec = await llm.structured("analyst", p["system"], user, JobSpec, offline=lambda: heuristic_spec(job))
    # trusted marketplace fields always win over model output
    spec.job_id, spec.screening_questions = job["job_id"], job.get("screening_questions") or []
    b = job.get("budget") or {}
    spec.budget_type, spec.budget_min, spec.budget_max = b.get("type", spec.budget_type), b.get("min"), b.get("max")
    if not spec.requirements:
        spec.requirements = heuristic_spec(job).requirements
    return {"analyses": {"job_spec": spec.model_dump()}}

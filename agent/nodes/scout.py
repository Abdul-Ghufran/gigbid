"""Scout: runs saved searches (worker, on schedule), deduplicates and queues new jobs; inside the bid graph it
hands one job in (fresh copy from the marketplace)."""
from __future__ import annotations

import hashlib
import re

from agent.mcp_client import Toolbox
from agent.runtime import node, tool_tracer


def fingerprint(job: dict) -> str:
    """Near-duplicate key: client + normalised title words + first 200 normalised description chars."""
    title = re.sub(r"\b(reposted|urgent)\b|[^a-z0-9 ]", " ", (job.get("title") or "").lower())
    desc = re.sub(r"[^a-z0-9]", "", (job.get("description") or "").lower().replace("we're", "weare").replace("we are", "weare"))[:200]
    key = f"{job.get('client_id')}|{' '.join(sorted(set(title.split())))}|{desc}"
    return hashlib.sha1(key.encode()).hexdigest()


async def run_saved_search(user_id: str, search: dict, seen_fingerprints: set[str], limit: int = 20) -> list[dict]:
    """One saved search -> new, de-duplicated jobs.  Called by the worker (never inside a web request)."""
    tb = Toolbox("scout", user_id, on_call=tool_tracer("scout"))
    res = await tb.call("marketplace", "search_jobs", {
        "query": search.get("query", ""), "category": search.get("category"), "skills": search.get("skills", []),
        "min_budget": search.get("min_budget", 0), "posted_within_minutes": search.get("posted_within_minutes"),
        "limit": limit})
    new = []
    for j in res["jobs"]:
        fp = fingerprint(j)
        j["_fingerprint"] = fp
        j["_duplicate"] = fp in seen_fingerprints
        seen_fingerprints.add(fp)
        new.append(j)
    return new


@node("scout")
async def intake(state: dict) -> dict:
    """First node of the bid graph: load the job through the marketplace port."""
    if state.get("job") and state["job"].get("description"):
        return {"status": "running"}
    tb = Toolbox("scout", state["user_id"], on_call=tool_tracer("scout"))
    job = await tb.call("marketplace", "get_job", {"job_id": state["job_id"]})
    return {"job": job, "status": "running"}

"""R&D question A: does tool granularity change agent behaviour?

40 tasks with known correct calls (10 intents x 4 instances drawn from the dev data).  Three tool sets offered to
the same open model (gpt-oss-20b, tool_choice=required, one call):
  fine    - 22 narrow tools (get_job_title, get_client_spend, search_repos, ...)
  coarse  - 2 tools: marketplace(action, params) and portfolio(action, params)
  best    - GigBid's real MCP tools with rewritten descriptions (schemas read from the servers)
Scores: tool-selection accuracy, argument accuracy (required values present and correct), tokens per task.
  python -m evals.runners.rq_a_tools [--model small]
"""
import argparse
import asyncio
import json
import time

import httpx

from evals.runners import harness as H
from agent.config import model_for  # noqa: E402
from agent.llm import _api_key, _base_url  # noqa: E402
from agent.mcp_client import load_schemas  # noqa: E402


def S(props, req=None):
    return {"type": "object", "properties": props, "required": req or list(props)}


STR = {"type": "string"}
FINE = {
    "get_job_title": ("Get the title of a job.", S({"job_id": STR})),
    "get_job_description": ("Get the full description of a job post.", S({"job_id": STR})),
    "get_job_budget": ("Get the budget of a job.", S({"job_id": STR})),
    "get_job_client": ("Get the client id of a job.", S({"job_id": STR})),
    "get_client_spend": ("Total amount a client has spent.", S({"client_id": STR})),
    "get_client_rating": ("Average rating a client gives.", S({"client_id": STR})),
    "get_client_payment_status": ("Whether the client's payment method is verified.", S({"client_id": STR})),
    "get_connects": ("Connects balance.", S({})),
    "get_connects_history": ("Connects ledger.", S({})),
    "get_market_price_median": ("Median awarded price for a category.", S({"category": STR})),
    "get_market_price_range": ("p25-p75 awarded price for a category.", S({"category": STR})),
    "search_jobs_by_skill": ("Search jobs by one skill.", S({"skill": STR})),
    "search_jobs_by_category": ("Search jobs in a category.", S({"category": STR})),
    "search_case_studies": ("Search case studies.", S({"query": STR})),
    "search_repos": ("Search repositories and code.", S({"query": STR})),
    "search_reviews": ("Search client reviews.", S({"query": STR})),
    "get_case_study": ("Get one case study.", S({"id": STR})),
    "list_threads": ("List conversation threads.", S({})),
    "list_unread_messages": ("List unread client messages.", S({})),
    "preview_submission_cost": ("Connects cost of submitting a proposal.", S({"proposal_id": STR})),
    "submit_proposal_now": ("Submit a proposal.", S({"proposal_id": STR})),
    "preview_message": ("Preview a message before sending.", S({"thread_id": STR, "text": STR})),
}
COARSE = {
    "marketplace": ("Marketplace operations. action is one of: search_jobs, get_job, get_client_history, get_connects_balance, "
                    "get_market_stats, list_messages, submit_proposal, send_message. params holds the arguments.",
                    S({"action": STR, "params": {"type": "object"}})),
    "portfolio": ("Portfolio operations. action is one of: search_evidence, get_case_study, list_skills. params holds the arguments.",
                  S({"action": STR, "params": {"type": "object"}})),
}
# expected: intent -> {set: (acceptable tool names / actions, arg checker)}
INTENTS = [
    ("Show me the full post for job {job_id}.", {"best": ["get_job"], "fine": ["get_job_description"], "coarse": ["get_job"]}, {"job_id": "{job_id}"}),
    ("Is the client {client_id} trustworthy? Check their history.", {"best": ["get_client_history"], "fine": ["get_client_spend", "get_client_rating", "get_client_payment_status"], "coarse": ["get_client_history"]}, {"client_id": "{client_id}"}),
    ("How many Connects do I have left?", {"best": ["get_connects_balance"], "fine": ["get_connects"], "coarse": ["get_connects_balance"]}, {}),
    ("What do comparable {category} jobs usually pay?", {"best": ["get_market_stats"], "fine": ["get_market_price_median", "get_market_price_range"], "coarse": ["get_market_stats"]}, {"category": "{category}"}),
    ("Find open {category} jobs that need {skill}.", {"best": ["search_jobs"], "fine": ["search_jobs_by_skill", "search_jobs_by_category"], "coarse": ["search_jobs"]}, {"_any": "{skill}"}),
    ("Find proof in my portfolio that I have done {skill}.", {"best": ["search_evidence"], "fine": ["search_case_studies", "search_repos", "search_reviews"], "coarse": ["search_evidence"]}, {"_any": "{skill}"}),
    ("Open my case study {case_id}.", {"best": ["get_case_study"], "fine": ["get_case_study"], "coarse": ["get_case_study"]}, {"_any": "{case_id}"}),
    ("Have any clients written to me?", {"best": ["list_messages"], "fine": ["list_unread_messages", "list_threads"], "coarse": ["list_messages"]}, {}),
    ("What would it cost to submit proposal {pid}? Preview only, do not send.", {"best": ["submit_proposal"], "fine": ["preview_submission_cost"], "coarse": ["submit_proposal"]}, {"_any": "{pid}", "_dry": True}),
    ("Draft a reply 'Tuesday 3pm works' in thread {tid} but only preview it.", {"best": ["send_message"], "fine": ["preview_message"], "coarse": ["send_message"]}, {"_any": "{tid}", "_dry": True}),
]


def tasks():
    out = []
    jobs = [r for p in ("ai", "web", "data") for r in H.dev(p)][::37][:4]
    skills = ["Celery", "Power BI", "RAG", "dbt"]
    for i, j in enumerate(jobs):
        v = {"job_id": j["job_id"], "client_id": j["client_id"], "category": j["category"], "skill": skills[i],
             "case_id": f"{['ai', 'web', 'data', 'web'][i]}-case-0{i + 2}", "pid": f"p-{1000 + i}", "tid": f"t-p-{2000 + i}"}
        for text, acc, args in INTENTS:
            out.append({"text": text.format(**v), "acceptable": acc, "args": {k: (x.format(**v) if isinstance(x, str) else x) for k, x in args.items()}})
    return out


def tools_payload(kind: str, best_schemas: dict) -> list[dict]:
    if kind == "fine":
        src = FINE
    elif kind == "coarse":
        src = COARSE
    else:
        src = {n: (d["description"], {**d["inputSchema"], "properties": {k: v for k, v in d["inputSchema"]["properties"].items() if k != "trace_id"}})
               for (srv, n), d in best_schemas.items() if n in {"search_jobs", "get_job", "get_client_history", "get_connects_balance",
                                                               "get_market_stats", "list_messages", "submit_proposal", "send_message",
                                                               "search_evidence", "get_case_study", "list_skills", "list_proposals"}}
    return [{"type": "function", "function": {"name": n, "description": d, "parameters": p}} for n, (d, p) in src.items()]


def score(kind, call, task) -> tuple[bool, bool]:
    if not call:
        return False, False
    name = call["name"]
    try:
        args = json.loads(call.get("arguments") or "{}")
    except Exception:
        args = {}
    if kind == "coarse":
        name = args.get("action", "")
        args = args.get("params") or {}
    tool_ok = name in task["acceptable"][kind]
    flat = json.dumps(args).lower()
    ok = True
    for k, v in task["args"].items():
        if k == "_any":
            ok &= v.lower() in flat
        elif k == "_dry":
            ok &= (kind == "fine") or args.get("dry_run") is True
        else:
            ok &= str(args.get(k, "")).lower() == v.lower() or v.lower() in flat
    return tool_ok, tool_ok and ok


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="small")
    a = ap.parse_args()
    from agent.config import config

    spec = {"alias": a.model, **config()["models"][a.model]}  # a model ALIAS (small = gpt-oss-20b), not a node name
    best = await load_schemas()
    ts = tasks()
    results = {}
    ckpt = H.RESULTS / "rq_a_tools.partial.jsonl"
    done = {}
    if ckpt.exists():
        for line in ckpt.read_text(encoding="utf-8").splitlines():
            x = json.loads(line)
            done[(x["kind"], x["task"])] = x
    async with httpx.AsyncClient(timeout=60) as http:
        for kind in ("fine", "coarse", "best"):
            tools = tools_payload(kind, best)
            rows = []
            for t in ts:
                if (kind, t["text"]) in done:
                    rows.append(done[(kind, t["text"])])
                    continue
                body = {"model": spec["model"], "messages": [
                    {"role": "system", "content": "You are a freelancer's assistant. Call exactly one tool to serve the request."},
                    {"role": "user", "content": t["text"]}], "tools": tools, "tool_choice": "required", "max_tokens": 400}
                if spec.get("reasoning_effort"):
                    body["reasoning_effort"] = "low"
                for attempt in range(30):  # a 429 is a quota wait, never a task failure
                    r = await http.post(f"{_base_url(spec)}/chat/completions", json=body, headers={"Authorization": f"Bearer {_api_key(spec)}"})
                    if r.status_code != 429:
                        break
                    print("429:", r.text[:220], "retry-after", r.headers.get("retry-after"), flush=True)
                    await asyncio.sleep(min(90, float(r.headers.get("retry-after", 10)) + 1))
                d = r.json()
                used = (d.get("usage") or {}).get("total_tokens") or 2000
                await asyncio.sleep(max(0.0, used / 7500 * 60 - 2.2))  # pace under the 8K tokens/minute limit
                calls = (d.get("choices") or [{}])[0].get("message", {}).get("tool_calls") or []
                call = calls[0]["function"] if calls else None
                tok, arg = score(kind, call, t)
                rows.append({"kind": kind, "task": t["text"], "call": call, "tool_ok": tok, "args_ok": arg,
                             "tokens": d.get("usage", {}).get("total_tokens"), "status": r.status_code})
                if r.status_code == 200:
                    with open(ckpt, "a", encoding="utf-8") as fh:
                        fh.write(json.dumps(rows[-1]) + "\n")
                await asyncio.sleep(2.2)
            results[kind] = {"n_tools": len(tools), "tool_selection_accuracy": H.mean([r["tool_ok"] for r in rows]),
                             "argument_accuracy": H.mean([r["args_ok"] for r in rows]),
                             "tokens_per_task": H.mean([r["tokens"] for r in rows if r["tokens"]]), "rows": rows}
            print(kind, {k: v for k, v in results[kind].items() if k != "rows"}, flush=True)
    H.write("rq_a_tools", {"model": spec["model"], "n_tasks": len(ts), "results": results})


if __name__ == "__main__":
    asyncio.run(main())

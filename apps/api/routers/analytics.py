from __future__ import annotations

import statistics
from collections import Counter, defaultdict

from fastapi import APIRouter, Depends

from apps.api.auth.users import current_user
from common.db import JobRecord, Run, User, session

router = APIRouter(prefix="/analytics", tags=["analytics"])
REPLIED = {"replied", "interview", "hired"}


def _pct(xs, p):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))], 3) if xs else None


@router.get("", response_model=dict)
def analytics(u: User = Depends(current_user)):
    with session() as s:
        jobs = s.query(JobRecord).filter_by(user_id=u.id).all()
        runs = s.query(Run).filter_by(user_id=u.id, graph="bid").all()
        by_cat = defaultdict(lambda: {"submitted": 0, "replied": 0, "hired": 0, "connects": 0})
        funnel = Counter()
        rejections = Counter()
        for j in jobs:
            funnel["seen"] += 1
            sm = j.summary or {}
            if sm.get("decision") == "bid":
                funnel["recommended_bid"] += 1
            if sm.get("scam"):
                funnel["scams_caught"] += 1
            if sm.get("reject_reason"):
                rejections[sm["reject_reason"][:60]] += 1
            if j.status == "skipped" and sm.get("reasons"):
                rejections["auto: " + sm["reasons"][-1][:57]] += 1
            if j.pipeline_stage and j.pipeline_stage != "drafted":
                c = by_cat[j.job.get("category") or "unknown"]
                c["submitted"] += 1
                c["connects"] += sm.get("connects_spent") or 0
                funnel["submitted"] += 1
                if j.pipeline_stage in REPLIED:
                    c["replied"] += 1
                    funnel["replied"] += 1
                if j.pipeline_stage == "hired":
                    c["hired"] += 1
                    funnel["hired"] += 1
        cats = [{"category": k, **v, "reply_rate": round(v["replied"] / v["submitted"], 3) if v["submitted"] else None,
                 "hire_rate": round(v["hired"] / v["submitted"], 3) if v["submitted"] else None} for k, v in by_cat.items()]
        drafts = [j for j in jobs if (j.summary or {}).get("tokens")]
        lat = [r.latency_s for r in runs if r.status in ("done", "interrupted") and r.latency_s]
        cost = [(j.summary or {}).get("cost_usd", 0) for j in drafts if (j.summary or {}).get("decision") == "bid"]
        return {
            "funnel": dict(funnel), "by_category": cats, "top_rejection_reasons": rejections.most_common(6),
            "cost_latency": {"runs": len(runs), "p50_latency_s": _pct(lat, 0.5), "p95_latency_s": _pct(lat, 0.95),
                             "mean_cost_per_proposal_usd": round(statistics.mean(cost), 5) if cost else None,
                             "total_cost_usd": round(sum(r.cost_usd for r in runs), 5), "total_tokens": sum(r.tokens for r in runs)},
            "connects_spent": sum(c["connects"] for c in cats),
        }

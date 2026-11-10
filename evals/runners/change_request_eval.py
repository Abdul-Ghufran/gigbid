"""Change request (2 Nov 2026 GigSim policy update): effect of the config-only change.

Against GigSim running the NEW policy, compare GigBid with the old vs new `platform_policy` config:
  * Connects-cost prediction errors on gold-bid dev jobs (pricing / budget decisions use this number)
  * proposals with an unanswered screening question: caught by the Compliance Guard before submission, or rejected
    by GigSim at submission (a wasted round trip and a confused user)
"""
import asyncio
import copy
import os

os.environ["GIGSIM_POLICY_VERSION"] = "2026-11-02"
os.environ.setdefault("LLM_OFFLINE", "1")
from evals.runners import harness as H  # noqa: E402
from agent.config import config  # noqa: E402
from agent.nodes.compliance import check_text  # noqa: E402
from agent.nodes.pricing import connects_with_policy  # noqa: E402
from gigsim.policy import connects_cost  # noqa: E402

OLD = {"version": "2026-10-27", "require_all_screening_answers": False,
       "connects": {"high_competition_threshold": None, "high_competition_multiplier": 1.0}}


async def evaluate(policy_cfg: dict, jobs) -> dict:
    cfg = config()
    saved = copy.deepcopy(cfg["platform_policy"])
    cfg["platform_policy"].update(policy_cfg)
    wrong, caught, rejected = 0, 0, 0
    with_q = 0
    for p, j in jobs:
        base = connects_cost(j["budget"]["max"], 0, {"connects": {**cfg["platform_policy"]["connects"], "base_divisor": 150, "base_offset": 2,
                                                                  "min": 2, "max": 16, "high_competition_threshold": None,
                                                                  "high_competition_multiplier": 1.0}})
        ours = connects_with_policy(base, j)
        truth = connects_cost(j["budget"]["max"], j.get("proposals_count", 0))  # GigSim, new policy
        wrong += ours != truth
        if j["screening_questions"]:
            with_q += 1
            answers = [""] * len(j["screening_questions"])  # e.g. the writer or the user left a question blank
            v = await check_text("I would start with a short scoping call and deliver the first milestone in week one, "
                                 "keeping you updated on progress at every step along the way here on the platform. I would agree the acceptance "
                                 "criteria with you first, share a working build early for feedback, and hand over clear documentation at the end.",
                                 answers, j)
            if v.status == "block":
                caught += 1
            else:
                rejected += 1  # GigSim (new policy) would answer 422 at submission
    cfg["platform_policy"] = saved
    return {"jobs": len(jobs), "connects_prediction_wrong": wrong, "connects_prediction_error_rate": round(wrong / len(jobs), 4),
            "jobs_with_screening_questions": with_q, "blank_answers_caught_before_submit": caught, "rejected_by_marketplace": rejected}


async def main():
    jobs = [(p, j) for p in ("ai", "web", "data") for j in H.dev(p) if j["_gold"]["bid"]]
    new = {k: v for k, v in config()["platform_policy"].items() if k in ("version", "require_all_screening_answers", "connects")}
    out = {"gigsim_policy": "2026-11-02", "before_change (config 2026-10-27)": await evaluate(OLD, jobs),
           "after_change (config 2026-11-02)": await evaluate(new, jobs),
           "diff": "git show <change-request commit>: agent/config.yaml +4/-4, data/policy_pack/marketplace_policy.md +2; no Python changed"}
    H.write("change_request_eval", out)
    print(out)


if __name__ == "__main__":
    asyncio.run(main())

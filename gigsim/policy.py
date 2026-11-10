"""Marketplace policy versions.  The active version is chosen with GIGSIM_POLICY_VERSION.

2026-11-02 is the "platform policy update" change request announced mid-assignment.
"""
import os

POLICIES = {
    "2026-10-27": {
        "version": "2026-10-27",
        "announcement": "Baseline marketplace rules.",
        "connects": {"base_divisor": 150, "base_offset": 2, "min": 2, "max": 16,
                     "high_competition_threshold": None, "high_competition_multiplier": 1.0},
        "require_all_screening_answers": False,
        "weekly_connects_grant": 80,
        "rules": [
            "No off-platform contact or payment.",
            "No fabricated experience.",
            "No guarantees of results.",
            "Fair use of automation: every proposal must be reviewed by the freelancer.",
        ],
    },
    "2026-11-02": {
        "version": "2026-11-02",
        "announcement": (
            "Platform policy update (2 Nov 2026): proposals to jobs that already have 20 or more proposals "
            "cost 1.5x Connects (rounded up). Every screening question must be answered or the proposal is "
            "rejected at submission."
        ),
        "connects": {"base_divisor": 150, "base_offset": 2, "min": 2, "max": 16,
                     "high_competition_threshold": 20, "high_competition_multiplier": 1.5},
        "require_all_screening_answers": True,
        "weekly_connects_grant": 80,
        "rules": [
            "No off-platform contact or payment.",
            "No fabricated experience.",
            "No guarantees of results.",
            "Fair use of automation: every proposal must be reviewed by the freelancer.",
            "Jobs with 20+ proposals cost 1.5x Connects.",
            "All screening questions must be answered.",
        ],
    },
}


def active_policy() -> dict:
    return POLICIES[os.getenv("GIGSIM_POLICY_VERSION", "2026-10-27")]


def connects_cost(budget_max: float, proposals_count: int, policy: dict | None = None) -> int:
    import math

    p = (policy or active_policy())["connects"]
    base = int(min(p["max"], max(p["min"], round(budget_max / p["base_divisor"]) + p["base_offset"])))
    thr = p["high_competition_threshold"]
    if thr is not None and proposals_count >= thr:
        base = int(math.ceil(base * p["high_competition_multiplier"]))
    return base

# ADR-006: Deterministic rules decide safety, LLMs add detail

**Decision.** Scam / free-work / off-platform flags, the bid threshold, pricing and compliance filters are deterministic; LLM output can add risk or explanations but never lower a rule finding.

**Why.** Rules are auditable, cheap and robust to prompt injection; `evals/results/decision_eval_offline.json` shows scam precision and recall 1.0 with rules alone.

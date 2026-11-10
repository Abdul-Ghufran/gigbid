# Signature extension: X2 — proposal experiments

**What it is.** GigBid can run two proposal strategies as an A/B test and tell the freelancer whether one actually gets
more replies — instead of trusting proposal-writing folklore.

- **Arms** (in `agent/config.yaml → experiments.strategies`, editable without code):
  - `proof_first` — client's problem → single most relevant past result with its number → approach → next step.
  - `plan_first` — client's problem → a concrete 3-step plan for this job → supporting past results → next step.
- **Assignment** — `agent/nodes/writer.py::pick_strategy`: a stable hash of the job id, so re-drafts and revisions stay
  in the same arm and assignment is independent of the job's content. The arm is stored on the draft and on the job
  record (`summary.strategy`).
- **In the product** — Analytics → "Proposal A/B test" shows submissions, replies and reply rate per arm from real
  marketplace events (GigSim or Upwork).
- **Offline evaluation** — `python -m evals.runners.ab_test` → `evals/results/ab_test.json`.

## Evaluation design
A between-jobs A/B on a few dozen live submissions has very low power, so the offline evaluation is **paired**: for each
of the 90 drafted gold-bid jobs, the *same sentences* (same facts, same citations, same price) are arranged in both
structures, and both versions are scored by GigSim's simulated client. Reply outcomes are compared with **McNemar's exact
test** on discordant pairs; the client's continuous score with a paired t-test.

## Result
See `evals/results/ab_test.json`: 88 usable pairs; proof-first 19.3 % vs plan-first 21.6 % simulated reply rate;
discordant pairs 9 vs 11; **McNemar exact p = 0.82** — no detectable difference. The client's continuous score was
*identical* for every pair (the paired t-test is undefined): GigSim's rule-based client scores content features
(must-have coverage, specificity, opening, price, length) and is blind to paragraph order, so the only differences are
its random draws.

## What this taught me
1. The experiment machinery works and is honest: it refuses to "find" a winner from noise.
2. **The simulator, not the strategy, limited the result.** A structural change can only be measured by a client model
   that reads structure. GigSim's optional LLM client brain (`GIGSIM_CLIENT_BRAIN=llm`) is the next step — at roughly
   2 × 90 judge calls it did not fit the free-tier daily token budget this week.
3. For real use (Upwork live mode) the in-product per-arm reply rates are what matter; with ~20 % base reply rate a
   two-arm test needs roughly 400 proposals per arm to detect a 7-point difference at 80 % power, i.e. this is a
   months-long experiment for one freelancer — which is exactly why the paired offline design exists.

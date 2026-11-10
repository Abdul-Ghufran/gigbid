# Data card

## Why synthetic, and who made it
The AI-4016 starter kit (v0.1) shipped **without** GigSim, the three persona corpora and the dev evaluation set — only
four tiny sample JSON files. To build and measure GigBid on schedule, I generated a stand-in world with
`tools/synth/build.py` (seed 4016) that follows the assignment's description of those assets as closely as possible,
then **froze** it (`gigsim/MANIFEST.sha256`, checked in CI). If the official GigSim is supplied, point
`GIGSIM_BASE_URL` at it; GigBid only talks to it through the Marketplace MCP server.

**Limitation that matters most:** the same author wrote the generator and the system. I reduced the circularity in
three ways: (1) the generator uses *hard paraphrases* ("background jobs that run off the request path" for Celery)
that GigBid's skill normaliser (`rag/ingest/skills.yaml`) never sees; (2) some skills appear only in code imports;
(3) every threshold was tuned on the dev set and the report says so. A real held-out set would still be better.

All data is synthetic; no real people, clients or Upwork data. Persona names are invented.

## Contents
| Asset | Path | Size | Notes |
|---|---|---|---|
| Persona corpora (AI/ML engineer, full-stack web dev, data analyst) | `data/personas/{ai,web,data}/` | 3 × (CV PDF, 16–18 case studies, 11–14 repos with README + code, 6–8 reviews, 150 past proposals) | 599 evidence items |
| Past proposals with outcomes | `data/personas/*/proposals.jsonl` | 450 | outcome won / replied / ignored from a latent quality model (specific opening, cited metric, on-topic, price fit, length) so outcomes carry real signal |
| GigSim clients | `gigsim/seed/clients.json` | 520 | public history + **hidden** preferences (must-haves, budget ceiling, dislike of generic openings, length preference, reply propensity); 1 in 13 are scam accounts |
| Historical jobs (closed, awarded price) | `gigsim/seed/jobs_historical.jsonl` | 1,500 | market statistics for pricing |
| Live job stream | `gigsim/seed/jobs_live.jsonl` | 360 | released every 20 simulated minutes; ~7% reposted duplicates, ~10% scams, ~9% planted prompt injections |
| Dev set with gold labels | `evals/datasets/dev_{ai,web,data}.jsonl` | 3 × 200 | kinds: strong 62, partial 40, off-domain 30, scam 22, low-budget 14, injection 18, vague 14 per persona |
| Gold evidence | `evals/datasets/gold_items.json` + per-job `_gold.requirements` | 599 items | which skills each item truly demonstrates (prose, synonym, hard paraphrase or import) |

## Gold labels (per dev job, under `_gold`)
- `bid`: not a scam **and** the persona covers ≥ 60 % of required skills **and** the budget clears the persona's floor.
- `scam` (+ `scam_types`), `injection`, `kind`, `coverage`, `fair_band` (market rate × experience level × estimated hours ± 15 %).
- `requirements`: for each required skill, the **acceptable evidence items** (any item that demonstrates it).
- `relevance`: graded relevance per item = number of the job's required skills it demonstrates.

## Metric definitions used everywhere
- **Evidence Recall@5** — fraction of a job's coverable requirements for which ≥ 1 acceptable item is in the top 5.
- **MRR** — reciprocal rank of the first item demonstrating any required skill (top 10).
- **nDCG@10** — graded by `relevance`.
- **Bid F1** — bid is the positive class. **Scam P/R** — on `scam`. **Price in band** — quote inside `fair_band` (gold-bid jobs).
- **Unsupported claims / proposal** — sentences the verifier labels unsupported (before = writer output; after = audit of
  the final text).
- **GigSim reply rate** — the simulated client's verdict from `/v1/admin/score` (same deterministic scoring as a real
  submission, no Connects spent). The rule-based client brain rewards naming must-have skills, personalisation, a
  concrete result, fair price and length; it penalises generic openings, contact details, guarantees and unanswered
  questions. **It does not check whether claims are true** (see the report's reply-gap analysis).

## Handling
- Generated / derived artefacts under `data/processed/` and `.cache/` are git-ignored.
- No hidden test set exists in this repository; the instructor's hidden run uses its own jobs against the live URL.
- The live Upwork mode never stores job or client data beyond the user's own inbox rows, scoped by user id.

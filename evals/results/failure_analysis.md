| # | Job | Failure category | Node | What went wrong | Fixed? |
|---|---|---|---|---|---|
| 1 | `dev-ai-024` | wrong bid (partial fit) | decide (Fit Matcher score) | fit 0.67 >= 0.55 but gold coverage < 0.6 | yes |
| 2 | `dev-ai-039` | wrong bid (partial fit) | decide (Fit Matcher score) | fit 1.00 >= 0.55 but gold coverage < 0.6 | no |
| 3 | `dev-ai-042` | wrong bid (partial fit) | decide (Fit Matcher score) | fit 0.57 >= 0.55 but gold coverage < 0.6 | yes |
| 4 | `dev-web-155` | wrong skip | fit_matcher | gold bid, predicted skip (fit 0.00) | no |
| 5 | `dev-ai-000` | mispriced | pricing | old quote 45.0 outside band [46.8, 63.2]; new quote 57.3 | yes |
| 6 | `dev-ai-001` | mispriced | pricing | old quote 2803.6 outside band [3090.0, 4170.0]; new quote 3893.0 | yes |
| 7 | `dev-web-047` | missed evidence | fit_matcher / retrieval | Recall@5 0.00 (partial, 3 requirements) | no |
| 8 | `dev-ai-066` | missed evidence | fit_matcher / retrieval | Recall@5 0.33 (vague, 3 requirements) | no |
| 9 | `dev-ai-194` | unsupported claim | writer -> verifier | 4 unsupported claims before verification, 0 after | yes |
| 10 | `dev-web-143` | unsupported claim | writer -> verifier | 4 unsupported claims before verification, 0 after | yes |
| 11 | `dev-ai-184` | generic opening / low coverage | writer | proof never named the client's must-have skill; simulated client did not reply | no |
| 12 | `dev-ai-167` | generic opening / low coverage | writer | proof never named the client's must-have skill; simulated client did not reply | no |

| Category | Fix tried | Measured effect |
|---|---|---|
| wrong bid (partial fit) | Raised bid_min_fit 0.55 -> 0.70 (middle of the plateau in threshold_sweep.json) | partial-fit accuracy 61.7% -> 90.0%, bid F1 0.918 -> 0.976 on the same 600 jobs |
| mispriced | Pricing v2: anchor on the job's own budget range instead of the category median | price inside fair band 52.8% -> 86.2% (pricing_eval.json, 282 jobs); remaining misses are hourly jobs where the client range sits below market |
| missed evidence | Skill graph (V9) + requirement decomposition; corrective grader marks the requirement unsupported instead of guessing | Recall@5 0.740 -> 0.890; residual misses are hard paraphrases with no skill keyword (e.g. 'a document store') |
| unsupported claim | Strict number/tool rule + rewrite-then-reverify; fallback writer v3 opening without an uncited claim | unsupported claims per proposal 1.13 -> 0.34 before verification, 0 after (retrieval_outcome_test.json) |
| generic opening / low coverage | Name the client's requirement next to the proof that covers it (writer prompt v2.5 + fallback writer) | simulated reply rate 15.6% -> 64.4% for the shipped pipeline on the same 90 jobs |
| wrong skip | None yet: these are gold-bid jobs whose requirement sentences contain only hard paraphrases, so the Fit Matcher finds no skill and the dense fallback stays under the 0.83 cosine grader | not fixed - candidate fix: LLM requirement rewrite in the corrective loop (llm_rewrite option), not enabled because of the free-tier token budget |

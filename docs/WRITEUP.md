# Better retrieval made my simulated clients reply less — and that was the most useful bug I found

*Abdul Ghufran · AI-4016 R&D project "GigBid" · every number links to a results file in the
[GigBid repository](https://github.com/Abdul-Ghufran/gigbid/tree/main/evals/results)*

I spent two weeks building GigBid, a multi-agent copilot for freelancers. A Scout pulls new jobs; an Analyst, a Risk
Assessor and a Fit Matcher read each post in parallel; a Writer drafts a proposal in which every claim has to point at a
piece of the freelancer's portfolio; a verifier, a Critic and a Compliance Guard check it; and nothing is sent until a
human approves it. The system is graded against GigSim, a marketplace simulator whose clients have hidden preferences
and decide whether to reply, interview or hire.

I expected the hard part to be the agents. It wasn't. The most surprising result came from the least glamorous
component — retrieval — and it was a negative one.

## The retrieval work went exactly as planned

The portfolio corpus is built to defeat naive RAG: the same project described three different ways (case study,
README, the phrase used in old proposals), skills implied by code imports but never named in prose, and client job
posts that paraphrase ("background jobs that run off the request path" instead of "Celery").

I implemented ten retrieval variants and measured them on 444 dev jobs with gold evidence labels
([`rag_variants_offline.json`](https://github.com/Abdul-Ghufran/gigbid/blob/main/evals/results/rag_variants_offline.json)).
The naive baseline — fixed chunks, cosine similarity against the whole job post — reached evidence Recall@5 of 0.740.
Splitting the post into one query per requirement helped a little (0.762). A cross-encoder reranker helped a little
more (0.769) while being sixty times slower. "Outcome-aware" ranking, which boosts projects that appeared in proposals
that won, made things *worse* (0.642): winning projects are not the relevant ones for a new job.

The winner was unexpectedly old-fashioned: a skill graph. Normalise every requirement and every portfolio item to
canonical skills (with synonyms and code-import signals), connect skills to projects, industries and outcomes, and walk
the graph — with dense retrieval only as a fallback for requirements that name no recognisable skill. Recall@5 0.911,
MRR 0.875, p95 latency 3 ms. On top of it I put a corrective loop: grade each requirement's evidence, re-query weak
ones, and mark requirements with no evidence as **unsupported** so the Writer is forbidden from claiming them. That
traded half a point of recall for eight points of MRR (0.951) and gave the system the ability to say "I have not done
this" ([`rag_ablation.json`](https://github.com/Abdul-Ghufran/gigbid/blob/main/evals/results/rag_ablation.json)).

So far, a tidy story: measure, pick the best, ship it.

## Then I connected it to the simulated clients

To see whether better evidence produced better *outcomes*, I held everything else fixed: the same 90 gold-bid jobs, the
same deterministic writer, the same price. The only difference was the retrieval pipeline. The shipped pipeline's
letters contained 1.13 unsupported claims per proposal before verification versus 2.07 for the naive baseline. Good.

And GigSim's clients replied to **15.6 %** of the shipped pipeline's proposals — versus **37.8 %** for the naive
baseline ([`proposals_best_fixedwriter.json`](https://github.com/Abdul-Ghufran/gigbid/blob/main/evals/results/proposals_best_fixedwriter.json),
[`proposals_v0_fixedwriter.json`](https://github.com/Abdul-Ghufran/gigbid/blob/main/evals/results/proposals_v0_fixedwriter.json)).

Better retrieval, more honest proposals, less than half the replies.

## Why it happened

I re-scored both sets and logged the simulated client's internal features
([`reply_gap_analysis.json`](https://github.com/Abdul-Ghufran/gigbid/blob/main/evals/results/reply_gap_analysis.json)).
The difference was almost entirely one feature: **must-have coverage** — whether the proposal names the client's
must-have skills. 0.47 for the naive pipeline, 0.20 for the good one.

The mechanism was subtle. The naive retriever often returns READMEs and code files with no measurable outcome. When the
writer has a weak piece of evidence like that, it falls back to restating the requirement: *"My README for
fleet-live covers real-time updates with WebSockets."* That sentence is barely evidence — but it repeats the client's
own words. The good retriever returns case studies with concrete results, so the writer leads with the result:
*"In the live fleet map project, the work tracked 600 vehicles with sub-second updates."* A stronger claim — that never
mentions "WebSockets".

The simulator rewards keyword coverage. It cannot check whether a claim is true. My better system was losing to my
worse one because it was *more specific and less parroting*, and the grader only noticed the parroting.

Two lessons were tangled together here:

1. **A simulator measures what it measures.** GigSim's clients are a reasonable proxy for "does this proposal speak to
   my requirements", and a terrible proxy for "is this true". A reply-rate number from it is only meaningful next to an
   independent truthfulness metric — which is why every proposal result in GigBid reports unsupported claims alongside
   reply rate, and why the verifier is calibrated on its own labelled set rather than trusted.
2. **The simulator was also right about something.** Real clients skim. A proof that never names their requirement
   makes them do the mapping. The fix was not to retrieve worse evidence; it was to *name the requirement next to the
   proof that covers it*: *"For your real-time tracking with WebSockets: in the live fleet map project, the work tracked
   600 vehicles…"*. That is honest — the requirement is only named when the evidence for it passed the grader.

## What the fix did

I changed one line of the writer (and the equivalent instruction in the LLM writer's prompt), re-ran both pipelines on the
same 90 jobs, and later removed an uncited "I have done this before" opening that the verifier was — correctly —
deleting from every letter. With the final writer
([`retrieval_outcome_test.json`](https://github.com/Abdul-Ghufran/gigbid/blob/main/evals/results/retrieval_outcome_test.json)):

| | Unsupported claims / proposal | Simulated client score | Interview rate | Reply rate |
|---|---|---|---|---|
| Naive retrieval | 1.48 | 1.09 | 21 % | 72 % |
| Shipped retrieval | **0.34** | **1.25** | **33 %** | 64 % |

Unsupported claims fell more than four-fold (Wilcoxon p < 0.001) and the client's score rose (paired t-test
p < 0.001). Interviews rose by twelve points (McNemar p = 0.08). Reply rate was *lower* but not significantly (p = 0.26).
In other words: on the measures that track truth and depth, better retrieval clearly wins; on the shallowest measure it is
a coin flip. I would ship it without hesitation — a proposal that gets a reply by implying experience you don't have is
a liability, not a lead.

## The second surprise: my own verifier was lying to me

The claim verifier splits each draft into claims and checks each against the cited evidence: semantic similarity, plus
"every number in the claim appears in the evidence" and "every tool named in the claim is demonstrated by the evidence".
I built a labelled set of 302 claims — true ones, and fabrications with a wrong number, a tool the project never used, a
wrong citation, or invented years of experience.

The first version caught 100 % of invented experience and wrong citations — and **0 %** of wrong numbers and **6 %** of
wrong tools ([`verifier_eval_v1_rule.json`](https://github.com/Abdul-Ghufran/gigbid/blob/main/evals/results/verifier_eval_v1_rule.json)).
It was labelling "cut lookup time by 85 %" against evidence that said 9 minutes to 40 seconds as *partly supported*:
the gist matched, only "a detail" was off. But for a freelancer, the number *is* the claim. Making any unmatched number or
tool an automatic "unsupported" took F1 from 0.69 to 0.99 — and a lightweight bi-encoder then performed exactly as well as
the cross-encoder, which let me drop the reranker from the 512 MB deployment
([`verifier_eval.json`](https://github.com/Abdul-Ghufran/gigbid/blob/main/evals/results/verifier_eval.json)).

## What I'd tell someone building the next one

- **Put a truth metric next to every outcome metric.** Reply rate alone would have pushed me to ship the worse retriever.
- **Read your simulator's features, not just its verdicts.** The explanation was one column away.
- **Old ideas are underrated.** A skill graph with a synonym list beat dense retrieval, hybrid search and a reranker on
  this corpus — because the corpus is about *skills*, and the graph encodes exactly that.
- **Label your own checker.** Thirty minutes of building a labelled claim set found the bug that would otherwise have
  let fabricated numbers through every proposal.

The code, the simulator, all evaluation scripts and every result file are public in the repository.

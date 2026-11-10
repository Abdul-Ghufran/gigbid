# ADR-002: Ship the corrective loop over the skill graph (V8 on V9)

**Decision.** `rag.shipped_variant: v8_corrective` with `base: v9_skill_graph`, grader threshold 0.83 cosine.

**Evidence.** `evals/results/rag_variants_offline.json`, `rag_ablation.json`, `grader_calibration_v9.json`: V9 Recall@5 0.911 vs V0 0.740; the corrective loop trades 0.5 pt Recall@5 for +7.9 pt MRR and +7.3 pt nDCG and supplies the per-requirement 'unsupported' signal the writer must respect.

**Rejected.** V3 cross-encoder reranking (+2.9 pt Recall@5 at 60x latency), V4 outcome boosting (-9.8 pt).

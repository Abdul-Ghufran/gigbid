# ADR-005: Verification with the bi-encoder, strict number/tool rule

**Decision.** Claims are unsupported if any number or named tool is absent from the evidence; semantic support measured with the embedding model (cosine >= 0.8 supported, >= 0.65 partly).

**Evidence.** `evals/results/verifier_eval.json`: F1 0.99 for both cross-encoder and bi-encoder after the rule change; the bi-encoder removes the reranker from RAM.

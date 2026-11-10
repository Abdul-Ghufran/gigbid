# ADR-003: Open models on Groq, routed per node

**Decision.** `open` profile: gpt-oss-20b for analyst, risk, compliance, verifier rewrites; gpt-oss-120b for writer, critic, liaison; bge-small embeddings on CPU. Qwen3.8-27B rejected for writing roles: Groq caps it at 1,000 output tokens/min and its tool calls were frequently malformed.

**Why.** The deployed link must run on open models with no GPU. Every node's model is in `agent/config.yaml`; fallback model then deterministic offline path.

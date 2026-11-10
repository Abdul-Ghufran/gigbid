# Résumé bullet (numbers from evals/results/)

- Built **GigBid**, a deployed multi-agent freelancer copilot (LangGraph, 3 custom MCP servers + Upwork/GitHub MCP, FastAPI, React) with human-approved, exactly-once submissions; a skill-graph + corrective RAG pipeline lifted evidence Recall@5 from 0.74 to 0.89 and MRR from 0.85 to 0.95 over dense retrieval on 444 dev jobs (`rag_ablation.json`).
- Cut unsupported proposal claims 4x (1.48 -> 0.34 per proposal, p < 0.001) with a calibrated claim verifier (F1 0.99 on 302 labelled claims) while catching 100% of scams and planted prompt injections in a 600-job dev set (`retrieval_outcome_test.json`, `verifier_eval.json`, `decision_eval_offline.json`).

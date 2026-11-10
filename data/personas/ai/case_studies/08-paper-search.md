---
id: ai-case-08
type: case_study
project: paper-search
date: 2024-08
client_industry: biotech
---
# Semantic search over research papers

## The problem
Scientists could not find relevant prior work across thousands of papers.

## What I did
- I wrote the core of it with FAISS, to keep latency low under load.
- Brought in transformers so the system scales cleanly.
- Brought in fastapi backend to make results reproducible.

## Outcome
The work returned a relevant paper in the top 3 for 91% of test queries.

_Timeline: about 9 weeks. Client industry: biotech._
# GigBid Portfolio MCP server

A read-only [Model Context Protocol](https://modelcontextprotocol.io) server that turns a freelancer's portfolio —
CV, case studies, GitHub repos (README **and** code), client reviews and past proposals with their outcomes — into
evidence an AI assistant can cite. Plug it into Claude Desktop, Cursor or any MCP host and ask things like
*"answer this screening question from my portfolio"* or *"have I done Celery for a fintech client?"*.

It is the retrieval layer of [GigBid](https://github.com/Abdul-Ghufran/gigbid), so it ships the pipeline that won GigBid's
evaluation: requirement decomposition → skill graph (skills ↔ projects ↔ industries ↔ outcomes) with dense fallback →
a corrective grader that marks requirements it **cannot** prove (`supported: false`), so the assistant does not invent
experience. On GigBid's dev set it reached evidence Recall@5 0.89 and MRR 0.95 versus 0.74 / 0.85 for naive dense
retrieval (`evals/results/rag_ablation.json`). Embeddings run locally on CPU (bge-small via ONNX); no API key needed.

## Install and run

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11–3.12.

```bash
uvx --from git+https://github.com/Abdul-Ghufran/gigbid gigbid-portfolio-mcp --portfolio-dir /path/to/my_portfolio
```

Docker:

```bash
docker build -f infra/docker/mcp-portfolio.Dockerfile -t gigbid-portfolio-mcp .   # after building infra/docker/python-base.Dockerfile
docker run -i --rm -v /path/to/my_portfolio:/portfolio gigbid-portfolio-mcp python -m mcp_servers.portfolio.server --portfolio-dir /portfolio
```

### Claude Desktop / Cursor config

```json
{
  "mcpServers": {
    "portfolio": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Abdul-Ghufran/gigbid", "gigbid-portfolio-mcp",
               "--portfolio-dir", "/absolute/path/to/my_portfolio"]
    }
  }
}
```

The first start downloads the embedding model (~130 MB) into `~/.cache/gigbid`.

## Portfolio folder layout

```
my_portfolio/
├── cv.pdf                       # optional
├── case_studies/*.md            # optional front matter: id, project, date, client_industry
├── repos/<repo-name>/README.md  # and any source files (.py .ts .js .sql ...) - imports reveal implied skills
├── reviews.jsonl                # {"id", "text", "rating", "project", "date", "client_industry"}
└── proposals.jsonl              # {"id", "text", "job_title", "outcome": "won|replied|ignored", "project", "date"}
```

Try it with a demo persona from the repo: `--portfolio-dir data/personas/web` (or `ai`, `data`).

## What it exposes

| Kind | Name | What it does |
|---|---|---|
| tool | `search_evidence(requirement, k, filters)` | Evidence items (type, source, date, outcome, skills, snippet) that prove **one** requirement; `supported=false` means do not claim it. Filters: `types`, `since`, `industry`. |
| tool | `get_case_study(id)` | Full case study plus the ids of the same project's README, code and reviews |
| tool | `list_skills()` | Every skill the portfolio demonstrates, with item and project counts |
| tool | `have_i_done(skill, industry?)` | Skill-graph answer to "have I done X for a client in industry Y?" |
| resource | `portfolio://case/{id}`, `portfolio://proposal/{id}`, `portfolio://item/{id}`, `portfolio://profile` | Load full items |
| prompt | `answer_screening_question`, `prove_requirement`, `tailored_opening`, `skills_gap` | Ready-made workflows a freelancer actually uses |

All tools are annotated `readOnlyHint: true`. Over stdio the server is local and single-user; over HTTP
(`--transport http`) it requires a signed bearer token (used inside GigBid).

## Safety
Job posts you paste into prompts are treated as untrusted text by the prompt templates. The server never writes,
never calls the network except to download the embedding model once, and never sends your portfolio anywhere.

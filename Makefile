# GigBid - make dev | test | eval | seed | demo | lint
PY ?= $(if $(wildcard .venv/Scripts/python.exe),.venv/Scripts/python.exe,$(if $(wildcard .venv/bin/python),.venv/bin/python,python))
COMPOSE = docker compose -f infra/docker-compose.yml

.PHONY: install dev up down test unit contract e2e eval eval-smoke seed demo lint openapi freeze-gigsim

install:            ## Python + web dependencies
	uv venv --python 3.12 .venv && uv pip install --python $(PY) -e ".[dev]"
	cd apps/web && npm ci

dev:                ## API (in-process worker, MCP and GigSim) + Vite dev server
	MCP_TRANSPORT=memory GIGSIM_INPROCESS=1 $(PY) -m uvicorn apps.api.main:app --reload --port 8000 & \
	cd apps/web && npm run dev

up:                 ## full stack: web, api, worker, 3 MCP servers, GigSim, Postgres, Redis (+ ollama with --profile local)
	$(COMPOSE) --profile build build python-base && $(COMPOSE) up --build

down:
	$(COMPOSE) down

test: unit contract ## unit + contract tests (Playwright: make e2e)

unit:
	LLM_OFFLINE=1 $(PY) -m pytest -q tests/unit tests/integration mcp_servers

contract:
	LLM_OFFLINE=1 $(PY) -m pytest -q tests/contract

e2e:
	cd apps/web && npm run build && npx playwright test

eval:               ## full evaluation suite -> evals/results/*.json
	$(PY) -m evals.runners.rag_eval
	$(PY) -m evals.runners.decision_eval
	$(PY) -m evals.runners.gigsim_outcomes
	$(PY) -m evals.runners.injection_eval
	$(PY) -m evals.runners.verifier_eval

eval-smoke:         ## 30-job smoke eval with CI thresholds
	$(PY) -m evals.runners.smoke --jobs 30

seed:               ## regenerate the synthetic world (personas, GigSim seed, dev set)
	$(PY) -m tools.synth.build

demo:               ## advance GigSim time so clients react (needs a running stack)
	curl -s -X POST -H "X-Admin-Token: $${GIGSIM_ADMIN_TOKEN:-gigsim-admin}" "$${GIGSIM_BASE_URL:-http://localhost:8081}/v1/admin/tick?minutes=180"

lint:
	$(PY) -m ruff check .
	$(PY) -m tools.ci_checks
	cd apps/web && npm run typecheck

openapi:            ## regenerate the typed TypeScript client from FastAPI
	$(PY) tools/export_openapi.py && cd apps/web && npm run gen:api

freeze-gigsim:
	$(PY) -m tools.ci_checks --freeze-gigsim

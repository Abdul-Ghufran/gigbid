# Single-container image for Render's free tier (512 MB): API + in-process worker + in-process MCP servers
# (real MCP JSON-RPC over memory streams) + GigSim, serving the built web app.  See docs/RUNBOOK.md.
FROM node:22-alpine AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 GIGBID_CACHE_DIR=/app/.cache \
    MCP_TRANSPORT=memory GIGSIM_INPROCESS=1 INPROCESS_SCHEDULER=1 OMP_NUM_THREADS=1 MALLOC_ARENA_MAX=2
WORKDIR /app
COPY . .
COPY --from=web /web/dist ./apps/web/dist
RUN pip install --upgrade pip && pip install -e . && python -m tools.warm_models && rm -rf /root/.cache
EXPOSE 8000
CMD ["sh", "-c", "uvicorn apps.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-keep-alive 75"]

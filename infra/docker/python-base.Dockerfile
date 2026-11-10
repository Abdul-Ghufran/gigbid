# Shared Python image for api, worker, MCP servers (each service Dockerfile builds FROM this).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 GIGBID_CACHE_DIR=/app/.cache
WORKDIR /app
COPY . .
RUN pip install --upgrade pip && pip install -e . && python -m tools.warm_models && rm -rf /root/.cache

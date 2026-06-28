# ── Build frontend ──────────────────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ .
RUN npm run build

# ── Build Python package ────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build
COPY llm_apipool/ ./llm_apipool/
COPY pyproject.toml README.md CHANGELOG.md CONTRIBUTING.md PROVIDER_GUIDE.md ./
COPY alembic.ini alembic/ ./alembic/
COPY --from=frontend-builder /build/web/ ./web/

RUN pip install --no-cache-dir build && python -m build --wheel

# ── Runtime ─────────────────────────────────────────────────────────────────
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the wheel and install
COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/llm_apipool*.whl[all] && rm /tmp/*.whl

# Copy built frontend assets
COPY --from=frontend-builder /build/web/ /app/web/

# Volume for persistent data
VOLUME ["/data"]

ENV LLM_APIPOOL_DB=/data/keys.db \
    LLM_APIPOOL_API_KEY="" \
    LLM_APIPOOL_ENCRYPTION_KEY="" \
    LLM_APIPOOL_HEALTH_CHECK_INTERVAL=300

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

ENTRYPOINT ["llm-apipool"]
CMD ["proxy", "--host", "0.0.0.0", "--port", "8000"]

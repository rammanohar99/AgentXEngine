# Build context must be the repo root:
#   docker build -f apps/backend/Dockerfile .
#
# docker-compose.yml sets context: . (repo root) for this service.

# ── Stage 1: dependency builder ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only the dependency manifest first for layer caching
COPY apps/backend/pyproject.toml .

RUN pip install --upgrade pip && \
    pip install --prefix=/install .


# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

# Copy application source
COPY apps/backend/app/ ./app/

# Copy Alembic migrations
COPY apps/backend/alembic/ ./alembic/
COPY apps/backend/alembic.ini ./alembic.ini

# Copy monorepo packages (agent runtime, tools, etc.)
COPY packages/ ./packages/

# Non-root user
RUN useradd --no-create-home --shell /bin/false appuser && \
    chown -R appuser:appuser /app
USER appuser

# PYTHONPATH includes /app so both `app` and `packages` are importable
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

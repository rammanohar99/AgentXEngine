---
title: Infrastructure Overview
domain: infrastructure
doc_type: architecture
status: active
owner: infrastructure
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: medium
tags: [infrastructure, docker, cloud-run, ci-cd, alembic, celery, kubernetes, terraform]
---

# Infrastructure Overview

**Related:** [Architecture Overview](../architecture/overview.md) · [Onboarding — Getting Started](../onboarding/getting-started.md) · [Phase 7 Roadmap](../roadmap/phase-07-production-state.md)

---

## Local Development (Docker Compose)

All services run locally via Docker Compose:

| Service | Image | Port | Purpose |
|---|---|---|---|
| `postgres` | pgvector/pgvector:pg16 | 5432 | Vector database |
| `redis` | redis:7.4-alpine | 6379 | Cache, queue, session state |
| `backend` | FastAPI + uvicorn | 8000 | API server |
| `frontend` | Vite dev server | 3000 | React UI |
| `worker` | Celery | — | Background task processor |

```bash
# Start everything
docker compose up

# Infrastructure only (for local hot-reload development)
docker compose up postgres redis
```

---

## Database Migrations (Alembic)

All schema changes go through Alembic. Never modify the database schema directly.

```bash
cd apps/backend

# Create a new migration
alembic revision --autogenerate -m "add vector_memory_entries table"

# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history
```

Migration files live in `apps/backend/alembic/versions/`.

---

## Celery Workers

Background tasks for:
- **Document ingestion** — chunking + embedding, avoids blocking the API
- **Memory summarization** — triggered when short-term memory fills

Tasks retry on transient failures with exponential backoff.

**Known gap:** No dead letter queue for permanently failed tasks. Tracked for Phase 7.

Worker startup:
```bash
cd apps/backend
celery -A app.workers.celery_app worker --loglevel=info
```

---

## Cloud Run (Production)

Production deployment via Google Cloud Run:

- Secrets via Google Secret Manager (never in environment variables in production)
- Database via Cloud SQL (managed PostgreSQL with pgvector)
- Health probes: liveness and readiness both at `GET /health`
- Auto-scaling based on request concurrency
- Min instances: 1 (avoid cold starts)

Deployment:
```bash
./scripts/deploy.sh
```

---

## CI/CD Pipeline (GitHub Actions)

Runs on every push to `main`/`develop` and every PR.

**Backend pipeline:**
1. `ruff check .` — lint
2. `black --check .` — format check
3. `mypy app/` — type check
4. `pytest` — tests

**Frontend pipeline:**
1. `eslint` — lint
2. `tsc --noEmit` — type check
3. `npm run build` — build

**Docker pipeline (main branch only):**
1. Build backend image
2. Build frontend image
3. Push to Artifact Registry

**Rule:** Never merge a broken build.

Configuration: `.github/workflows/ci.yml`

---

## Kubernetes (In Progress)

Kubernetes manifests in `infrastructure/k8s/`. Not yet production-ready.

Planned:
- Deployment manifests for backend and worker
- HorizontalPodAutoscaler
- ConfigMap for non-secret configuration
- ExternalSecret for secrets from Secret Manager

---

## Terraform (In Progress)

Infrastructure as code in `infrastructure/terraform/`. Not yet production-ready.

Planned:
- Cloud Run service
- Cloud SQL instance
- Redis (Memorystore)
- Artifact Registry
- IAM bindings

---

## Health Checks

`GET /health` returns:
```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected"
}
```

Returns 200 if healthy, 503 if any dependency is unavailable.
Used by Cloud Run for liveness and readiness probes.

**Implementation:** `apps/backend/app/api/health.py`

---

## Rate Limiting

Rate limiting is applied on all LLM endpoints via Redis sliding window counters.
Falls back to in-process counters if Redis is unavailable.

**Implementation:** `apps/backend/app/core/rate_limit.py`

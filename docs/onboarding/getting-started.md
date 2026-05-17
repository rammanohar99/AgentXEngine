---
title: Getting Started
domain: onboarding
doc_type: guide
status: active
owner: platform-engineering
last_reviewed: 2026-05-18
stability: evergreen
retrieval_priority: high
tags: [onboarding, setup, quickstart, orientation, new-engineer]
---

# Getting Started

**Related:** [Engineering Principles](engineering-principles.md) · [Architecture Overview](../architecture/overview.md) · [Agent Runtime](../architecture/agent-runtime.md) · [Reliability Principles](../reliability/principles.md)

---

## Prerequisites

- Python 3.12+
- Node 22+
- Docker + Docker Compose
- One of:
  - Google Cloud project with Vertex AI API enabled
  - Gemini API key (simpler for local development)

---

## Setup

```bash
# 1. Clone the repository
git clone <repo-url>
cd ai-engineering-os

# 2. Run first-time setup (creates virtualenvs, installs deps)
./scripts/setup.sh

# 3. Configure credentials
cp apps/backend/.env.example apps/backend/.env
vim apps/backend/.env
# Set GEMINI_API_KEY (easiest) or GOOGLE_CLOUD_PROJECT + GOOGLE_CLOUD_LOCATION
```

---

## Start the Stack

```bash
# Full stack (all services)
docker compose up

# Or: infrastructure only + local hot-reload servers
docker compose up postgres redis

# Backend (separate terminal)
cd apps/backend
source .venv/bin/activate
uvicorn app.main:app --reload

# Frontend (separate terminal)
cd apps/frontend
npm run dev
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

---

## Run the Tests

```bash
cd apps/backend
pytest                    # All tests
pytest tests/test_health.py   # Single file
pytest -k "chunker"           # Pattern match
```

---

## Codebase Orientation

Start with these files in order:

1. **[Architecture Overview](../architecture/overview.md)** — system design, request flow, key decisions
2. **[Agent Runtime](../architecture/agent-runtime.md)** — the most important component
3. **`packages/agents/runtime.py`** — the ReAct loop implementation
4. **`apps/backend/app/services/agent.py`** — how the API layer uses the runtime
5. **[Reliability Principles](../reliability/principles.md)** — rules you must not violate

---

## Where Things Live

| What you want to change | Where to look |
|---|---|
| API endpoint | `apps/backend/app/api/` |
| Business logic | `apps/backend/app/services/` |
| Agent runtime behavior | `packages/agents/runtime.py` |
| Tool implementations | `packages/agents/tools/` |
| RAG pipeline | `packages/rag/` |
| Memory systems | `packages/memory/` |
| Observability / tracing | `packages/observability/` |
| Database schema | `apps/backend/alembic/versions/` |
| Frontend components | `apps/frontend/src/` |

---

## Before You Write Code

1. Read [AGENTS.md](../../AGENTS.md) — the engineering constitution
2. Read the relevant architecture doc for the area you're changing
3. Read the existing implementation files — understand the patterns
4. Check for existing implementations before creating new ones
5. Verify your change does not violate any principle in this document

---

## Before You Submit a PR

```bash
cd apps/backend
ruff check .          # Lint
black --check .       # Format check
mypy app/             # Type check
pytest                # Tests

cd apps/frontend
npm run lint
npm run typecheck
npm run build
```

Also verify:
- [ ] No new retry layer added above `VertexAIService`
- [ ] No runtime objects created per-request that should be long-lived
- [ ] All new external calls have timeouts
- [ ] All new subsystem failures degrade gracefully
- [ ] All new operations emit `metric.*` events
- [ ] No secrets committed
- [ ] Docker builds successfully

---

## Common Tasks

### Add a new API endpoint

1. Add route handler in `apps/backend/app/api/`
2. Add business logic in `apps/backend/app/services/`
3. Add Pydantic schemas in `apps/backend/app/schemas/`
4. Register route in `apps/backend/app/api/router.py`

### Add a new tool

See [Tool Reference — Adding a New Tool](../tools/reference.md#adding-a-new-tool).

### Add a database table

```bash
cd apps/backend
alembic revision --autogenerate -m "add my_table"
# Review the generated migration in alembic/versions/
alembic upgrade head
```

### Add a new memory type

Implement the interface in `packages/memory/` and register it in `packages/memory/manager.py`.

---

## Getting Help

- Architecture questions → [docs/architecture/](../architecture/)
- Reliability questions → [docs/reliability/](../reliability/)
- Why was X decided this way → [docs/adr/](../adr/)
- Operational procedures → [docs/runbooks/](../runbooks/)

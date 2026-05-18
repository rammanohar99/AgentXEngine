# AgentXEngine

A production-grade multi-agent AI platform for autonomous code understanding,
repository analysis, RAG, and engineering workflows.

> This is not a chatbot. It is an **AI Operating System** — a runtime infrastructure
> platform for autonomous agent execution, multi-agent orchestration, and observable,
> replayable, recoverable AI workflows.

---

## What This Is

| Capability | Description |
|---|---|
| Agent Runtime | ReAct loop with circuit breaker, retry, and timeout enforcement |
| Multi-Agent Orchestration | One orchestrator + 5 specialist agents with filtered tool registries |
| RAG Pipeline | Ingest → Chunk → Embed → Store → Retrieve → Rerank → Assemble |
| Memory Systems | Short-term, long-term (Redis), summarized, and vector episodic memory |
| Evaluation | LLM-as-judge quality scoring on every agent run |
| Observability | Langfuse tracing, OpenTelemetry, structured logs, metric events |
| Workflow Engine | DAG-based multi-agent task execution with dependency resolution |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, Python 3.12+, Pydantic v2 |
| Frontend | React 18, TypeScript, Tailwind CSS, shadcn/ui |
| AI | Vertex AI Gemini 2.0 Flash, Google Gen AI SDK, text-embedding-004 |
| Database | PostgreSQL 16 + pgvector |
| Cache / Queue | Redis 7, Celery |
| Observability | Langfuse, OpenTelemetry, structlog |
| Deployment | Docker Compose (local), Cloud Run (production), GitHub Actions (CI/CD) |

---

## Quickstart

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose)
- [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) — for Vertex AI auth **or** a [Gemini API key](https://aistudio.google.com/app/apikey) (simpler, no GCP needed)
- Python 3.12+ — only needed for local development outside Docker
- Node 22+ — only needed for local frontend development outside Docker

### 1. Clone the repo

```bash
git clone https://github.com/rammanohar99/AgentXEngine
cd AgentXEngine
```

### 2. Configure environment variables

```bash
# Backend
cp apps/backend/.env.example apps/backend/.env

# Frontend (optional — only needed for production deploys)
cp apps/frontend/.env.example apps/frontend/.env
```

Open `apps/backend/.env` and set **one** of the following:

**Option A — Gemini API key** (quickest, no GCP setup needed):
```bash
GEMINI_API_KEY=your-api-key-here
```

**Option B — Vertex AI via Application Default Credentials**:
```bash
# Authenticate with Google Cloud (run once on your machine)
gcloud auth application-default login

# Then in apps/backend/.env set:
GOOGLE_CLOUD_PROJECT=your-gcp-project-id

# And set your local gcloud config path so Docker can mount it:
# Windows:
GCLOUD_CONFIG_DIR=C:/Users/<your-username>/AppData/Roaming/gcloud
# macOS/Linux:
GCLOUD_CONFIG_DIR=~/.config/gcloud
```

### 3. Start the full stack

```bash
docker compose up
```

This starts PostgreSQL, Redis, the FastAPI backend, Celery worker, and the React frontend.

### 4. Run database migrations

In a separate terminal, once the backend container is healthy:

```bash
docker compose exec backend alembic upgrade head
```

### 5. Open the app

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |

---

### Local Development (hot-reload, without Docker)

Run only the infrastructure in Docker, and the app processes natively:

```bash
# Start only Postgres and Redis
docker compose up postgres redis

# Backend (in a new terminal)
cd apps/backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload

# Frontend (in a new terminal)
cd apps/frontend
npm install
npm run dev
```

Frontend dev server runs at http://localhost:5173 and proxies `/api` to the backend automatically.

---

## Repository Structure

```
apps/
  backend/          FastAPI — API layer, services, Celery workers
  frontend/         React + TypeScript — chat UI, streaming, tool visualization

packages/
  agents/           Runtime core: ReAct loop, planner, executor, orchestrator
  rag/              Ingestion, chunking, embedding, reranking, retrieval
  memory/           Short/long/summarized/vector memory systems
  observability/    Langfuse tracing, OpenTelemetry, evaluation, metrics
  workflows/        Multi-agent workflow engine (DAG executor)
  tools/            Tool implementations (filesystem, web, GitHub, database)
  shared/           Shared types and utilities

infrastructure/
  docker/           Service init scripts
  k8s/              Kubernetes manifests
  terraform/        Infrastructure as code

docs/               Architecture, ADRs, runbooks, onboarding
scripts/            Dev, test, and deploy scripts
tests/              Integration and system tests
```

---

## Development

### Backend

```bash
cd apps/backend

ruff check .                          # Lint
black .                               # Format
mypy app/                             # Type check
pytest                                # Tests
pytest tests/test_benchmarks.py \
  --benchmark-only --benchmark-sort=mean   # Benchmarks

alembic revision --autogenerate -m "description"   # New migration
alembic upgrade head                               # Apply migrations
```

### Frontend

```bash
cd apps/frontend
npm run lint
npm run typecheck
npm run build
```

---

## Documentation

| Document | Purpose |
|---|---|
| [Architecture Overview](docs/architecture/overview.md) | System design, request flow, data flow, key decisions |
| [Agent Runtime](docs/architecture/agent-runtime.md) | ReAct loop, planner, executor, orchestrator, lifecycle rules |
| [RAG Pipeline](docs/architecture/rag-pipeline.md) | Ingestion, chunking, embedding, retrieval, reranking |
| [Memory Systems](docs/architecture/memory-systems.md) | Memory types, summarization, failure isolation |
| [Reliability](docs/reliability/principles.md) | Retry ownership, circuit breaker, timeouts, graceful degradation |
| [Observability](docs/observability/overview.md) | Logging, tracing, metrics, correlation IDs |
| [Evaluation](docs/evaluation/overview.md) | LLM-as-judge, trajectory evaluation, hallucination detection |
| [Performance](docs/performance/overview.md) | Latency hierarchy, benchmarks, optimization targets |
| [Context Engineering](docs/architecture/context-engineering.md) | Token budget, truncation, memory injection |
| [Tool Reference](docs/tools/reference.md) | All tools, parameters, security boundaries |
| [Infrastructure](docs/infrastructure/overview.md) | Docker, Cloud Run, CI/CD, migrations |
| [ADRs](docs/adr/) | Architectural decision records |
| [Onboarding](docs/onboarding/getting-started.md) | New engineer / agent setup guide |
| [Runbooks](docs/runbooks/) | Operational procedures |

---

## Implementation Phases

| Phase | Status | Description |
|---|---|---|
| 1 | ✅ Complete | FastAPI backend, React frontend, Vertex AI, Docker |
| 2 | ✅ Complete | Agent runtime (ReAct), all tools, RAG pipeline |
| 3 | ✅ Complete | Memory systems, Langfuse + OpenTelemetry |
| 4 | ✅ Complete | Multi-agent orchestration, Celery workers, workflow engine |
| 5 | ✅ Complete | Evaluation, rate limiting, Cloud Run + k8s + terraform |
| 6 | ✅ Complete | Reliability: circuit breaker, retry, timeouts, context budget |
| 6.1 | ✅ Complete | Reliability fixes: retry amplification, orchestrator lifecycle, memory degradation |
| 7 | 🔲 Next | Production state: Redis sessions, distributed circuit breaker |
| 8 | 🔲 Planned | Event-sourced runtime, execution journal, replayability |
| 9 | 🔲 Planned | DAG workflow engine, parallel task execution |
| 10 | 🔲 Planned | Advanced evaluation: trajectory, hallucination detection, regression benchmarks |
| 11 | 🔲 Planned | Performance observatory: p99 tracking, prompt caching |
| 12 | 🔲 Planned | Agent replay UI, trajectory visualization |
| 13 | 🔲 Planned | Context engineering: semantic compression, dynamic tool selection |
| 14 | 🔲 Planned | Browser agents, Docker sandbox execution |
| 15 | 🔲 Planned | Policy and governance engine |

---

## Environment Variables

See [`apps/backend/.env.example`](apps/backend/.env.example) for the full list.

```bash
# AI — one of these is required
GOOGLE_CLOUD_PROJECT=your-gcp-project-id   # Vertex AI mode
GEMINI_API_KEY=your-api-key                 # Developer API mode (takes priority)

GOOGLE_CLOUD_LOCATION=us-central1
VERTEX_AI_MODEL=gemini-2.0-flash
VERTEX_AI_FALLBACK_MODEL=gemini-2.0-flash-lite

# Infrastructure
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/aiengos
REDIS_URL=redis://localhost:6379/0

# Observability (optional)
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...
LANGFUSE_HOST=https://cloud.langfuse.com

# Reliability
LLM_TIMEOUT_SECONDS=60
TOOL_TIMEOUT_SECONDS=30
AGENT_RUN_TIMEOUT_SECONDS=300
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_RECOVERY_SECONDS=60
```

---

## Core Engineering Principles

**Always:**
- Write modular, composable code — small functions, single responsibility
- Use typed interfaces and Pydantic schemas everywhere
- Use async IO — never block the event loop
- Emit structured logs and metrics for every operation
- Read existing code before writing new code

**Never:**
- Place business logic inside routes
- Nest retry loops (retry amplification)
- Use in-memory state in production multi-replica deployments
- Swallow exceptions silently
- Grow context unboundedly
- Merge without passing tests

See [docs/onboarding/engineering-principles.md](docs/onboarding/engineering-principles.md) for the full constitution.

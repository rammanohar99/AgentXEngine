# Tests

Root-level test directory for cross-package integration tests.

Unit tests for individual packages live alongside the code they test:
- `apps/backend/tests/` — backend API, services, agent runtime, RAG, memory

## Running Tests

```bash
# All backend tests (from repo root)
python -m pytest apps/backend/tests/ -v

# Specific test file
python -m pytest apps/backend/tests/test_runtime.py -v

# With coverage
python -m pytest apps/backend/tests/ --cov=apps/backend/app --cov=packages/

# Fast (skip slow integration tests)
python -m pytest apps/backend/tests/ -m "not integration"
```

## Test Categories

| File | What it tests |
|---|---|
| test_planner.py | ReAct output parsing |
| test_tools.py | Filesystem tool sandbox |
| test_executor.py | Tool dispatch |
| test_runtime.py | Full ReAct loop (mocked LLM) |
| test_chunker.py | Document chunking |
| test_retrieval_tool.py | RAG retrieval tool |
| test_memory.py | All memory systems |
| test_tracer.py | Langfuse tracer |
| test_orchestrator.py | Multi-agent orchestration |
| test_evaluation.py | LLM-as-judge evaluation |
| test_vector_memory.py | Vector memory |
| test_reranker.py | RAG reranker |
| test_health.py | Health endpoints |
| test_config.py | Settings validation |

---
title: Incident Response Runbook
domain: reliability
doc_type: runbook
status: active
owner: platform-engineering
last_reviewed: 2026-05-18
stability: operational
retrieval_priority: high
tags: [runbook, incident-response, llm-degradation, redis, latency, circuit-breaker, operations]
related_adrs: [ADR-001, ADR-002, ADR-003, ADR-004]
related_incidents: [INC-001, INC-002, INC-003, INC-004]
---

# Incident Response Runbook

**Related:** [Reliability Principles](../reliability/principles.md) · [Observability Overview](../observability/overview.md) · [Incidents Index](../incidents/README.md)

---

## LLM Service Degraded (429 / 503)

**Symptoms:**
- Agent runs returning ERROR events
- `metric.llm_call` events with `success=false` and `error_type=rate_limit`
- Circuit breaker opening (`metric.circuit_breaker` with `event=opened`)

**Immediate actions:**
1. Check Vertex AI / Gemini API status page
2. Check `metric.circuit_breaker` events — is the breaker open?
3. If breaker is open, requests are being rejected immediately (this is correct behavior)
4. Check `metric.llm_call` for `retry_count` — are retries amplifying the problem?

**Resolution:**
- Wait for the circuit breaker recovery period (default: 60s)
- The breaker will transition to HALF_OPEN and probe with one request
- If the probe succeeds, the breaker closes and normal operation resumes
- If quota is exhausted (billing), the fallback model (`gemini-2.0-flash-lite`) will be tried

**Do not:**
- Restart the backend to "reset" the circuit breaker — this loses accumulated state
- Manually force the circuit breaker closed — let it recover naturally

---

## High Latency on RAG Queries

**Symptoms:**
- `metric.rag_retrieval` events with high `latency_ms`
- User-facing timeouts on document search

**Diagnosis:**
1. Check if reranking is enabled (`reranked=true` in `metric.rag_retrieval`)
2. If reranking is sequential (not concurrent), this is the bottleneck
3. Check `metric.llm_call` events during the query — are reranker calls sequential?

**Resolution:**
- Verify reranker uses `asyncio.gather` (see [ADR-004](../adr/004-concurrent-reranker.md))
- Reduce `top_k` temporarily if latency is critical
- Check pgvector index health: `SELECT * FROM pg_stat_user_indexes WHERE indexname LIKE '%embedding%'`

---

## Memory Summarization Failures

**Symptoms:**
- `summarization_skipped` warnings in logs
- Sessions growing large without summarization

**Diagnosis:**
1. Check if the LLM service is degraded (see above)
2. Check Redis connectivity: `redis-cli ping`
3. Check `metric.memory_operation` events for failures

**Resolution:**
- Memory summarization failures are non-fatal (see [ADR-003](../adr/003-graceful-memory-degradation.md))
- Agent runs continue with raw turns
- Summarization will resume when the LLM service recovers
- No manual intervention required unless sessions are growing unboundedly

---

## Redis Unavailable

**Symptoms:**
- `redis_unavailable` warnings in logs
- Rate limiting falling back to in-process counters
- Long-term memory falling back to in-process dict

**Diagnosis:**
1. `redis-cli -u $REDIS_URL ping`
2. Check Docker Compose: `docker compose ps redis`
3. Check Redis logs: `docker compose logs redis`

**Resolution:**
- Restart Redis: `docker compose restart redis`
- The system degrades gracefully — agent runs continue with in-process fallbacks
- Sessions created during Redis outage will be lost when the process restarts
- Rate limiting may be less accurate during the outage (per-replica counters)

---

## Database Connection Failures

**Symptoms:**
- 500 errors on document ingestion or search
- SQLAlchemy connection pool errors in logs

**Diagnosis:**
1. Check PostgreSQL: `docker compose ps postgres`
2. Check connection: `psql $DATABASE_URL -c "SELECT 1"`
3. Check connection pool: look for `QueuePool limit` errors in logs

**Resolution:**
- Restart PostgreSQL: `docker compose restart postgres`
- Run pending migrations: `alembic upgrade head`
- Check for long-running queries: `SELECT * FROM pg_stat_activity WHERE state = 'active'`

---

## Agent Run Producing Empty Responses

**Symptoms:**
- Agent runs completing with empty final answers
- Workflow tasks marked COMPLETE with no output

**Diagnosis:**
1. Check for ERROR events in the run stream
2. Check `metric.agent_run` for `success=false`
3. Check if the circuit breaker was open during the run
4. Check if the LLM call timed out (`error_type=timeout`)

**Context:**
This was a known bug (Phase 6.1): when a workflow task's LLM call failed,
the runtime emitted an ERROR event and returned empty text. The `WorkflowExecutor`
was collecting empty text and marking the task as COMPLETE.

**Resolution:**
- Verify `WorkflowExecutor` treats ERROR events as FAILED, not COMPLETE
- Check `metric.llm_call` for the run — did any calls fail?
- If the LLM service is healthy, check for context length exceeded errors

---

## Checking System Health

```bash
# Health endpoint
curl http://localhost:8000/health

# Recent errors (last 100 lines)
docker compose logs backend --tail=100 | grep '"level":"error"'

# Circuit breaker events
docker compose logs backend | grep 'metric.circuit_breaker'

# Agent run metrics
docker compose logs backend | grep 'metric.agent_run'

# LLM call metrics
docker compose logs backend | grep 'metric.llm_call'
```

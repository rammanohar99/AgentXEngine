---
title: "Phase 14: Browser and Sandbox Execution Agents"
domain: roadmap
doc_type: roadmap
status: planned
owner: agent-runtime
last_reviewed: 2026-05-18
stability: experimental
retrieval_priority: low
tags: [roadmap, phase-14, browser, playwright, sandbox, docker, execution]
---

# Phase 14: Browser and Sandbox Execution Agents

**Status:** 🔲 Planned (requires Phase 15 governance engine for safe deployment)
**Related:** [Tool Reference](../tools/reference.md) · [Phase 15 — Governance Engine](phase-15-governance-engine.md)

---

## Objective

Add two new agent capabilities: browser navigation via Playwright, and
arbitrary code execution in Docker-isolated sandboxes.

---

## Browser Agent

A new tool: `browser_navigate` — web navigation, form filling, scraping.

Built on Playwright. Capabilities:
- Navigate to URLs
- Click elements, fill forms
- Extract page content
- Take screenshots
- Wait for dynamic content

Security constraints:
- Allowlisted domains only (configurable)
- No access to internal network
- Session isolation per agent run
- Timeout: 30s per action

---

## Sandbox Execution Agent

A new tool: `execute_code` — run arbitrary code in an isolated Docker container.

Security constraints:
- Docker container per execution (no shared state)
- Resource limits: CPU (0.5 cores), memory (256MB), disk (100MB)
- Network: disabled by default
- Filesystem: ephemeral, destroyed after execution
- Timeout: 60s
- Allowlisted languages: Python, JavaScript, Bash

Requires Phase 15 governance engine for approval workflows on high-risk executions.

---

## Work Items

- [ ] `browser_navigate` tool implementation (Playwright)
- [ ] Domain allowlist configuration
- [ ] `execute_code` tool implementation (Docker SDK)
- [ ] Container resource limits and cleanup
- [ ] Integration with Phase 15 approval workflows
- [ ] Security audit before deployment

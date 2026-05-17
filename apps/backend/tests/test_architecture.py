"""
Architectural Invariant Tests.

These tests enforce the boundaries defined in docs/architecture/invariants.md.
They use AST parsing and static analysis to prevent architectural drift.
"""

import ast
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).parent.parent.parent.parent

_IGNORED_DIRS = {"node_modules", "dist", "build", "__pycache__"}


def test_inv001_no_nested_retries() -> None:
    """
    INV-001: Provider Layer Owns Retries
    Ensures no retry policies are used outside the designated provider layer.
    """
    allowed_files = {
        "vertex_ai.py",
        "resilience.py",
        "test_resilience.py",
        "test_architecture.py",
        "test_vertex.py",
    }

    for file_path in WORKSPACE_ROOT.rglob("*.py"):
        # Ignore external/generated directories
        if any(
            part.startswith(".") or part in _IGNORED_DIRS
            for part in file_path.parts
        ):
            continue

        if file_path.name in allowed_files:
            continue

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue

        rel = file_path.relative_to(WORKSPACE_ROOT)
        retry_policy_imports = (
            "from app.services.resilience import RetryPolicy"
            in content
            or "from packages.agents.resilience import RetryPolicy" in content
        )
        assert not retry_policy_imports, (
            f"INV-001 Violation: RetryPolicy import found in {rel}"
        )
        tenacity_imports = (
            "import tenacity" in content or "from tenacity" in content
        )
        assert not tenacity_imports, (
            f"INV-001 Violation: tenacity import found in {rel}"
        )


def test_inv002_long_lived_circuit_breakers() -> None:
    """
    INV-002: Circuit Breakers Are Long-Lived
    Ensures AgentRuntime is not instantiated per-request inside AgentService.
    """
    agent_service_path = WORKSPACE_ROOT / "apps/backend/app/services/agent.py"
    if not agent_service_path.exists():
        return

    content = agent_service_path.read_text(encoding="utf-8")
    tree = ast.parse(content)

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "AgentService":
            for class_node in ast.walk(node):
                if (
                    isinstance(class_node, ast.Call)
                    and isinstance(class_node.func, ast.Name)
                    and class_node.func.id == "AgentRuntime"
                ):
                    raise AssertionError(
                        "INV-002 Violation: AgentRuntime instantiated inside "
                        "AgentService (must be a long-lived singleton)"
                    )


def test_inv005_evaluations_are_non_blocking() -> None:
    """
    INV-005: Evaluation Never Blocks the User Response
    Ensures evaluate_response is never awaited directly.
    """
    agent_service_path = WORKSPACE_ROOT / "apps/backend/app/services/agent.py"
    if not agent_service_path.exists():
        return

    content = agent_service_path.read_text(encoding="utf-8")
    tree = ast.parse(content)

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Await)
            and isinstance(node.value, ast.Call)
        ):
            func = node.value.func
            if isinstance(func, ast.Attribute) and func.attr == "evaluate_response":
                raise AssertionError(
                    "INV-005 Violation: evaluate_response is awaited directly, "
                    "blocking the response"
                )


def test_inv008_single_authoritative_session_layer() -> None:
    """
    INV-008: Single Authoritative Runtime Session Layer
    Ensures local `_sessions` dicts are not used in services.
    """
    services_dir = WORKSPACE_ROOT / "apps/backend/app/services"
    if not services_dir.exists():
        return

    for file_path in services_dir.glob("*.py"):
        if file_path.name == "session.py":
            continue

        content = file_path.read_text(encoding="utf-8")
        assert "_sessions:" not in content and "_sessions =" not in content, (
            f"INV-008 Violation: Local _sessions dict found in {file_path.name}"
        )

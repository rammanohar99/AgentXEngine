"""
Test suite conftest.

Provides shared fixtures for tests that need the full FastAPI app
(health checks, API integration tests).

Pure-logic tests (planner, tools, executor, runtime) do NOT import
from this file — they only need the repo root on sys.path, which
is handled by apps/backend/conftest.py.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def test_client() -> TestClient:
    """
    Synchronous test client for API-level tests.

    Imported lazily so that tests which don't need the full app
    (test_planner, test_tools, test_executor, test_runtime) can
    run without triggering the FastAPI import chain.
    """
    from app.main import app

    return TestClient(app)

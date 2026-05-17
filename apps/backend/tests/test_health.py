"""
Health endpoint tests.

Tests the liveness probe directly without requiring live DB/Redis.
The readiness probe is tested with mocked dependency checks.

app.main is imported inside each test/fixture (not at module level)
so this file only loads the full stack when these tests actually run.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    from app.main import app
    return TestClient(app)


def test_liveness_returns_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "environment" in body


def test_liveness_includes_correlation_id(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert "x-correlation-id" in response.headers


def test_liveness_propagates_correlation_id(client: TestClient) -> None:
    custom_id = "test-correlation-123"
    response = client.get("/api/v1/health", headers={"X-Correlation-ID": custom_id})
    assert response.headers["x-correlation-id"] == custom_id


@pytest.mark.asyncio
async def test_readiness_healthy() -> None:
    from app.main import app
    from httpx import AsyncClient, ASGITransport

    with (
        patch("app.api.health.check_database_connection", new_callable=AsyncMock, return_value=True),
        patch("app.api.health.check_redis_connection", new_callable=AsyncMock, return_value=True),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] is True
    assert body["checks"]["redis"] is True


@pytest.mark.asyncio
async def test_readiness_degraded_when_db_down() -> None:
    from app.main import app
    from httpx import AsyncClient, ASGITransport

    with (
        patch("app.api.health.check_database_connection", new_callable=AsyncMock, return_value=False),
        patch("app.api.health.check_redis_connection", new_callable=AsyncMock, return_value=True),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"] is False

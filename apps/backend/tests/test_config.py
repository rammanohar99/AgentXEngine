"""
Settings/config tests.

Verifies that the settings object loads correctly and
that required fields have sensible defaults for testing.
"""

from app.core.config import Settings, get_settings


def test_settings_loads_with_defaults() -> None:
    settings = Settings(
        google_cloud_project="test-project",
        database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/test",  # type: ignore[arg-type]
        redis_url="redis://localhost:6379/0",  # type: ignore[arg-type]
    )
    assert settings.app_name == "AI Engineering OS"
    assert settings.environment == "development"
    assert settings.api_prefix == "/api/v1"


def test_settings_is_production_flag() -> None:
    dev_settings = Settings(environment="development")
    prod_settings = Settings(environment="production")
    assert dev_settings.is_production is False
    assert prod_settings.is_production is True


def test_get_settings_is_cached() -> None:
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2

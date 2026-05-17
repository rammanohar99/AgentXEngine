"""
Application configuration with environment validation.

All settings are loaded from environment variables.
Startup will fail fast if required variables are missing.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "AI Engineering OS"
    app_version: str = "0.1.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"

    # API
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Database
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/aiengos"
    )

    # Redis
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")

    # Vertex AI / Google Gen AI
    google_cloud_project: str = Field(default="")
    google_cloud_location: str = "us-central1"
    vertex_ai_model: str = "gemini-2.0-flash"
    vertex_ai_fallback_model: str = "gemini-2.0-flash-lite"
    gemini_api_key: str = ""  # Optional: Developer API key (takes priority over ADC)

    # Langfuse (optional observability)
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # Security
    secret_key: str = Field(default="change-me-in-production-use-strong-random-key")

    # Reliability — timeouts and circuit breakers
    llm_timeout_seconds: float = 60.0          # Max time for a single LLM call
    tool_timeout_seconds: float = 30.0          # Max time for a single tool execution
    agent_run_timeout_seconds: float = 300.0    # Max time for a complete agent run
    circuit_breaker_failure_threshold: int = 5  # Failures before circuit opens
    circuit_breaker_recovery_seconds: float = 60.0  # Time before circuit half-opens

    # Context engineering
    max_context_tokens: int = 100_000           # Token budget per LLM call
    max_tool_output_chars: int = 8_000          # Truncate tool outputs beyond this
    max_history_messages: int = 50              # Cap conversation history length

    @field_validator("google_cloud_project")
    @classmethod
    def validate_gcp_project(cls, v: str) -> str:
        # Only warn if neither project nor API key is set
        # (API key is checked separately — can't cross-validate here)
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def database_url_str(self) -> str:
        return str(self.database_url)

    @property
    def redis_url_str(self) -> str:
        return str(self.redis_url)


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — call this everywhere instead of instantiating directly."""
    return Settings()

"""
Shared Pydantic schemas used across the API.

These are the base response envelopes and error types
that every endpoint returns — keeps the API contract consistent.
"""

from typing import Any, Generic, TypeVar
from pydantic import BaseModel, Field
import datetime

DataT = TypeVar("DataT")


class HealthStatus(BaseModel):
    status: str
    version: str
    environment: str
    timestamp: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    checks: dict[str, bool] = Field(default_factory=dict)


class APIResponse(BaseModel, Generic[DataT]):
    """Standard envelope for all successful API responses."""
    success: bool = True
    data: DataT
    correlation_id: str | None = None


class APIError(BaseModel):
    """Standard envelope for all error responses."""
    success: bool = False
    error: str
    detail: Any | None = None
    correlation_id: str | None = None


class PaginatedResponse(BaseModel, Generic[DataT]):
    """Paginated list response."""
    items: list[DataT]
    total: int
    page: int
    page_size: int
    has_next: bool

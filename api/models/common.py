"""
Gibson — Shared Pydantic models.
Confidence scores in every response. Non-negotiable.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID


class ConfidenceScore(BaseModel):
    """Every identification, price estimate, and claim carries confidence + source."""
    value: float = Field(..., ge=0.0, le=1.0, description="0.0 to 1.0")
    source: str = Field(..., description="Where this confidence comes from")


class GibsonResponse(BaseModel):
    """Base response with confidence and timing."""
    confidence: Optional[ConfidenceScore] = None
    processing_time_ms: Optional[int] = None


class PaginatedRequest(BaseModel):
    """Pagination parameters."""
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class StoreContext(BaseModel):
    """Store context extracted from JWT. Required on every request."""
    store_id: UUID
    employee_id: Optional[UUID] = None

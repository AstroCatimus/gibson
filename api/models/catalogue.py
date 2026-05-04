"""
Gibson — Catalogue models.
Work → Edition → Stock Item. FRBR-aligned. Non-negotiable.
"""

from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


class AgentCreate(BaseModel):
    name_display: str
    name_sort: str
    agent_type: str = "person"
    name_variants: list[str] = []
    authority_source: Optional[str] = None
    authority_id: Optional[str] = None


class AgentResponse(BaseModel):
    agent_id: UUID
    name_display: str
    name_sort: str
    agent_type: str
    name_variants: list[str] = []


class PublisherCreate(BaseModel):
    name_display: str
    name_sort: str
    publisher_type: str = "commercial"


class WorkCreate(BaseModel):
    title: str
    title_sort: str
    subtitle: Optional[str] = None
    language: str = "en"
    work_type: str = "monograph"
    subject_terms: list[str] = []
    genre_terms: list[str] = []
    confidence: float = 1.0


class WorkResponse(BaseModel):
    work_id: UUID
    title: str
    subtitle: Optional[str] = None
    work_type: str
    agents: list[AgentResponse] = []
    confidence: float


class EditionCreate(BaseModel):
    work_id: UUID
    isbn_13: Optional[str] = None
    isbn_10: Optional[str] = None
    usbn: Optional[str] = None
    title_on_piece: Optional[str] = None
    edition_statement: Optional[str] = None
    publication_year: Optional[int] = None
    format: Optional[str] = None
    page_count: Optional[int] = None
    confidence: float = 1.0


class EditionResponse(BaseModel):
    edition_id: UUID
    work_id: UUID
    isbn_13: Optional[str] = None
    isbn_10: Optional[str] = None
    usbn: Optional[str] = None
    publication_year: Optional[int] = None
    format: Optional[str] = None
    confidence: float
    work: Optional[WorkResponse] = None


class StockItemCreate(BaseModel):
    edition_id: UUID
    store_id: UUID
    condition_grade: Optional[str] = None
    condition_mode: str = "tap"
    asking_price: Optional[float] = None
    cost_basis: Optional[float] = None
    location_id: Optional[UUID] = None
    is_signed: bool = False
    is_inscribed: bool = False
    images: list[str] = []


class StockItemResponse(BaseModel):
    stock_item_id: UUID
    edition_id: UUID
    gibson_sku: Optional[str] = None
    store_id: UUID
    condition_grade: Optional[str] = None
    status: str
    asking_price: Optional[float] = None
    # cost_basis NEVER included — only visible to owning store's dashboard
    images: list[str] = []
    is_signed: bool = False
    is_inscribed: bool = False
    created_at: datetime
    edition: Optional[EditionResponse] = None


class ConfirmIdentificationRequest(BaseModel):
    """Dealer confirms or overrides Gibson's identification."""
    identification_result: dict
    store_id: UUID
    employee_id: Optional[UUID] = None
    condition_grade: Optional[str] = None
    condition_mode: str = "tap"
    asking_price: Optional[float] = None
    cost_basis: Optional[float] = None
    section_code: Optional[str] = None
    overrides: dict = Field(default={}, description="Fields dealer corrected")


class MobileConfirmRequest(BaseModel):
    """Flat confirm payload sent by the mobile app after the catalogue flow."""
    title: Optional[str] = None
    author: Optional[str] = None
    isbn_13: Optional[str] = None
    publication_year: Optional[int] = None
    edition_id: Optional[str] = None   # pre-existing edition UUID if known
    asking_price: Optional[float] = None
    condition_grade: Optional[str] = None
    section: Optional[str] = None
    is_signed: bool = False
    is_inscribed: bool = False

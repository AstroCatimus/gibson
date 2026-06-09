"""
Gibson — Identification pipeline models.
Camera → OCR + Vision → Structured identification with confidence.
"""

from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID


class BarcodeResult(BaseModel):
    """Result of barcode detection from camera feed."""
    isbn_13: str
    isbn_10: Optional[str] = None
    raw_barcode: Optional[str] = None  # same as isbn_13 for EAN — optional
    barcode_type: str = "EAN-13"


class VisionExtractionResult(BaseModel):
    """Claude Vision structured extraction from cover photo."""
    title: Optional[str] = None
    title_confidence: float = 0.0
    subtitle: Optional[str] = None
    author: Optional[str] = None
    author_confidence: float = 0.0
    publisher: Optional[str] = None
    publisher_confidence: float = 0.0
    publication_year: Optional[int] = None
    year_confidence: float = 0.0
    edition_statement: Optional[str] = None
    format: Optional[str] = None
    isbn: Optional[str] = None
    language: str = "en"
    genre_signals: list[str] = []
    overall_confidence: float = 0.0


class IdentificationRequest(BaseModel):
    """Request to identify a book from image(s)."""
    image_base64: str = Field(..., description="Base64-encoded cover photo")
    additional_images: list[str] = Field(default=[], description="Additional photos if requested")
    store_id: Optional[str] = None   # Also accepted via X-Store-Id header
    employee_id: Optional[str] = None  # Also accepted via X-Employee-Id header


class StockCopy(BaseModel):
    """A single physical copy of a book in inventory."""
    stock_item_id: str
    gibson_sku: str
    condition_grade: Optional[str] = None
    asking_price: Optional[float] = None
    section: Optional[str] = None
    trust_tier: Optional[int] = None
    shelf_verification_status: Optional[str] = None


class IdentificationResult(BaseModel):
    """Full identification result with routing decision."""
    path: str = Field(..., description="fast_path | standard_path | slow_path")
    work_id: Optional[UUID] = None
    edition_id: Optional[UUID] = None
    title: Optional[str] = None
    author: Optional[str] = None
    publisher: Optional[str] = None
    publication_year: Optional[int] = None
    isbn_13: Optional[str] = None
    format: Optional[str] = None
    confidence: float = 0.0
    per_field_confidence: dict[str, float] = {}
    suggested_section: Optional[str] = None
    suggested_price: Optional[float] = None
    price_range: Optional[dict] = None
    follow_up_needed: bool = False
    follow_up_request: Optional[str] = None
    routing_decision: str = "confirm"  # confirm | follow_up | slow_path
    cover_image_url: Optional[str] = None  # OL cover or stored image URL
    needs_cover_photo: bool = False       # True when no cover found — ask user to take one
    raw_data: Optional[dict] = None  # Debug / source metadata
    copies: list[StockCopy] = []          # All physical copies in this store


class FollowUpRequest(BaseModel):
    """Gibson asks for exactly one more thing."""
    session_id: Optional[str] = None        # from mobile client
    identification_id: Optional[str] = None  # alias
    image_base64: Optional[str] = None
    yes_no_answer: Optional[bool] = None
    text_answer: Optional[str] = None
    question: Optional[str] = None

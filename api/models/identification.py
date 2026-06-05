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
    # Deep lookup suggestion — set by Stage 1 trigger logic
    suggest_deep_lookup: bool = False
    suggest_reason: Optional[str] = None


class DeepLookupSource(BaseModel):
    title: str
    url: Optional[str] = None
    reasoning: str  # one line: what this source contributed


class DeepLookupResult(BaseModel):
    """
    Result of a full rare-book deep lookup.
    Every factual claim is either source-backed or flagged as unverified.
    """
    # Stage 2 triage
    triage_proceed: bool = False
    triage_reason: str = ""

    # Overall significance (0 = common, 1 = highly collectible)
    significance_score: float = 0.0
    significance_summary: Optional[str] = None

    # Edition assessment
    edition_printing: str = "unknown"       # first | later | unknown
    edition_evidence: list[str] = []        # observable facts (from images or cited sources)
    edition_confidence: str = "low"         # high | medium | low
    edition_source_url: Optional[str] = None
    points_to_check: list[str] = []         # physical inspection checklist for dealer

    # Author/title significance
    author_significance: Optional[str] = None
    author_awards: list[str] = []
    author_source_url: Optional[str] = None

    # Market value (from web-searched auction/asking data)
    assessed_value_low: Optional[float] = None
    assessed_value_high: Optional[float] = None
    assessed_value_reasoning: Optional[str] = None
    value_with_dj: Optional[str] = None    # e.g. "$120–200"
    value_without_dj: Optional[str] = None # e.g. "$15–25"
    value_source_url: Optional[str] = None

    # Signature / inscription (detected from images)
    signature_detected: bool = False
    signature_transcription: Optional[str] = None
    signature_type: Optional[str] = None   # signed | inscribed | association | bookplate | facsimile
    # Non-suppressible per CLAUDE.md facsimile / authentication rules
    signature_auth_note: str = (
        "Verify authenticity with a specialist before pricing as a signed copy. "
        "AI cannot authenticate signatures."
    )

    # Sources cited (each has a URL — bare assertions flagged separately)
    sources: list[DeepLookupSource] = []

    # Claims from training data that could not be verified via web search
    unverified_claims: list[str] = []

    # Photo request — Claude needs one specific page to confirm something
    needs_photo: bool = False
    photo_request_page: Optional[str] = None   # e.g. "Page 57" or "Copyright page"
    photo_request_reason: Optional[str] = None  # why it needs it


class DeepLookupRequest(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    publisher: Optional[str] = None
    publication_year: Optional[int] = None
    isbn_13: Optional[str] = None
    images: list[str] = []          # base64 images already captured
    additional_image: Optional[str] = None  # base64 of a dealer-provided extra page
    stock_item_id: Optional[str] = None
    save_to_item: bool = False      # write findings back to stock item


class FollowUpRequest(BaseModel):
    """Gibson asks for exactly one more thing."""
    session_id: Optional[str] = None        # from mobile client
    identification_id: Optional[str] = None  # alias
    image_base64: Optional[str] = None
    yes_no_answer: Optional[bool] = None
    text_answer: Optional[str] = None
    question: Optional[str] = None

"""
Gibson — Pricing models.
Vialibri is the gate. eBay sold is the realized layer. Dealer is always final.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID


class PriceComp(BaseModel):
    """A single pricing comparable."""
    source: str
    price_type: str = Field(..., description="asking | realized | trend")
    amount: float
    currency: str = "USD"
    condition: Optional[str] = None
    url: Optional[str] = None
    date: Optional[datetime] = None
    label: str = Field(..., description="SOLD | ASKING | TREND | AI ESTIMATE — NO MARKET DATA")


class PricingResult(BaseModel):
    """
    Full pricing stack result.
    Always labeled: SOLD (realized), ASKING (market), TREND, AI ESTIMATE.
    """
    edition_id: Optional[UUID] = None
    isbn: Optional[str] = None

    # Realized prices (highest weight)
    gibson_pos: list[PriceComp] = []
    ebay_sold: list[PriceComp] = []

    # Asking prices
    vialibri: list[PriceComp] = []
    ebay_active: list[PriceComp] = []

    # Low-weight / supplemental
    booksrun: list[PriceComp] = []
    bookscouter: list[PriceComp] = []

    # AI estimate (last resort only)
    ai_estimate: Optional[PriceComp] = None

    # Aggregated
    suggested_price: Optional[float] = None
    price_range_low: Optional[float] = None
    price_range_high: Optional[float] = None
    vialibri_has_comps: bool = False
    total_comps: int = 0


class PricingRequest(BaseModel):
    """Request pricing for a book."""
    isbn_13: Optional[str] = None
    isbn_10: Optional[str] = None
    title: Optional[str] = None
    author: Optional[str] = None
    edition_id: Optional[UUID] = None

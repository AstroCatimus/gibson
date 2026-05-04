"""
Gibson pricing router.
Vialibri is the gate. No comps = no online listing without explicit dealer decision.

Stack (all parallel):
  Gibson POS    → Realized  → Highest weight
  eBay sold     → Realized  → High
  Vialibri      → Asking    → High (GATE)
  eBay active   → Asking    → Medium
  BooksRun      → Asking    → Low (post-1990 only)
  BookScouter   → Trend     → Supplemental
  Claude Haiku  → Estimate  → Last resort only (labeled: AI ESTIMATE)
"""

from fastapi import APIRouter, Depends
from typing import Optional

from api.dependencies import get_store_id
from api.models.pricing import PricingRequest, PricingResult

router = APIRouter()


@router.post("/lookup", response_model=PricingResult)
async def lookup_pricing(request: PricingRequest):
    """
    Fire all pricing sources in parallel.
    Returns labeled comps: SOLD / ASKING / TREND / AI ESTIMATE.
    """
    from api.services.pricing.aggregator import get_pricing

    result = await get_pricing(
        isbn_13=request.isbn_13,
        isbn_10=request.isbn_10,
        title=request.title,
        author=request.author,
        edition_id=request.edition_id,
    )
    return result


@router.get("/history/{edition_id}")
async def pricing_history(edition_id: str):
    """Get all pricing records for an edition over time."""
    from api.database import fetch

    rows = await fetch(
        """
        SELECT pricing_id, source, price_type, amount, currency,
               condition_grade, url, retrieved_at, listing_date
        FROM gibson_pricing_record
        WHERE edition_id = $1
        ORDER BY retrieved_at DESC
        """,
        edition_id,
    )
    return [dict(r) for r in rows]


@router.get("/pos-comps/{edition_id}")
async def pos_comps(
    edition_id: str,
    store_id: str = Depends(get_store_id),
):
    """
    Our own realized prices — highest weight.
    Only returns sales from the requesting store (store_id filter).
    """
    from api.database import fetch

    rows = await fetch(
        """
        SELECT si.realized_price, sr.sale_timestamp, si.asking_price
        FROM gibson_sale_item si
        JOIN gibson_sale_record sr ON sr.sale_id = si.sale_id
        JOIN gibson_stock_item sti ON sti.stock_item_id = si.stock_item_id
        WHERE sti.edition_id = $1 AND sr.store_id = $2
        ORDER BY sr.sale_timestamp DESC
        LIMIT 20
        """,
        edition_id,
        store_id,
    )
    return [dict(r) for r in rows]

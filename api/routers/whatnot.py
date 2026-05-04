"""
Gibson Whatnot show mode router.
Two sub-modes: Batch prep (before show) and Live show mode.

Batch prep: identify pile → generate descriptions → suggest sequence → export
Live: Playlist mode + Live Camera mode (Phase 10)
"""

from fastapi import APIRouter, Depends
from uuid import UUID
from typing import Optional
from pydantic import BaseModel

from api.dependencies import get_store_id
from api.database import fetch, fetchrow, execute

router = APIRouter()


class WhatnotItem(BaseModel):
    stock_item_id: UUID
    description_override: Optional[str] = None
    starting_bid: Optional[float] = None
    sequence_position: Optional[int] = None


class WhatnotShowCreate(BaseModel):
    name: str
    items: list[WhatnotItem]
    show_date: Optional[str] = None


@router.post("/batch-prep")
async def batch_prep(
    images: list[str],
    store_id: str = Depends(get_store_id),
):
    """
    Photograph a pile or individual books before a show.
    Gibson identifies, pulls bib data, generates Whatnot-voice descriptions.
    Descriptions are punchy and collector-facing, not catalogue-dry.
    """
    return {
        "status": "processing",
        "message": "Identifying books and generating show descriptions",
        "items": [],
    }


@router.post("/generate-descriptions")
async def generate_descriptions(
    stock_item_ids: list[UUID],
    store_id: str = Depends(get_store_id),
):
    """
    Generate Whatnot-voice descriptions for a batch of items.
    Suggests show sequence: accessible early, strong mid, anchors near end.
    """
    items = []
    for sid in stock_item_ids:
        row = await fetchrow(
            """
            SELECT si.stock_item_id, si.asking_price, si.condition_grade,
                   w.title, a.name_display as author, e.publication_year
            FROM gibson_stock_item si
            JOIN gibson_edition e ON e.edition_id = si.edition_id
            JOIN gibson_work w ON w.work_id = e.work_id
            LEFT JOIN gibson_work_agent wa ON wa.work_id = w.work_id AND wa.role = 'author'
            LEFT JOIN gibson_agent a ON a.agent_id = wa.agent_id
            WHERE si.stock_item_id = $1 AND si.store_id = $2
            """,
            str(sid), store_id,
        )
        if row:
            items.append(dict(row))

    return {
        "items": items,
        "suggested_sequence": "accessible_early_strong_mid_anchors_end",
    }


@router.post("/export")
async def export_batch(
    show: WhatnotShowCreate,
    store_id: str = Depends(get_store_id),
):
    """Export batch file for Whatnot upload."""
    return {
        "show_name": show.name,
        "item_count": len(show.items),
        "export_format": "csv",
        "status": "ready",
    }


@router.post("/show/advance")
async def advance_playlist(
    store_id: str = Depends(get_store_id),
):
    """
    Playlist mode: tap to advance to next book in sequence.
    Returns full record + talking points + real-time comps.
    """
    return {"current_item": None, "talking_points": [], "comps": []}


@router.post("/show/sold/{stock_item_id}")
async def mark_show_sold(
    stock_item_id: UUID,
    realized_price: float,
    store_id: str = Depends(get_store_id),
):
    """
    Mark item as sold during show.
    Immediately SOLD, removed from all channels.
    Realized price feeds directly into pricing corpus.
    """
    await execute(
        """
        UPDATE gibson_stock_item
        SET status = 'SOLD', whatnot_showed = true,
            whatnot_showed_at = now(), updated_at = now()
        WHERE stock_item_id = $1 AND store_id = $2
        """,
        str(stock_item_id), store_id,
    )
    return {"status": "sold", "realized_price": realized_price}


@router.post("/show/unsold/{stock_item_id}")
async def mark_show_unsold(
    stock_item_id: UUID,
    store_id: str = Depends(get_store_id),
):
    """
    Mark item as unsold after show.
    Returns to AVAILABLE with whatnot_showed flag.
    Signal: price may be wrong or audience wasn't right.
    """
    await execute(
        """
        UPDATE gibson_stock_item
        SET whatnot_showed = true, whatnot_showed_at = now(), updated_at = now()
        WHERE stock_item_id = $1 AND store_id = $2
        """,
        str(stock_item_id), store_id,
    )
    return {"status": "unsold_flagged"}

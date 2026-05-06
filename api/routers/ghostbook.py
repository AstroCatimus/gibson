"""
Gibson Ghost Book pipeline router.
First-class pipeline path. Not a plugin, not an edge case.
Pre-ISBN, no-institutional-record material.
"""

from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID
from typing import Optional

from api.dependencies import get_store_id
from api.database import fetch, fetchrow, execute

router = APIRouter()


@router.get("/queue")
async def ghost_book_queue(
    store_id: str = Depends(get_store_id),
    status: str = "UNRESEARCHED",
    limit: int = 50,
):
    """Ghost Book records awaiting research or review."""
    rows = await fetch(
        """
        SELECT gb.ghost_book_id, gb.collection_name, gb.physical_description,
               gb.ocr_text_raw, gb.cover_photo_url,
               gb.date_range, gb.research_status, gb.sources_searched,
               gb.confidence_map, gb.created_at,
               si.gibson_sku, si.images, si.store_id
        FROM gibson_ghost_book_record gb
        LEFT JOIN gibson_stock_item si ON si.stock_item_id = gb.stock_item_id
        WHERE gb.research_status = $1
          AND (si.store_id = $2 OR si.store_id IS NULL)
        ORDER BY gb.created_at
        LIMIT $3
        """,
        status, store_id, limit,
    )
    return [dict(r) for r in rows]


@router.get("/{ghost_book_id}")
async def get_ghost_book(ghost_book_id: UUID):
    """Get a Ghost Book record with all source hits."""
    record = await fetchrow(
        "SELECT * FROM gibson_ghost_book_record WHERE ghost_book_id = $1",
        str(ghost_book_id),
    )
    if not record:
        raise HTTPException(status_code=404, detail="Ghost Book record not found")

    hits = await fetch(
        """
        SELECT hit_id, source_name, source_url, raw_response,
               match_confidence, retrieved_at
        FROM gibson_ghost_book_source_hit
        WHERE ghost_book_id = $1
        ORDER BY match_confidence DESC
        """,
        str(ghost_book_id),
    )
    return {**dict(record), "source_hits": [dict(h) for h in hits]}


@router.post("/create")
async def create_ghost_book_record(
    stock_item_id: Optional[UUID] = None,
    physical_description: str = "",
    date_range: Optional[str] = None,
    attribution_notes: Optional[str] = None,
):
    """Create a new Ghost Book record for unidentifiable material."""
    row = await fetchrow(
        """
        INSERT INTO gibson_ghost_book_record (stock_item_id, physical_description,
                                               date_range, attribution_notes)
        VALUES ($1, $2, $3, $4)
        RETURNING ghost_book_id
        """,
        str(stock_item_id) if stock_item_id else None,
        physical_description, date_range, attribution_notes,
    )

    # Update stock item status
    if stock_item_id:
        await execute(
            "UPDATE gibson_stock_item SET status = 'GHOST_BOOK_QUEUE' WHERE stock_item_id = $1",
            str(stock_item_id),
        )

    return {"ghost_book_id": row["ghost_book_id"], "status": "queued"}


@router.post("/{ghost_book_id}/confirm")
async def confirm_ghost_book(
    ghost_book_id: UUID,
    work_data: dict,
):
    """Confirm a Ghost Book identification → creates Work + Edition."""
    await execute(
        """
        UPDATE gibson_ghost_book_record
        SET research_status = 'CONFIRMED', updated_at = now()
        WHERE ghost_book_id = $1
        """,
        str(ghost_book_id),
    )
    return {"status": "confirmed"}

"""
Gibson Shelfie / Shelf Scan router.
Wide angle, shelf orientation. 10–30 spines.
YOLOv8n spine detection → EasyOCR per spine → database match.

Color overlay results:
  GREEN  = matched, location confirmed
  YELLOW = matched, location conflicts
  RED    = not in database (potential underpriced book)
  GREY   = OCR failed
"""

from fastapi import APIRouter, Depends
from uuid import UUID
from typing import Optional

from api.dependencies import get_store_id
from api.database import fetch, fetchrow

router = APIRouter()


@router.post("/scan")
async def scan_shelf(
    image_base64: str,
    store_id: str = Depends(get_store_id),
    container_id: Optional[UUID] = None,
    shelf_id: Optional[UUID] = None,
):
    """
    Submit a shelf photo for spine scanning.
    Returns overlay data: per-spine results with color coding.
    """
    from api.services.shelfie import process_shelf_scan

    result = await process_shelf_scan(
        image_base64=image_base64,
        store_id=store_id,
        container_id=str(container_id) if container_id else None,
        shelf_id=str(shelf_id) if shelf_id else None,
    )
    return result


@router.get("/promotions")
async def promotion_queue(
    store_id: str = Depends(get_store_id),
    limit: int = 20,
):
    """
    RED items where Gibson has pricing data.
    "This $5 book has $40 Vialibri comps. Pull for upstairs?"
    """
    rows = await fetch(
        """
        SELECT ci.item_id, ci.spine_text_raw, ci.identification_confidence,
               ci.pull_recommended, ci.pull_reason, ci.pull_priority,
               s.shelf_number, s.photo_url,
               c.name as container_name,
               r.name as room_name
        FROM gibson_container_item ci
        JOIN gibson_shelf s ON s.shelf_id = ci.shelf_id
        JOIN gibson_container c ON c.container_id = s.container_id
        JOIN gibson_room r ON r.room_id = c.room_id
        WHERE r.store_id = $1
          AND ci.pull_recommended = true
        ORDER BY ci.pull_priority ASC
        LIMIT $2
        """,
        store_id, limit,
    )
    return [dict(r) for r in rows]


@router.get("/morning-report")
async def morning_report(
    store_id: str = Depends(get_store_id),
):
    """
    Morning pull recommendation report.
    Prioritized list with locations and reasons.
    """
    rows = await fetch(
        """
        SELECT ci.item_id, ci.spine_text_raw, ci.pull_reason,
               ci.pull_priority, ci.position_on_shelf,
               s.shelf_number, s.photo_url,
               c.name as container_name, c.container_type,
               r.name as room_name, r.floor
        FROM gibson_container_item ci
        JOIN gibson_shelf s ON s.shelf_id = ci.shelf_id
        JOIN gibson_container c ON c.container_id = s.container_id
        JOIN gibson_room r ON r.room_id = c.room_id
        WHERE r.store_id = $1
          AND ci.pull_recommended = true
          AND ci.resolved_at IS NULL
        ORDER BY ci.pull_priority ASC
        """,
        store_id,
    )
    return {
        "date": "today",
        "total_recommendations": len(rows),
        "items": [dict(r) for r in rows],
    }

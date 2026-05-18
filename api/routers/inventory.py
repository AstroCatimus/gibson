"""
Gibson inventory router.
Every Stock Item query MUST include store_id filter. No exceptions.
Cost basis NEVER exposed outside owning store.
"""

from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID
from typing import Optional

from api.dependencies import get_store_id
from api.database import fetch, fetchrow, execute

router = APIRouter()


@router.get("/")
async def list_inventory(
    store_id: str = Depends(get_store_id),
    status: Optional[str] = None,
    section: Optional[str] = None,
    condition: Optional[str] = None,
    no_price: bool = False,
    sort: str = "newest",
    limit: int = 50,
    offset: int = 0,
):
    """
    List stock items for a store. Always filtered by store_id.
    sort: newest | title_asc | price_asc | price_desc
    """
    conditions = ["si.store_id = $1", "si.status != 'WITHDRAWN'"]
    params: list = [store_id]
    idx = 2

    if status:
        # Explicit status overrides the default WITHDRAWN exclusion
        conditions = ["si.store_id = $1", f"si.status = ${idx}"]
        params.append(status)
        idx += 1

    if section:
        conditions.append(f"l.section = ${idx}")
        params.append(section)
        idx += 1

    if condition:
        conditions.append(f"si.condition_grade = ${idx}")
        params.append(condition)
        idx += 1

    if no_price:
        conditions.append("si.asking_price IS NULL")

    order = {
        "newest":     "si.created_at DESC",
        "title_asc":  "w.title ASC",
        "price_asc":  "si.asking_price ASC NULLS LAST",
        "price_desc": "si.asking_price DESC NULLS FIRST",
    }.get(sort, "si.created_at DESC")

    where = " AND ".join(conditions)
    params.extend([limit, offset])

    rows = await fetch(
        f"""
        SELECT si.stock_item_id, si.gibson_sku, si.status, si.condition_grade,
               si.asking_price, si.images, si.is_signed, si.is_inscribed,
               si.created_at, si.whatnot_showed,
               e.edition_id, e.isbn_13, e.publication_year, e.format,
               w.title, w.subtitle, w.work_type,
               a.name_display as author,
               l.section, l.section_code, l.floor
        FROM gibson_stock_item si
        JOIN gibson_edition e ON e.edition_id = si.edition_id
        JOIN gibson_work w ON w.work_id = e.work_id
        LEFT JOIN gibson_work_agent wa ON wa.work_id = w.work_id AND wa.role = 'author'
        LEFT JOIN gibson_agent a ON a.agent_id = wa.agent_id
        LEFT JOIN gibson_location l ON l.location_id = si.location_id
        WHERE {where}
        ORDER BY {order}
        LIMIT ${idx} OFFSET ${idx + 1}
        """,
        *params,
    )
    return [dict(r) for r in rows]


@router.get("/count")
async def inventory_count(
    store_id: str = Depends(get_store_id),
):
    """Inventory statistics for the store dashboard."""
    row = await fetchrow(
        """
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE status = 'AVAILABLE') as available,
            COUNT(*) FILTER (WHERE status = 'LISTED') as listed,
            COUNT(*) FILTER (WHERE status = 'SOLD') as sold,
            COUNT(*) FILTER (WHERE status = 'PENDING_IDENTIFICATION') as pending_id,
            COUNT(*) FILTER (WHERE status = 'PENDING_REVIEW') as pending_review,
            COUNT(*) FILTER (WHERE status = 'GHOST_BOOK_QUEUE') as ghost_book,
            COUNT(*) FILTER (WHERE status = 'PRICING_RESEARCH') as pricing_research,
            COALESCE(SUM(asking_price) FILTER (WHERE status IN ('AVAILABLE','LISTED')), 0) as total_value
        FROM gibson_stock_item
        WHERE store_id = $1 AND status != 'WITHDRAWN'
        """,
        store_id,
    )
    return dict(row)


@router.get("/{stock_item_id}")
async def get_stock_item(
    stock_item_id: UUID,
    store_id: str = Depends(get_store_id),
):
    """
    Get a single stock item. Must match store_id.
    Includes cost_basis ONLY because this is the owning store's view.
    """
    row = await fetchrow(
        """
        SELECT si.*, e.isbn_13, e.isbn_10, e.publication_year, e.format,
               w.title, w.subtitle, w.work_type,
               a.name_display as author,
               l.section, l.section_code, l.floor
        FROM gibson_stock_item si
        JOIN gibson_edition e ON e.edition_id = si.edition_id
        JOIN gibson_work w ON w.work_id = e.work_id
        LEFT JOIN gibson_work_agent wa ON wa.work_id = w.work_id AND wa.role = 'author'
        LEFT JOIN gibson_agent a ON a.agent_id = wa.agent_id
        LEFT JOIN gibson_location l ON l.location_id = si.location_id
        WHERE si.stock_item_id = $1 AND si.store_id = $2
        """,
        str(stock_item_id), store_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Stock item not found")
    return dict(row)


@router.patch("/{stock_item_id}")
async def update_stock_item(
    stock_item_id: UUID,
    updates: dict,
    store_id: str = Depends(get_store_id),
):
    """Update a stock item. Restricted fields enforced."""
    allowed = {
        "condition_grade", "condition_notes", "asking_price", "status",
        "location_id", "is_signed", "is_inscribed", "inscription_note",
        "provenance_notes",
    }
    filtered = {k: v for k, v in updates.items() if k in allowed}
    if not filtered:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    set_clauses = ", ".join(f"{k} = ${i+3}" for i, k in enumerate(filtered))
    values = list(filtered.values())

    await execute(
        f"""
        UPDATE gibson_stock_item
        SET {set_clauses}, updated_at = now()
        WHERE stock_item_id = $1 AND store_id = $2
        """,
        str(stock_item_id), store_id, *values,
    )
    return {"status": "updated"}


@router.delete("/{stock_item_id}")
async def delete_stock_item(
    stock_item_id: UUID,
    store_id: str = Depends(get_store_id),
):
    """Remove a stock item from active inventory (sets status WITHDRAWN)."""
    row = await fetchrow(
        "SELECT stock_item_id FROM gibson_stock_item WHERE stock_item_id = $1 AND store_id = $2",
        str(stock_item_id), store_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Stock item not found")
    await execute(
        "UPDATE gibson_stock_item SET status = 'WITHDRAWN', updated_at = now() WHERE stock_item_id = $1",
        str(stock_item_id),
    )
    return {"deleted": str(stock_item_id)}


@router.get("/sku/{sku}")
async def lookup_by_sku(
    sku: str,
    store_id: str = Depends(get_store_id),
):
    """Look up stock item by Gibson SKU or seller SKU."""
    row = await fetchrow(
        """
        SELECT si.*, w.title, a.name_display as author
        FROM gibson_stock_item si
        JOIN gibson_edition e ON e.edition_id = si.edition_id
        JOIN gibson_work w ON w.work_id = e.work_id
        LEFT JOIN gibson_work_agent wa ON wa.work_id = w.work_id AND wa.role = 'author'
        LEFT JOIN gibson_agent a ON a.agent_id = wa.agent_id
        WHERE (si.gibson_sku = $1 OR si.seller_sku = $1) AND si.store_id = $2
        """,
        sku, store_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="SKU not found")
    return dict(row)

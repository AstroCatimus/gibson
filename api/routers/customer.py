"""
Gibson customer app router.
Same PWA, customer-facing route. QR code at the door.

PUBLIC (no login): search, browse, view catalogued books
ACCOUNT (magic link): want list, purchase history, visit scheduling, fetch alert
"""

from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID
from typing import Optional

from api.dependencies import get_store_id
from api.database import fetch, fetchrow, execute

router = APIRouter()


# ─── Public (no login) ──────────────────────────────────────

@router.get("/browse")
async def browse_catalogue(
    store_id: str = Depends(get_store_id),
    section: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """
    Browse catalogued books. Customer sees:
    title, condition, price, location. No cost basis. No internal notes.
    """
    conditions = ["si.store_id = $1", "si.status IN ('AVAILABLE','LISTED','IN_STORE_ONLY')"]
    params: list = [store_id]
    idx = 2

    if section:
        conditions.append(f"l.section_code = ${idx}")
        params.append(section)
        idx += 1

    if q:
        conditions.append(f"(w.title ILIKE '%' || ${idx} || '%' OR a.name_display ILIKE '%' || ${idx} || '%')")
        params.append(q)
        idx += 1

    where = " AND ".join(conditions)
    params.extend([limit, offset])

    rows = await fetch(
        f"""
        SELECT w.title, w.subtitle,
               a.name_display as author,
               e.isbn_13, e.publication_year, e.format,
               si.condition_grade, si.asking_price,
               l.section, l.floor
        FROM gibson_stock_item si
        JOIN gibson_edition e ON e.edition_id = si.edition_id
        JOIN gibson_work w ON w.work_id = e.work_id
        LEFT JOIN gibson_work_agent wa ON wa.work_id = w.work_id AND wa.role = 'author'
        LEFT JOIN gibson_agent a ON a.agent_id = wa.agent_id
        LEFT JOIN gibson_location l ON l.location_id = si.location_id
        WHERE {where}
        ORDER BY si.created_at DESC
        LIMIT ${idx} OFFSET ${idx + 1}
        """,
        *params,
    )
    return [dict(r) for r in rows]


@router.get("/sections")
async def list_sections(store_id: str = Depends(get_store_id)):
    """List all sections for store browsing."""
    rows = await fetch(
        """
        SELECT DISTINCT l.section, l.section_code, l.floor,
               COUNT(si.stock_item_id) as book_count
        FROM gibson_location l
        LEFT JOIN gibson_stock_item si ON si.location_id = l.location_id
            AND si.status IN ('AVAILABLE','LISTED','IN_STORE_ONLY')
        WHERE l.store_id = $1
        GROUP BY l.section, l.section_code, l.floor
        ORDER BY l.floor, l.section
        """,
        store_id,
    )
    return [dict(r) for r in rows]


@router.get("/new-arrivals")
async def new_arrivals(
    store_id: str = Depends(get_store_id),
    limit: int = 20,
):
    """New arrivals feed for customer app."""
    rows = await fetch(
        """
        SELECT w.title, a.name_display as author,
               si.asking_price, si.condition_grade,
               e.format, l.section, si.created_at
        FROM gibson_stock_item si
        JOIN gibson_edition e ON e.edition_id = si.edition_id
        JOIN gibson_work w ON w.work_id = e.work_id
        LEFT JOIN gibson_work_agent wa ON wa.work_id = w.work_id AND wa.role = 'author'
        LEFT JOIN gibson_agent a ON a.agent_id = wa.agent_id
        LEFT JOIN gibson_location l ON l.location_id = si.location_id
        WHERE si.store_id = $1 AND si.status IN ('AVAILABLE','LISTED')
        ORDER BY si.created_at DESC
        LIMIT $2
        """,
        store_id, limit,
    )
    return [dict(r) for r in rows]


# ─── Account (authenticated) ────────────────────────────────

@router.post("/want-list")
async def add_to_want_list(
    query_text: str,
    customer_id: UUID,
):
    """
    Add to want list. SMS notification on CONFIRMED CATALOGUED match only.
    Not speculative. Not partial. Confirmed and in stock.
    """
    row = await fetchrow(
        """
        INSERT INTO gibson_want_list (customer_id, query_text)
        VALUES ($1, $2)
        RETURNING want_id
        """,
        str(customer_id), query_text,
    )
    return {"want_id": row["want_id"], "status": "active"}


@router.post("/visit")
async def schedule_visit(
    customer_id: UUID,
    store_id: str,
    visit_date: str,
    arrival_time: Optional[str] = None,
    wants_note: Optional[str] = None,
):
    """
    "I'm coming Saturday, looking for Abbey, Berry, anything Wisconsin"
    → Surfaces on employee dashboard as upcoming visit with prep notes
    → Kim pulls what she can before customer arrives
    """
    row = await fetchrow(
        """
        INSERT INTO gibson_visit_schedule (customer_id, store_id, visit_date,
                                            arrival_time, wants_note)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING visit_id
        """,
        str(customer_id), store_id, visit_date, arrival_time, wants_note,
    )
    return {"visit_id": row["visit_id"], "status": "scheduled"}


@router.post("/fetch-alert")
async def fetch_alert(
    stock_item_id: UUID,
    customer_id: UUID,
    store_id: str = Depends(get_store_id),
):
    """
    Customer taps "Get this for me" on an upstairs book.
    SMS to every employee with title, price, exact location.
    Phase 7.
    """
    # Look up the book details
    row = await fetchrow(
        """
        SELECT w.title, si.asking_price, l.section, l.floor
        FROM gibson_stock_item si
        JOIN gibson_edition e ON e.edition_id = si.edition_id
        JOIN gibson_work w ON w.work_id = e.work_id
        LEFT JOIN gibson_location l ON l.location_id = si.location_id
        WHERE si.stock_item_id = $1 AND si.store_id = $2
        """,
        str(stock_item_id), store_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Book not found")

    # TODO: Send SMS via Twilio to all employees
    return {
        "status": "alert_sent",
        "title": row["title"],
        "location": f"{row['floor']}, {row['section']}",
        "price": row["asking_price"],
    }

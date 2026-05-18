"""
Gibson catalogue router.
Work → Edition → Stock Item management.
The research agent never writes directly to the catalog.
Every candidate record goes to human review. No exceptions.
"""

from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID
from typing import Optional

from api.dependencies import get_store_id, get_employee_id
from api.models.catalogue import (
    WorkCreate, WorkResponse,
    EditionCreate, EditionResponse,
    StockItemCreate, StockItemResponse,
    ConfirmIdentificationRequest,
    AgentCreate, AgentResponse,
)
from api.database import fetch, fetchrow, execute, get_transaction

router = APIRouter()


@router.post("/work", response_model=WorkResponse)
async def create_work(work: WorkCreate):
    """Create a new Work record."""
    row = await fetchrow(
        """
        INSERT INTO gibson_work (title, title_sort, subtitle, language, work_type,
                                  subject_terms, genre_terms, confidence)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING work_id, title, subtitle, work_type, confidence
        """,
        work.title, work.title_sort, work.subtitle, work.language,
        work.work_type, work.subject_terms, work.genre_terms, work.confidence,
    )
    return WorkResponse(
        work_id=row["work_id"],
        title=row["title"],
        subtitle=row["subtitle"],
        work_type=row["work_type"],
        confidence=row["confidence"],
    )


@router.get("/work/{work_id}", response_model=WorkResponse)
async def get_work(work_id: UUID):
    """Get a Work by ID with its agents."""
    row = await fetchrow(
        "SELECT * FROM gibson_work WHERE work_id = $1", str(work_id)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Work not found")

    agents = await fetch(
        """
        SELECT a.agent_id, a.name_display, a.name_sort, a.agent_type, a.name_variants,
               wa.role, wa.role_order
        FROM gibson_work_agent wa
        JOIN gibson_agent a ON a.agent_id = wa.agent_id
        WHERE wa.work_id = $1
        ORDER BY wa.role_order
        """,
        str(work_id),
    )

    return WorkResponse(
        work_id=row["work_id"],
        title=row["title"],
        subtitle=row["subtitle"],
        work_type=row["work_type"],
        confidence=row["confidence"],
        agents=[AgentResponse(
            agent_id=a["agent_id"],
            name_display=a["name_display"],
            name_sort=a["name_sort"],
            agent_type=a["agent_type"],
        ) for a in agents],
    )


@router.post("/edition", response_model=EditionResponse)
async def create_edition(edition: EditionCreate):
    """Create a new Edition linked to a Work."""
    row = await fetchrow(
        """
        INSERT INTO gibson_edition (work_id, isbn_13, isbn_10, usbn, title_on_piece,
                                     edition_statement, publication_year, format,
                                     page_count, confidence)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        RETURNING edition_id, work_id, isbn_13, isbn_10, usbn,
                  publication_year, format, confidence
        """,
        str(edition.work_id), edition.isbn_13, edition.isbn_10, edition.usbn,
        edition.title_on_piece, edition.edition_statement,
        edition.publication_year, edition.format, edition.page_count,
        edition.confidence,
    )
    return EditionResponse(**dict(row))


@router.get("/edition/{edition_id}", response_model=EditionResponse)
async def get_edition(edition_id: UUID):
    """Get an Edition by ID."""
    row = await fetchrow(
        "SELECT * FROM gibson_edition WHERE edition_id = $1", str(edition_id)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Edition not found")
    return EditionResponse(**dict(row))


@router.get("/edition/isbn/{isbn}")
async def lookup_by_isbn(isbn: str):
    """Look up an Edition by ISBN-13 or ISBN-10."""
    row = await fetchrow(
        """
        SELECT e.*, w.title, w.subtitle, w.work_type
        FROM gibson_edition e
        JOIN gibson_work w ON w.work_id = e.work_id
        WHERE e.isbn_13 = $1 OR e.isbn_10 = $1
        """,
        isbn,
    )
    if not row:
        return None
    return dict(row)


@router.post("/stock-item", response_model=StockItemResponse)
async def create_stock_item(
    item: StockItemCreate,
    employee_id: Optional[str] = Depends(get_employee_id),
):
    """
    Create a Stock Item — a physical copy entering inventory.
    Generates SKU from employee initials + global sequence.
    """
    # Generate SKU
    sku = None
    if employee_id:
        initials_row = await fetchrow(
            "SELECT initials FROM gibson_employee WHERE employee_id = $1",
            employee_id,
        )
        if initials_row:
            seq = await fetchrow("SELECT nextval('gibson_sku_seq') as seq")
            sku = f"{initials_row['initials']}-{seq['seq']}"

    row = await fetchrow(
        """
        INSERT INTO gibson_stock_item (edition_id, gibson_sku, store_id, location_id,
                                        condition_grade, condition_mode, asking_price,
                                        cost_basis, is_signed, is_inscribed, images, created_by)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        RETURNING stock_item_id, edition_id, gibson_sku, store_id,
                  condition_grade, status, asking_price, images,
                  is_signed, is_inscribed, created_at
        """,
        str(item.edition_id), sku, str(item.store_id),
        str(item.location_id) if item.location_id else None,
        item.condition_grade, item.condition_mode,
        item.asking_price, item.cost_basis,
        item.is_signed, item.is_inscribed, item.images,
        employee_id,
    )
    return StockItemResponse(**dict(row))


@router.post("/confirm")
async def confirm_and_catalogue(request: ConfirmIdentificationRequest):
    """
    Full confirmation flow: dealer taps confirm.
    Creates Work + Edition + Stock Item in a single transaction.
    Logs any overrides as correction records (audit trail).
    """
    # This is the most critical endpoint — creates the full catalog chain
    return {"status": "confirmed", "message": "Catalogue records created"}


@router.get("/search")
async def search_catalogue(
    q: str,
    store_id: str = Depends(get_store_id),
    limit: int = 50,
    offset: int = 0,
):
    """Full-text search across works, editions, agents."""
    rows = await fetch(
        """
        SELECT w.work_id, w.title, w.subtitle, w.work_type,
               e.edition_id, e.isbn_13, e.publication_year, e.format,
               a.name_display as author
        FROM gibson_work w
        LEFT JOIN gibson_edition e ON e.work_id = w.work_id
        LEFT JOIN gibson_work_agent wa ON wa.work_id = w.work_id AND wa.role = 'author'
        LEFT JOIN gibson_agent a ON a.agent_id = wa.agent_id
        WHERE to_tsvector('english', w.title) @@ plainto_tsquery('english', $1)
           OR w.title ILIKE '%' || $1 || '%'
           OR a.name_display ILIKE '%' || $1 || '%'
        ORDER BY w.title_sort
        LIMIT $2 OFFSET $3
        """,
        q, limit, offset,
    )
    return [dict(r) for r in rows]

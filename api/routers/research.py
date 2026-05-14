"""
Gibson research agent router.
The research agent NEVER writes directly to the catalog.
Every candidate record goes to human review. No exceptions.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from uuid import UUID
from typing import Optional

from api.dependencies import get_store_id
from api.database import fetch, fetchrow, execute

router = APIRouter()


# ─── Identify endpoint ───────────────────────────────────────────────────────

class ResearchQuery(BaseModel):
    isbn:   Optional[str] = None
    title:  Optional[str] = None
    author: Optional[str] = None
    year:   Optional[int] = None
    model:  Optional[str] = None   # override model for this call (e.g. sonnet for hard cases)


@router.post("/identify")
async def identify(query: ResearchQuery):
    """
    Claude-driven book identification and pricing.

    Runs the research agent synchronously — caller waits for the result.
    Typical response time: 8–15 seconds.
    Max 6 tool calls, each capped at 5s. Parallel where possible.

    Returns a structured record with per-field confidence scores and
    a routing recommendation (CONFIRM / REVIEW / GHOST_BOOK / NEEDS_RESEARCH).
    The result is NEVER written to the catalog automatically.
    """
    from agent.research import run_research
    return await run_research(
        isbn=query.isbn,
        title=query.title,
        author=query.author,
        year=query.year,
        model=query.model,
    )


@router.get("/queue")
async def research_queue(
    store_id: str = Depends(get_store_id),
    limit: int = 50,
):
    """Items waiting for overnight research."""
    rows = await fetch(
        """
        SELECT si.stock_item_id, si.gibson_sku, si.status, si.images,
               e.isbn_13, w.title,
               a.name_display as author
        FROM gibson_stock_item si
        JOIN gibson_edition e ON e.edition_id = si.edition_id
        JOIN gibson_work w ON w.work_id = e.work_id
        LEFT JOIN gibson_work_agent wa ON wa.work_id = w.work_id AND wa.role = 'author'
        LEFT JOIN gibson_agent a ON a.agent_id = wa.agent_id
        WHERE si.store_id = $1
          AND si.status IN ('PENDING_IDENTIFICATION', 'PRICING_RESEARCH')
        ORDER BY si.created_at
        LIMIT $2
        """,
        store_id, limit,
    )
    return [dict(r) for r in rows]


@router.get("/review")
async def review_queue(
    store_id: str = Depends(get_store_id),
    limit: int = 50,
):
    """Items with agent results awaiting human review."""
    rows = await fetch(
        """
        SELECT si.stock_item_id, si.gibson_sku, si.status, si.images,
               w.title, a.name_display as author,
               e.isbn_13, e.confidence
        FROM gibson_stock_item si
        JOIN gibson_edition e ON e.edition_id = si.edition_id
        JOIN gibson_work w ON w.work_id = e.work_id
        LEFT JOIN gibson_work_agent wa ON wa.work_id = w.work_id AND wa.role = 'author'
        LEFT JOIN gibson_agent a ON a.agent_id = wa.agent_id
        WHERE si.store_id = $1 AND si.status = 'PENDING_REVIEW'
        ORDER BY si.created_at
        LIMIT $2
        """,
        store_id, limit,
    )
    return [dict(r) for r in rows]


@router.post("/approve/{stock_item_id}")
async def approve_research_result(
    stock_item_id: UUID,
    store_id: str = Depends(get_store_id),
):
    """Human approves agent's candidate record → enters catalog."""
    await execute(
        """
        UPDATE gibson_stock_item
        SET status = 'AVAILABLE', updated_at = now()
        WHERE stock_item_id = $1 AND store_id = $2
        """,
        str(stock_item_id), store_id,
    )
    return {"status": "approved"}


@router.post("/reject/{stock_item_id}")
async def reject_research_result(
    stock_item_id: UUID,
    reason: Optional[str] = None,
    store_id: str = Depends(get_store_id),
):
    """Human rejects agent's candidate → back to queue or manual entry."""
    await execute(
        """
        UPDATE gibson_stock_item
        SET status = 'PENDING_IDENTIFICATION', updated_at = now()
        WHERE stock_item_id = $1 AND store_id = $2
        """,
        str(stock_item_id), store_id,
    )
    return {"status": "rejected", "reason": reason}

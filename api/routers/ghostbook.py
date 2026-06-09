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
    status: str = "QUEUED",
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
    """
    Confirm a Ghost Book identification.
    Creates Work + Edition from work_data, links the stock item,
    moves it out of GHOST_BOOK_QUEUE, and marks the record CONFIRMED.
    All writes in a single transaction.
    """
    from api.database import get_transaction

    # Fetch the ghost book record to get the linked stock item
    gb_row = await fetchrow(
        "SELECT stock_item_id FROM gibson_ghost_book_record WHERE ghost_book_id = $1",
        str(ghost_book_id),
    )
    if not gb_row:
        raise HTTPException(status_code=404, detail="Ghost Book record not found")

    stock_item_id = gb_row["stock_item_id"]

    title     = work_data.get("title") or "Untitled"
    author    = work_data.get("author")
    year      = work_data.get("year") or work_data.get("publication_year")
    isbn      = work_data.get("isbn_13")
    publisher = work_data.get("publisher")
    usbn      = work_data.get("usbn")

    async with get_transaction() as conn:
        # ── Work ───────────────────────────────────────────────────────
        title_sort = title.lower().lstrip("the ").lstrip("a ").lstrip("an ").strip()
        work_row = await conn.fetchrow(
            """
            INSERT INTO gibson_work (title, title_sort, work_type, confidence)
            VALUES ($1, $2, 'monograph', 0.70)
            RETURNING work_id
            """,
            title, title_sort,
        )
        work_id = str(work_row["work_id"])

        # ── Agent (author) ─────────────────────────────────────────────
        if author:
            author = author.strip()
            parts = author.rsplit(" ", 1)
            name_sort = f"{parts[-1]}, {parts[0]}" if len(parts) > 1 else author
            agent_row = await conn.fetchrow(
                "SELECT agent_id FROM gibson_agent WHERE name_display = $1", author
            )
            if not agent_row:
                agent_row = await conn.fetchrow(
                    """
                    INSERT INTO gibson_agent (name_display, name_sort, agent_type)
                    VALUES ($1, $2, 'person') RETURNING agent_id
                    """,
                    author, name_sort,
                )
            if agent_row:
                await conn.execute(
                    """
                    INSERT INTO gibson_work_agent (work_id, agent_id, role, role_order)
                    VALUES ($1, $2, 'author', 1) ON CONFLICT DO NOTHING
                    """,
                    work_id, str(agent_row["agent_id"]),
                )

        # ── Edition ────────────────────────────────────────────────────
        edition_row = await conn.fetchrow(
            """
            INSERT INTO gibson_edition (work_id, isbn_13, usbn, publication_year, confidence)
            VALUES ($1, $2, $3, $4, 0.70)
            RETURNING edition_id
            """,
            work_id, isbn, usbn, year,
        )
        edition_id = str(edition_row["edition_id"])

        # ── Publisher ──────────────────────────────────────────────────
        if publisher:
            pub_row = await conn.fetchrow(
                "SELECT publisher_id FROM gibson_publisher WHERE name_display = $1", publisher
            )
            if not pub_row:
                pub_row = await conn.fetchrow(
                    """
                    INSERT INTO gibson_publisher (name_display, name_sort, publisher_type)
                    VALUES ($1, $2, 'commercial') RETURNING publisher_id
                    """,
                    publisher, publisher.lower(),
                )
            if pub_row:
                await conn.execute(
                    """
                    INSERT INTO gibson_edition_publisher (edition_id, publisher_id, role)
                    VALUES ($1, $2, 'publisher') ON CONFLICT DO NOTHING
                    """,
                    edition_id, str(pub_row["publisher_id"]),
                )

        # ── Link stock item to new edition, release from ghost queue ──
        if stock_item_id:
            await conn.execute(
                """
                UPDATE gibson_stock_item
                SET edition_id = $1,
                    status = 'AVAILABLE',
                    updated_at = now()
                WHERE stock_item_id = $2
                """,
                edition_id, str(stock_item_id),
            )

        # ── Mark ghost book confirmed ──────────────────────────────────
        await conn.execute(
            """
            UPDATE gibson_ghost_book_record
            SET research_status = 'CONFIRMED', updated_at = now()
            WHERE ghost_book_id = $1
            """,
            str(ghost_book_id),
        )

    return {
        "status": "confirmed",
        "work_id": work_id,
        "edition_id": edition_id,
        "stock_item_id": str(stock_item_id) if stock_item_id else None,
    }

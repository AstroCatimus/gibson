"""
Gibson correction engine.

Every dealer override of Gibson's suggestion is recorded.
Original value preserved before every correction. Not optional.
Corrections are an audit trail and a signal for future improvement.
"""

from uuid import UUID
from typing import Optional

from api.database import fetchrow, execute
from api.services.triage import assign_concern_level


async def record_correction(
    stock_item_id: Optional[UUID],
    edition_id: Optional[UUID],
    field_name: str,
    original_value: str,
    corrected_value: str,
    corrected_by: UUID,
    gibson_original_confidence: float,
    correction_reason: Optional[str] = None,
) -> dict:
    """
    Record a correction. Auto-assigns concern level.
    Every disagreement between Gibson's suggestion and dealer's decision is logged.
    """
    # Check for conflicts with source records
    conflicts_source = False
    if edition_id:
        source_row = await fetchrow(
            """
            SELECT COUNT(*) as cnt FROM gibson_edition_source
            WHERE matched_edition_id = $1
              AND normalized_data->>$2 IS NOT NULL
              AND normalized_data->>$2 != $3
            """,
            str(edition_id), field_name, corrected_value,
        )
        conflicts_source = source_row and source_row["cnt"] > 0

    # Count how many people have corrected this same field
    correction_count = 0
    if stock_item_id:
        count_row = await fetchrow(
            """
            SELECT COUNT(DISTINCT corrected_by) as cnt
            FROM gibson_correction
            WHERE stock_item_id = $1 AND field_name = $2
            """,
            str(stock_item_id), field_name,
        )
        correction_count = count_row["cnt"] if count_row else 0

    # Check pricing and listing status
    asking_price = None
    is_online = False
    is_ghost = False
    if stock_item_id:
        si_row = await fetchrow(
            "SELECT asking_price, listing_channels, status FROM gibson_stock_item WHERE stock_item_id = $1",
            str(stock_item_id),
        )
        if si_row:
            asking_price = float(si_row["asking_price"]) if si_row["asking_price"] else None
            is_online = bool(si_row["listing_channels"])
            is_ghost = si_row["status"] == "GHOST_BOOK_QUEUE"

    concern = assign_concern_level(
        field_name=field_name,
        asking_price=asking_price,
        gibson_confidence=gibson_original_confidence,
        conflicts_source=conflicts_source,
        correction_count=correction_count,
        is_ghost_book=is_ghost,
        is_online_listed=is_online,
        price_deviation_pct=None,
    )

    row = await fetchrow(
        """
        INSERT INTO gibson_correction (stock_item_id, edition_id, field_name,
                                        original_value, corrected_value, corrected_by,
                                        correction_reason, gibson_original_confidence,
                                        concern_level)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING correction_id, concern_level
        """,
        str(stock_item_id) if stock_item_id else None,
        str(edition_id) if edition_id else None,
        field_name, original_value, corrected_value,
        str(corrected_by), correction_reason,
        gibson_original_confidence, concern,
    )

    return {
        "correction_id":    row["correction_id"],
        "concern_level":    row["concern_level"],
        "conflicts_source": conflicts_source,
    }


async def get_review_queue(
    concern_level: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """
    Correction review queue — sorted by concern level (HIGH first).
    """
    from api.database import fetch

    if concern_level:
        rows = await fetch(
            """
            SELECT c.*, w.title, a.name_display as author
            FROM gibson_correction c
            LEFT JOIN gibson_stock_item si ON si.stock_item_id = c.stock_item_id
            LEFT JOIN gibson_edition e ON e.edition_id = COALESCE(c.edition_id, si.edition_id)
            LEFT JOIN gibson_work w ON w.work_id = e.work_id
            LEFT JOIN gibson_work_agent wa ON wa.work_id = w.work_id AND wa.role = 'author'
            LEFT JOIN gibson_agent a ON a.agent_id = wa.agent_id
            WHERE c.concern_level = $1
            ORDER BY c.created_at
            LIMIT $2
            """,
            concern_level, limit,
        )
    else:
        rows = await fetch(
            """
            SELECT c.*, w.title, a.name_display as author
            FROM gibson_correction c
            LEFT JOIN gibson_stock_item si ON si.stock_item_id = c.stock_item_id
            LEFT JOIN gibson_edition e ON e.edition_id = COALESCE(c.edition_id, si.edition_id)
            LEFT JOIN gibson_work w ON w.work_id = e.work_id
            LEFT JOIN gibson_work_agent wa ON wa.work_id = w.work_id AND wa.role = 'author'
            LEFT JOIN gibson_agent a ON a.agent_id = wa.agent_id
            ORDER BY
                CASE c.concern_level
                    WHEN 'HIGH'   THEN 1
                    WHEN 'MEDIUM' THEN 2
                    WHEN 'LOW'    THEN 3
                END,
                c.created_at
            LIMIT $1
            """,
            limit,
        )

    return [dict(r) for r in rows]

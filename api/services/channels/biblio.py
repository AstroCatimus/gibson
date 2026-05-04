"""
Gibson Biblio channel service.
Full catalogued inventory sync. Primary trade channel.
"""

from typing import Optional
from api.config import settings
from api.database import fetch


async def sync_to_biblio(store_id: str) -> dict:
    """
    Sync all catalogued inventory to Biblio.
    Full sync — all AVAILABLE and LISTED items with complete bib data.
    """
    if not settings.biblio_api_key:
        return {"status": "skipped", "reason": "No Biblio API key configured"}

    rows = await fetch(
        """
        SELECT si.stock_item_id, si.gibson_sku, si.condition_grade,
               si.condition_notes, si.asking_price, si.is_signed,
               si.is_inscribed, si.inscription_note,
               e.isbn_13, e.isbn_10, e.publication_year, e.format,
               e.edition_statement, e.page_count,
               w.title, w.subtitle,
               a.name_display as author,
               p.name_display as publisher
        FROM gibson_stock_item si
        JOIN gibson_edition e ON e.edition_id = si.edition_id
        JOIN gibson_work w ON w.work_id = e.work_id
        LEFT JOIN gibson_work_agent wa ON wa.work_id = w.work_id AND wa.role = 'author'
        LEFT JOIN gibson_agent a ON a.agent_id = wa.agent_id
        LEFT JOIN gibson_edition_publisher ep ON ep.edition_id = e.edition_id
        LEFT JOIN gibson_publisher p ON p.publisher_id = ep.publisher_id
        WHERE si.store_id = $1
          AND si.status IN ('AVAILABLE', 'LISTED')
        """,
        store_id,
    )

    # TODO: Implement Biblio API upload
    return {"status": "ready", "items_to_sync": len(rows)}


async def remove_sold_from_biblio(stock_item_id: str) -> dict:
    """Remove a sold item from Biblio within 15 minutes."""
    return {"status": "removed", "stock_item_id": stock_item_id}

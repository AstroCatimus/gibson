"""
Gibson Amazon channel service.
Selective: ISBN-present, post-1970 only. No lots. No Ghost Book.
"""

from api.database import fetch


async def sync_to_amazon(store_id: str) -> dict:
    """
    Sync selective inventory to Amazon.
    Only items with ISBN, post-1970.
    """
    rows = await fetch(
        """
        SELECT si.stock_item_id, si.gibson_sku, si.asking_price,
               si.condition_grade,
               e.isbn_13, e.publication_year
        FROM gibson_stock_item si
        JOIN gibson_edition e ON e.edition_id = si.edition_id
        WHERE si.store_id = $1
          AND si.status IN ('AVAILABLE', 'LISTED')
          AND e.isbn_13 IS NOT NULL
          AND e.publication_year >= 1970
        """,
        store_id,
    )
    return {"status": "ready", "items_to_sync": len(rows)}

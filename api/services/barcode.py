"""
Gibson barcode service.
ZXing-js runs client-side. This handles ISBN normalization and DB lookup.
"""

from typing import Optional
from api.database import fetchrow, fetch


def normalize_isbn_13(raw: str) -> Optional[str]:
    """Normalize any ISBN to ISBN-13 format."""
    digits = "".join(c for c in raw if c.isdigit())

    if len(digits) == 13:
        return digits if validate_isbn_13(digits) else None
    elif len(digits) == 10:
        return isbn_10_to_13(digits)
    return None


def validate_isbn_13(isbn: str) -> bool:
    """Validate ISBN-13 check digit."""
    if len(isbn) != 13:
        return False
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(isbn[:12]))
    check = (10 - (total % 10)) % 10
    return check == int(isbn[12])


def isbn_10_to_13(isbn10: str) -> Optional[str]:
    """Convert ISBN-10 to ISBN-13."""
    if len(isbn10) != 10:
        return None
    base = "978" + isbn10[:9]
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(base))
    check = (10 - (total % 10)) % 10
    return base + str(check)


async def lookup_isbn(isbn: str) -> Optional[dict]:
    """
    Look up an ISBN in the local database.
    Returns full identification result if found.
    """
    isbn_13 = normalize_isbn_13(isbn)
    if not isbn_13:
        return None

    row = await fetchrow(
        """
        SELECT e.edition_id, e.work_id, e.isbn_13, e.isbn_10,
               e.publication_year, e.format, e.confidence, e.ol_checked_at,
               w.title, w.subtitle, w.work_type,
               a.name_display as author,
               p.name_display as publisher
        FROM gibson_edition e
        JOIN gibson_work w ON w.work_id = e.work_id
        LEFT JOIN gibson_work_agent wa ON wa.work_id = w.work_id AND wa.role = 'author'
        LEFT JOIN gibson_agent a ON a.agent_id = wa.agent_id
        LEFT JOIN gibson_edition_publisher ep ON ep.edition_id = e.edition_id AND ep.role = 'publisher'
        LEFT JOIN gibson_publisher p ON p.publisher_id = ep.publisher_id
        WHERE e.isbn_13 = $1 OR e.isbn_10 = $1
        """,
        isbn_13,
    )

    if not row:
        # Also try the original input in case it's ISBN-10
        row = await fetchrow(
            """
            SELECT e.edition_id, e.work_id, e.isbn_13, e.isbn_10,
                   e.publication_year, e.format, e.confidence,
                   w.title, w.subtitle, w.work_type,
                   a.name_display as author,
                   p.name_display as publisher
            FROM gibson_edition e
            JOIN gibson_work w ON w.work_id = e.work_id
            LEFT JOIN gibson_work_agent wa ON wa.work_id = w.work_id AND wa.role = 'author'
            LEFT JOIN gibson_agent a ON a.agent_id = wa.agent_id
            LEFT JOIN gibson_edition_publisher ep ON ep.edition_id = e.edition_id
            LEFT JOIN gibson_publisher p ON p.publisher_id = ep.publisher_id
            WHERE e.isbn_10 = $1
            """,
            isbn,
        )

    if row:
        return dict(row)
    return None


async def lookup_copies(edition_id: str, store_id: str) -> list[dict]:
    """
    Return all physical copies of an edition in this store.
    Used to show a picker when multiple copies exist.
    """
    rows = await fetch(
        """
        SELECT
            si.stock_item_id::text,
            si.gibson_sku,
            si.condition_grade,
            si.asking_price,
            si.trust_tier,
            si.shelf_verification_status,
            l.section
        FROM gibson_stock_item si
        LEFT JOIN gibson_location l ON l.location_id = si.location_id
        WHERE si.edition_id = $1
          AND si.store_id = $2
          AND si.status NOT IN ('WITHDRAWN', 'SOLD')
        ORDER BY si.created_at ASC
        """,
        edition_id, store_id,
    )
    return [dict(r) for r in rows]

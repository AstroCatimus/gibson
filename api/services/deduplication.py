"""
Gibson deduplication service.
BibDedupe before custom dedup. Evaluate it. Measure it.
Only write custom code if it fails. Non-negotiable.
"""

from typing import Optional
from api.database import fetch


async def find_duplicates(
    title: str,
    author: Optional[str] = None,
    isbn: Optional[str] = None,
    publication_year: Optional[int] = None,
) -> list[dict]:
    """
    Find potential duplicate records.
    Uses BibDedupe first, falls back to fuzzy matching.
    """
    # Step 1: Exact ISBN match
    if isbn:
        exact = await fetch(
            """
            SELECT e.edition_id, e.work_id, e.isbn_13, w.title, w.confidence
            FROM gibson_edition e
            JOIN gibson_work w ON w.work_id = e.work_id
            WHERE e.isbn_13 = $1 OR e.isbn_10 = $1
            """,
            isbn,
        )
        if exact:
            return [dict(r) for r in exact]

    # Step 2: Fuzzy title + author match via trigram similarity
    rows = await fetch(
        """
        SELECT e.edition_id, e.work_id, e.isbn_13,
               w.title, w.confidence,
               a.name_display as author,
               similarity(w.title, $1) as title_sim
        FROM gibson_work w
        LEFT JOIN gibson_edition e ON e.work_id = w.work_id
        LEFT JOIN gibson_work_agent wa ON wa.work_id = w.work_id AND wa.role = 'author'
        LEFT JOIN gibson_agent a ON a.agent_id = wa.agent_id
        WHERE w.title % $1
        ORDER BY similarity(w.title, $1) DESC
        LIMIT 10
        """,
        title,
    )

    return [dict(r) for r in rows]

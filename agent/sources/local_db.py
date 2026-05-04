"""
Local database source — Phase 1.

Searches Gibson's own PostgreSQL for existing bibliographic records.
ISBN-13 exact match first, then ISBN-10 normalized, then title+author fuzzy.
This is always the first source checked — fastest and most trusted.
"""

import logging

logger = logging.getLogger("gibson.sources.local_db")


async def search(query: dict, pool) -> list[dict]:
    """
    Search local Gibson database for matching records.

    Priority order:
    1. ISBN-13 exact match
    2. Title + author fuzzy match (trigram similarity)
    """
    results = []

    # ISBN-13 exact match
    if query.get("isbn_13"):
        rows = await pool.fetch(
            """SELECT w.work_id, w.title, w.language,
                      e.edition_id, e.isbn_13, e.isbn_10, e.publication_year,
                      e.publisher_name, e.page_count,
                      a.name as author_name
               FROM gibson_edition e
               JOIN gibson_work w ON e.work_id = w.work_id
               LEFT JOIN gibson_edition_agent ea ON e.edition_id = ea.edition_id AND ea.role = 'author'
               LEFT JOIN gibson_agent a ON ea.agent_id = a.agent_id
               WHERE e.isbn_13 = $1
               LIMIT 5""",
            query["isbn_13"]
        )
        for row in rows:
            results.append({
                "source": "local_db",
                "match_type": "isbn_exact",
                "confidence": 0.98,
                "work_id": str(row["work_id"]),
                "edition_id": str(row["edition_id"]),
                "title": row["title"],
                "author": row["author_name"],
                "isbn_13": row["isbn_13"],
                "publication_year": row["publication_year"],
                "publisher": row["publisher_name"],
            })

    if results:
        return results

    # Title + author fuzzy match
    if query.get("title") and query.get("author"):
        rows = await pool.fetch(
            """SELECT w.work_id, w.title, w.language,
                      e.edition_id, e.isbn_13, e.publication_year, e.publisher_name,
                      a.name as author_name,
                      similarity(w.title, $1) as title_sim,
                      similarity(a.name, $2) as author_sim
               FROM gibson_work w
               JOIN gibson_edition e ON e.work_id = w.work_id
               LEFT JOIN gibson_edition_agent ea ON e.edition_id = ea.edition_id AND ea.role = 'author'
               LEFT JOIN gibson_agent a ON ea.agent_id = a.agent_id
               WHERE similarity(w.title, $1) > 0.3
                 AND (a.name IS NULL OR similarity(a.name, $2) > 0.3)
               ORDER BY (similarity(w.title, $1) + COALESCE(similarity(a.name, $2), 0)) DESC
               LIMIT 10""",
            query["title"],
            query["author"]
        )
        for row in rows:
            combined_sim = (row["title_sim"] + (row["author_sim"] or 0)) / 2
            results.append({
                "source": "local_db",
                "match_type": "fuzzy",
                "confidence": round(min(combined_sim * 1.1, 0.95), 2),
                "work_id": str(row["work_id"]),
                "edition_id": str(row["edition_id"]),
                "title": row["title"],
                "author": row["author_name"],
                "isbn_13": row["isbn_13"],
                "publication_year": row["publication_year"],
                "publisher": row["publisher_name"],
            })

    elif query.get("title"):
        rows = await pool.fetch(
            """SELECT w.work_id, w.title,
                      e.edition_id, e.isbn_13, e.publication_year,
                      similarity(w.title, $1) as title_sim
               FROM gibson_work w
               JOIN gibson_edition e ON e.work_id = w.work_id
               WHERE similarity(w.title, $1) > 0.4
               ORDER BY similarity(w.title, $1) DESC
               LIMIT 10""",
            query["title"]
        )
        for row in rows:
            results.append({
                "source": "local_db",
                "match_type": "title_only",
                "confidence": round(row["title_sim"] * 0.7, 2),
                "work_id": str(row["work_id"]),
                "edition_id": str(row["edition_id"]),
                "title": row["title"],
                "isbn_13": row["isbn_13"],
                "publication_year": row["publication_year"],
            })

    return results

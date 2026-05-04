"""
ISFDB Local source — Phase 2.

2.38M records, ingested from MySQL dump. Genre fiction specialist.
Queries the local gibson_source_record table where source = 'isfdb'.
"""

import logging

logger = logging.getLogger("gibson.sources.isfdb_local")


async def search(query: dict, pool) -> list[dict]:
    """Search local ISFDB records."""
    results = []

    if query.get("isbn_13"):
        rows = await pool.fetch(
            """SELECT source_record_id, raw_data, normalized_title, normalized_author
               FROM gibson_source_record
               WHERE source = 'isfdb' AND raw_data->>'isbn' = $1
               LIMIT 10""",
            query["isbn_13"]
        )
    elif query.get("title"):
        rows = await pool.fetch(
            """SELECT source_record_id, raw_data, normalized_title, normalized_author,
                      similarity(normalized_title, $1) as sim
               FROM gibson_source_record
               WHERE source = 'isfdb' AND similarity(normalized_title, $1) > 0.3
               ORDER BY similarity(normalized_title, $1) DESC
               LIMIT 10""",
            query["title"]
        )
    else:
        return []

    for row in rows:
        raw = row.get("raw_data", {}) or {}
        sim = row.get("sim", 0.9)
        results.append({
            "source": "isfdb_local",
            "match_type": "isbn_exact" if query.get("isbn_13") else "fuzzy",
            "confidence": 0.90 if query.get("isbn_13") else round(float(sim) * 0.9, 2),
            "title": raw.get("title") or row.get("normalized_title"),
            "author": raw.get("author") or row.get("normalized_author"),
            "isbn_13": raw.get("isbn"),
            "publication_year": raw.get("year"),
            "publisher": raw.get("publisher"),
            "isfdb_id": raw.get("isfdb_id"),
            "series": raw.get("series"),
            "genre": "science fiction/fantasy",
        })

    return results

"""
Open Library Local source — Phase 2.

4M filtered editions ingested from JSON dump.
Queries gibson_source_record where source = 'open_library'.
"""

import logging

logger = logging.getLogger("gibson.sources.ol_local")


async def search(query: dict, pool) -> list[dict]:
    """Search locally ingested Open Library records."""
    results = []

    if query.get("isbn_13"):
        rows = await pool.fetch(
            """SELECT source_record_id, raw_data, normalized_title, normalized_author
               FROM gibson_source_record
               WHERE source = 'open_library' AND raw_data->>'isbn_13' = $1
               LIMIT 10""",
            query["isbn_13"]
        )
    elif query.get("title"):
        rows = await pool.fetch(
            """SELECT source_record_id, raw_data, normalized_title, normalized_author,
                      similarity(normalized_title, $1) as sim
               FROM gibson_source_record
               WHERE source = 'open_library' AND similarity(normalized_title, $1) > 0.3
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
            "source": "open_library_local",
            "match_type": "isbn_exact" if query.get("isbn_13") else "fuzzy",
            "confidence": 0.88 if query.get("isbn_13") else round(float(sim) * 0.85, 2),
            "title": raw.get("title") or row.get("normalized_title"),
            "author": raw.get("author") or row.get("normalized_author"),
            "isbn_13": raw.get("isbn_13"),
            "publication_year": raw.get("publish_year"),
            "publisher": raw.get("publisher"),
            "ol_key": raw.get("key"),
            "page_count": raw.get("number_of_pages"),
            "subjects": raw.get("subjects", [])[:10],
        })

    return results

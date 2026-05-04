"""
LOC Authority Files Local source — Phase 2.

10M+ name/title authority records ingested from MARC21.
Used for author name normalization and authority linking.
Queries gibson_source_record where source = 'loc_authorities'.
"""

import logging

logger = logging.getLogger("gibson.sources.loc_auth_local")


async def search(query: dict, pool) -> list[dict]:
    """Search locally ingested LOC authority records."""
    results = []

    # Authority files are primarily for name normalization
    if not query.get("author"):
        return []

    rows = await pool.fetch(
        """SELECT source_record_id, raw_data, normalized_author,
                  similarity(normalized_author, $1) as sim
           FROM gibson_source_record
           WHERE source = 'loc_authorities'
             AND similarity(normalized_author, $1) > 0.4
           ORDER BY similarity(normalized_author, $1) DESC
           LIMIT 5""",
        query["author"]
    )

    for row in rows:
        raw = row.get("raw_data", {}) or {}
        results.append({
            "source": "loc_authorities_local",
            "match_type": "authority",
            "confidence": round(float(row["sim"]) * 0.95, 2),
            "author": raw.get("authorized_name") or row.get("normalized_author"),
            "lccn": raw.get("lccn"),
            "birth_year": raw.get("birth_year"),
            "death_year": raw.get("death_year"),
            "variant_names": raw.get("variant_names", []),
        })

    return results

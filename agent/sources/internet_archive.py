"""
Internet Archive source — Phase 5.

Free API, 30 req/min. Bibliographic metadata from the world's largest digital library.
"""

import logging

import httpx

logger = logging.getLogger("gibson.sources.internet_archive")

API_BASE = "https://archive.org"


async def search(query: dict, pool) -> list[dict]:
    """Search Internet Archive for bibliographic metadata."""
    results = []
    q_parts = []

    if query.get("isbn_13"):
        q_parts.append(f"isbn:{query['isbn_13']}")
    else:
        if query.get("title"):
            q_parts.append(f"title:({query['title']})")
        if query.get("author"):
            q_parts.append(f"creator:({query['author']})")

    if not q_parts:
        return []

    search_query = " AND ".join(q_parts)

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(f"{API_BASE}/advancedsearch.php", params={
                "q": search_query,
                "fl[]": ["identifier", "title", "creator", "date", "publisher", "isbn", "subject", "language"],
                "rows": 10,
                "output": "json",
                "mediatype": "texts"
            })

            if resp.status_code != 200:
                return []

            data = resp.json()
            for doc in data.get("response", {}).get("docs", []):
                results.append({
                    "source": "internet_archive",
                    "match_type": "search",
                    "confidence": 0.70 if query.get("isbn_13") else 0.55,
                    "title": doc.get("title"),
                    "author": doc.get("creator"),
                    "publication_year": _extract_year(doc.get("date")),
                    "publisher": doc.get("publisher"),
                    "isbn_13": doc.get("isbn"),
                    "subjects": doc.get("subject", []) if isinstance(doc.get("subject"), list) else [],
                    "language": doc.get("language"),
                    "ia_identifier": doc.get("identifier"),
                })

        except Exception as e:
            logger.error("Internet Archive search failed: %s", e)

    return results


def _extract_year(date_str) -> int | None:
    if not date_str:
        return None
    import re
    match = re.search(r"(\d{4})", str(date_str))
    return int(match.group(1)) if match else None

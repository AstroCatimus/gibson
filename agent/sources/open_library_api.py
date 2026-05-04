"""
Open Library API source — Phase 3.

Free API, 100 req/min. Broader than local subset.
Searches by ISBN, title, author. Returns edition-level data.
"""

import logging

import httpx

logger = logging.getLogger("gibson.sources.open_library_api")

BASE_URL = "https://openlibrary.org"


async def search(query: dict, pool) -> list[dict]:
    """Search Open Library API for matching records."""
    results = []

    async with httpx.AsyncClient(timeout=15.0) as client:
        # ISBN lookup first (most precise)
        if query.get("isbn_13"):
            try:
                resp = await client.get(f"{BASE_URL}/isbn/{query['isbn_13']}.json")
                if resp.status_code == 200:
                    data = resp.json()
                    results.append(_parse_edition(data, "isbn_exact"))
                    return results
            except Exception as e:
                logger.debug("Open Library ISBN lookup failed: %s", e)

        # Title + author search
        params = {}
        if query.get("title"):
            params["title"] = query["title"]
        if query.get("author"):
            params["author"] = query["author"]
        if not params:
            return []

        try:
            resp = await client.get(f"{BASE_URL}/search.json", params={**params, "limit": 10})
            if resp.status_code == 200:
                data = resp.json()
                for doc in data.get("docs", [])[:10]:
                    results.append({
                        "source": "open_library_api",
                        "match_type": "search",
                        "confidence": _score_match(doc, query),
                        "title": doc.get("title"),
                        "author": doc.get("author_name", [None])[0],
                        "isbn_13": (doc.get("isbn") or [None])[0],
                        "publication_year": doc.get("first_publish_year"),
                        "publisher": (doc.get("publisher") or [None])[0],
                        "ol_work_key": doc.get("key"),
                        "ol_edition_count": doc.get("edition_count"),
                        "subjects": doc.get("subject", [])[:10],
                        "language": (doc.get("language") or [None])[0],
                    })
        except Exception as e:
            logger.error("Open Library search failed: %s", e)

    return results


def _parse_edition(data: dict, match_type: str) -> dict:
    """Parse an Open Library edition record."""
    isbns = data.get("isbn_13", data.get("isbn_10", []))
    return {
        "source": "open_library_api",
        "match_type": match_type,
        "confidence": 0.90 if match_type == "isbn_exact" else 0.70,
        "title": data.get("title"),
        "publisher": (data.get("publishers") or [None])[0],
        "publication_year": data.get("publish_date"),
        "isbn_13": isbns[0] if isbns else None,
        "page_count": data.get("number_of_pages"),
        "ol_key": data.get("key"),
        "subjects": data.get("subjects", [])[:10],
    }


def _score_match(doc: dict, query: dict) -> float:
    """Rough relevance score for a search result."""
    score = 0.5
    if query.get("title") and doc.get("title"):
        if query["title"].lower() in doc["title"].lower():
            score += 0.2
    if query.get("author") and doc.get("author_name"):
        if any(query["author"].lower() in a.lower() for a in doc["author_name"]):
            score += 0.15
    if query.get("isbn_13") and doc.get("isbn"):
        if query["isbn_13"] in doc["isbn"]:
            score += 0.15
    return min(score, 0.95)

"""
Google Books Metadata source — Phase 3.

Free (limited), 20 req/min. Metadata only, used as fallback.
"""

import logging

import httpx

logger = logging.getLogger("gibson.sources.google_books")

API_BASE = "https://www.googleapis.com/books/v1/volumes"


async def search(query: dict, pool) -> list[dict]:
    """Search Google Books API for metadata."""
    results = []
    q_parts = []

    if query.get("isbn_13"):
        q_parts.append(f"isbn:{query['isbn_13']}")
    else:
        if query.get("title"):
            q_parts.append(f"intitle:{query['title']}")
        if query.get("author"):
            q_parts.append(f"inauthor:{query['author']}")

    if not q_parts:
        return []

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(API_BASE, params={"q": "+".join(q_parts), "maxResults": 10})
            if resp.status_code != 200:
                return []

            data = resp.json()
            for item in data.get("items", []):
                vol = item.get("volumeInfo", {})
                isbns = vol.get("industryIdentifiers", [])
                isbn_13 = None
                for ident in isbns:
                    if ident.get("type") == "ISBN_13":
                        isbn_13 = ident.get("identifier")
                        break

                results.append({
                    "source": "google_books_metadata",
                    "match_type": "isbn_exact" if query.get("isbn_13") else "search",
                    "confidence": 0.80 if query.get("isbn_13") else 0.55,
                    "title": vol.get("title"),
                    "author": (vol.get("authors") or [None])[0],
                    "isbn_13": isbn_13,
                    "publication_year": _extract_year(vol.get("publishedDate")),
                    "publisher": vol.get("publisher"),
                    "page_count": vol.get("pageCount"),
                    "language": vol.get("language"),
                    "subjects": vol.get("categories", []),
                    "google_books_id": item.get("id"),
                })

        except Exception as e:
            logger.error("Google Books search failed: %s", e)

    return results


def _extract_year(date_str: str | None) -> int | None:
    if not date_str:
        return None
    import re
    match = re.search(r"(\d{4})", date_str)
    return int(match.group(1)) if match else None

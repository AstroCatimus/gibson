"""
Open Library API service.

Ported from booksphere-mobile's lib/openLibrary.ts.
No API key required. User-Agent header identifies us politely.

Two entry points:
  fetch_by_isbn(isbn)          — ISBN lookup via /api/books endpoint
  search_by_text(title, author) — Text search with 3-strategy fallback
"""

import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger("gibson.services.open_library")

OL_HEADERS = {"User-Agent": "Gibson/1.0 (Alexandria Book Co-op - novaminowa@gmail.com)"}
SUMMARY_PATTERN = re.compile(
    r"^(summary|guide|analysis|review|study guide|workbook|notes on) of ", re.I
)


async def fetch_by_isbn(isbn: str) -> Optional[dict]:
    """
    Fetch full book data from Open Library by ISBN.
    Strategy 1: /api/books endpoint (richer data — publisher, cover, date).
    Strategy 2: /search.json?isbn= fallback (broader coverage for newer/obscure books).
    Returns None if not found in either.
    """
    isbn_clean = isbn.replace("-", "").strip()

    # ── Strategy 1: books API (rich data) ────────────────────────
    try:
        url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn_clean}&format=json&jscmd=data"
        async with httpx.AsyncClient(timeout=8.0, headers=OL_HEADERS) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                book = resp.json().get(f"ISBN:{isbn_clean}")
                if book:
                    return {
                        "isbn": isbn_clean,
                        "title": book.get("title", ""),
                        "authors": [a["name"] for a in book.get("authors", [])],
                        "publisher": book.get("publishers", [{}])[0].get("name", "") if book.get("publishers") else "",
                        "published_date": book.get("publish_date", ""),
                        "cover_image_url": (
                            book.get("cover", {}).get("large")
                            or book.get("cover", {}).get("medium")
                            or ""
                        ),
                        "page_count": book.get("number_of_pages"),
                        "subtitle": book.get("subtitle"),
                        "source": "open_library",
                        "confidence": 0.90,
                    }
    except Exception as e:
        logger.debug("Open Library books API failed: %s", e)

    # ── Strategy 2: search by ISBN (broader coverage) ─────────────
    try:
        async with httpx.AsyncClient(timeout=8.0, headers=OL_HEADERS) as client:
            resp = await client.get(
                "https://openlibrary.org/search.json",
                params={"isbn": isbn_clean, "limit": "1",
                        "fields": "title,author_name,isbn,publisher,publish_date,first_publish_year,cover_i,subtitle"},
            )
            if resp.status_code == 200:
                docs = resp.json().get("docs", [])
                if docs:
                    doc = docs[0]
                    cover_id = doc.get("cover_i")
                    publishers = doc.get("publisher") or []
                    return {
                        "isbn": isbn_clean,
                        "title": doc.get("title", ""),
                        "authors": doc.get("author_name") or [],
                        "publisher": publishers[0] if publishers else "",
                        "published_date": (
                            (doc.get("publish_date") or [None])[0]
                            or str(doc.get("first_publish_year") or "")
                        ),
                        "cover_image_url": f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else "",
                        "subtitle": doc.get("subtitle"),
                        "source": "open_library_search",
                        "confidence": 0.85,
                    }
    except Exception as e:
        logger.debug("Open Library search fallback failed: %s", e)

    return None


async def enrich_edition(db_result: dict) -> dict:
    """
    Fill gaps in a DB result using Open Library.
    Only fires if key fields are missing and ol_checked_at is NULL.
    Writes enriched fields back to gibson_edition / gibson_work.
    Returns the (possibly updated) db_result dict.
    """
    if db_result.get("ol_checked_at"):
        return db_result

    missing = not db_result.get("author") or not db_result.get("publication_year") or not db_result.get("publisher")
    if not missing:
        return db_result

    isbn = db_result.get("isbn_13") or db_result.get("isbn_10")
    if not isbn:
        return db_result

    ol = await fetch_by_isbn(isbn)

    from api.database import execute
    import re as _re

    # Stamp ol_checked_at regardless of whether OL had data
    await execute(
        "UPDATE gibson_edition SET ol_checked_at = now() WHERE edition_id = $1",
        db_result["edition_id"],
    )

    if not ol:
        return db_result

    authors = ol.get("authors") or []
    ol_author = authors[0] if authors else None
    pub_date = ol.get("published_date") or ""
    ol_year = None
    if pub_date:
        m = _re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", pub_date)
        ol_year = int(m.group(1)) if m else None
    ol_publisher = ol.get("publisher") or None

    # Merge: only fill fields that are missing in DB
    if not db_result.get("author") and ol_author:
        db_result["author"] = ol_author
    if not db_result.get("publication_year") and ol_year:
        db_result["publication_year"] = ol_year
        await execute(
            "UPDATE gibson_edition SET publication_year = $1, updated_at = now() WHERE edition_id = $2",
            ol_year, db_result["edition_id"],
        )
    if not db_result.get("publisher") and ol_publisher:
        db_result["publisher"] = ol_publisher

    return db_result


async def search_by_text(
    title: str,
    author: Optional[str] = None,
    publisher_override: Optional[str] = None,
) -> Optional[dict]:
    """
    Search Open Library by title + optional author.
    Three-strategy fallback matching booksphere's implementation exactly.
    Returns None if nothing matched.
    """
    if not title:
        return None

    doc = None

    # Strategy 1: title + author (most precise)
    if author:
        doc = await _ol_search({"title": title.lower(), "author": author.lower()})

    # Strategy 2: title only
    if not doc:
        doc = await _ol_search({"title": title.lower()})

    # Strategy 3: broad free-text fallback
    if not doc:
        q = f"{title.lower()} {(author or '').lower()}".strip()[:200]
        doc = await _ol_search({"q": q})

    if not doc:
        return None

    isbn13 = next((i for i in (doc.get("isbn") or []) if len(i) == 13), None)
    isbn10 = next((i for i in (doc.get("isbn") or []) if len(i) == 10), None)
    isbn = isbn13 or isbn10 or ""

    publishers = doc.get("publisher") or []
    cover_id = doc.get("cover_i")

    return {
        "isbn": isbn,
        "title": doc.get("title") or title,
        "authors": doc.get("author_name") or ([author] if author else []),
        "publisher": publisher_override or (publishers[0] if publishers else ""),
        "published_date": (
            doc.get("publish_date", [None])[0]
            or str(doc.get("first_publish_year") or "")
        ),
        "cover_image_url": f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else "",
        "source": "open_library",
        "confidence": 0.75,
    }


async def _ol_search(params: dict) -> Optional[dict]:
    """Run a single Open Library search and return first non-summary doc."""
    search_params = {
        **params,
        "limit": "5",
        "fields": "title,author_name,isbn,publisher,publish_date,first_publish_year,cover_i",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=OL_HEADERS) as client:
            resp = await client.get("https://openlibrary.org/search.json", params=search_params)
            if resp.status_code != 200:
                return None
            data = resp.json()
            for doc in data.get("docs", []):
                if SUMMARY_PATTERN.match(doc.get("title") or ""):
                    continue
                return doc
    except Exception as e:
        logger.debug("Open Library search failed: %s", e)
    return None

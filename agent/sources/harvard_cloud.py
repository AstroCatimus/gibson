"""
Harvard LibraryCloud source — Phase 3.

Free API, 100 req/min. 12.7M records, strong pre-ISBN scholarly material.
"""

import logging

import httpx

logger = logging.getLogger("gibson.sources.harvard_cloud")

API_BASE = "https://api.lib.harvard.edu/v2/items.json"


async def search(query: dict, pool) -> list[dict]:
    """Search Harvard LibraryCloud API."""
    results = []
    params = {"limit": 10}

    if query.get("isbn_13"):
        params["identifier"] = query["isbn_13"]
    elif query.get("title"):
        params["title"] = query["title"]
        if query.get("author"):
            params["name"] = query["author"]
    else:
        return []

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(API_BASE, params=params)
            if resp.status_code != 200:
                return []

            data = resp.json()
            for item in data.get("items", {}).get("mods", []):
                title_info = item.get("titleInfo", {})
                title = title_info.get("title") if isinstance(title_info, dict) else None

                name_info = item.get("name", [])
                author = None
                if isinstance(name_info, list) and name_info:
                    first_name = name_info[0]
                    if isinstance(first_name, dict):
                        author = first_name.get("namePart")

                origin = item.get("originInfo", {})
                year = None
                if isinstance(origin, dict):
                    date_issued = origin.get("dateIssued")
                    if date_issued:
                        import re
                        match = re.search(r"(\d{4})", str(date_issued))
                        if match:
                            year = int(match.group(1))

                identifiers = item.get("identifier", [])
                isbn = None
                if isinstance(identifiers, list):
                    for ident in identifiers:
                        if isinstance(ident, dict) and ident.get("type") == "isbn":
                            isbn = ident.get("#text") or ident.get("value")
                            break

                results.append({
                    "source": "harvard_librarycloud",
                    "match_type": "isbn_exact" if query.get("isbn_13") else "search",
                    "confidence": 0.85 if query.get("isbn_13") else 0.65,
                    "title": title,
                    "author": author,
                    "isbn_13": isbn,
                    "publication_year": year,
                })

        except Exception as e:
            logger.error("Harvard LibraryCloud search failed: %s", e)

    return results

"""
DuckDuckGo Research source — Phase 5.

Free, 20 req/min. General web search for title + author + publisher + year.
Last resort for items not found in bibliographic databases.
"""

import logging

import httpx

logger = logging.getLogger("gibson.sources.ddg_research")


async def search(query: dict, pool) -> list[dict]:
    """Search DuckDuckGo for bibliographic mentions."""
    results = []

    search_parts = []
    if query.get("title"):
        search_parts.append(f'"{query["title"]}"')
    if query.get("author"):
        search_parts.append(query["author"])
    if query.get("year"):
        search_parts.append(str(query["year"]))

    if not search_parts:
        return []

    search_query = " ".join(search_parts) + " book"

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get("https://api.duckduckgo.com/", params={
                "q": search_query,
                "format": "json",
                "no_redirect": 1,
                "no_html": 1,
            })

            if resp.status_code != 200:
                return []

            data = resp.json()

            # DDG Instant Answer API — limited but free
            if data.get("Abstract"):
                results.append({
                    "source": "duckduckgo_research",
                    "match_type": "instant_answer",
                    "confidence": 0.40,
                    "title": query.get("title"),
                    "abstract": data["Abstract"],
                    "abstract_source": data.get("AbstractSource"),
                    "abstract_url": data.get("AbstractURL"),
                })

            for related in data.get("RelatedTopics", [])[:5]:
                if isinstance(related, dict) and related.get("Text"):
                    results.append({
                        "source": "duckduckgo_research",
                        "match_type": "related",
                        "confidence": 0.25,
                        "text": related["Text"],
                        "url": related.get("FirstURL"),
                    })

        except Exception as e:
            logger.error("DuckDuckGo search failed: %s", e)

    return results

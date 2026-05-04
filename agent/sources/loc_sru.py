"""
Library of Congress SRU source — Phase 3.

Free API, 30 req/min. Authoritative for American publications.
Uses the Search/Retrieval via URL (SRU) protocol to query LOC catalog.
"""

import logging
import xml.etree.ElementTree as ET

import httpx

logger = logging.getLogger("gibson.sources.loc_sru")

SRU_BASE = "https://www.loc.gov/cgi-bin/retrieve"
SRU_SEARCH = "https://lx2.loc.gov/sru/lcdb"


async def search(query: dict, pool) -> list[dict]:
    """Search LOC via SRU protocol."""
    results = []

    cql_parts = []
    if query.get("isbn_13"):
        isbn = query["isbn_13"].replace("-", "")
        cql_parts.append(f'bath.isbn="{isbn}"')
    elif query.get("title"):
        cql_parts.append(f'dc.title="{query["title"]}"')
        if query.get("author"):
            cql_parts.append(f'dc.creator="{query["author"]}"')

    if not cql_parts:
        return []

    cql_query = " AND ".join(cql_parts)

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(SRU_SEARCH, params={
                "version": "1.1",
                "operation": "searchRetrieve",
                "query": cql_query,
                "maximumRecords": "10",
                "recordSchema": "dc"
            })

            if resp.status_code != 200:
                logger.warning("LOC SRU returned %d", resp.status_code)
                return []

            root = ET.fromstring(resp.text)
            ns = {
                "srw": "http://www.loc.gov/zing/srw/",
                "dc": "http://purl.org/dc/elements/1.1/"
            }

            for record in root.findall(".//srw:record", ns):
                data = record.find(".//srw:recordData", ns)
                if data is None:
                    continue

                title = _find_text(data, "dc:title", ns)
                creator = _find_text(data, "dc:creator", ns)
                date = _find_text(data, "dc:date", ns)
                publisher = _find_text(data, "dc:publisher", ns)
                identifier = _find_text(data, "dc:identifier", ns)
                subject = [el.text for el in data.findall("dc:subject", ns) if el.text]

                results.append({
                    "source": "loc_sru",
                    "match_type": "isbn_exact" if query.get("isbn_13") else "search",
                    "confidence": 0.92 if query.get("isbn_13") else _score(title, creator, query),
                    "title": title,
                    "author": creator,
                    "publication_year": _extract_year(date),
                    "publisher": publisher,
                    "loc_identifier": identifier,
                    "subjects": subject[:10],
                })

        except ET.ParseError as e:
            logger.error("LOC SRU XML parse error: %s", e)
        except Exception as e:
            logger.error("LOC SRU search failed: %s", e)

    return results


def _find_text(element, tag: str, ns: dict) -> str | None:
    """Find text content of a namespaced XML element."""
    el = element.find(tag, ns)
    return el.text if el is not None else None


def _extract_year(date_str: str | None) -> int | None:
    """Extract a 4-digit year from a date string."""
    if not date_str:
        return None
    import re
    match = re.search(r"(\d{4})", date_str)
    return int(match.group(1)) if match else None


def _score(title: str | None, creator: str | None, query: dict) -> float:
    """Rough relevance score."""
    score = 0.6  # LOC is authoritative, start higher
    if title and query.get("title"):
        if query["title"].lower() in title.lower():
            score += 0.15
    if creator and query.get("author"):
        if query["author"].lower() in creator.lower():
            score += 0.1
    return min(score, 0.92)

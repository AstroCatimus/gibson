"""
Deutsche Nationalbibliothek (DNB) source — Phase 3 (German signal).

Free API, 60 req/min. Authoritative for German publications post-1913.
Uses the SRU interface at services.dnb.de.
"""

import logging
import xml.etree.ElementTree as ET

import httpx

logger = logging.getLogger("gibson.sources.dnb")

SRU_BASE = "https://services.dnb.de/sru/dnb"


async def search(query: dict, pool) -> list[dict]:
    """Search DNB via SRU protocol."""
    results = []
    cql_parts = []

    if query.get("isbn_13"):
        cql_parts.append(f'num="{query["isbn_13"]}"')
    elif query.get("title"):
        cql_parts.append(f'tit="{query["title"]}"')
        if query.get("author"):
            cql_parts.append(f'per="{query["author"]}"')
    else:
        return []

    cql_query = " AND ".join(cql_parts)

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(SRU_BASE, params={
                "version": "1.1",
                "operation": "searchRetrieve",
                "query": cql_query,
                "maximumRecords": "10",
                "recordSchema": "MARC21-xml"
            })

            if resp.status_code != 200:
                return []

            # Parse MARC21-xml response
            root = ET.fromstring(resp.text)
            ns = {
                "srw": "http://www.loc.gov/zing/srw/",
                "marc": "http://www.loc.gov/MARC21/slim"
            }

            for record in root.findall(".//marc:record", ns):
                parsed = _parse_marc_record(record, ns)
                if parsed:
                    parsed["source"] = "dnb"
                    parsed["match_type"] = "isbn_exact" if query.get("isbn_13") else "search"
                    parsed["confidence"] = 0.92 if query.get("isbn_13") else 0.75
                    results.append(parsed)

        except ET.ParseError as e:
            logger.error("DNB XML parse error: %s", e)
        except Exception as e:
            logger.error("DNB search failed: %s", e)

    return results


def _parse_marc_record(record, ns: dict) -> dict | None:
    """Extract fields from a MARC21-xml record."""
    def get_field(tag: str, subfield: str) -> str | None:
        for df in record.findall(f"marc:datafield[@tag='{tag}']", ns):
            for sf in df.findall(f"marc:subfield[@code='{subfield}']", ns):
                return sf.text
        return None

    title = get_field("245", "a")
    author = get_field("100", "a")
    publisher = get_field("264", "b") or get_field("260", "b")
    date = get_field("264", "c") or get_field("260", "c")
    isbn = get_field("020", "a")

    if not title:
        return None

    import re
    year = None
    if date:
        match = re.search(r"(\d{4})", date)
        if match:
            year = int(match.group(1))

    return {
        "title": title.rstrip(" /"),
        "author": author.rstrip(",. ") if author else None,
        "publisher": publisher.rstrip(",. ") if publisher else None,
        "publication_year": year,
        "isbn_13": isbn,
        "language": "de",
    }

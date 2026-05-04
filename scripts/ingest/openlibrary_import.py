"""
Open Library Bulk Import — 4M filtered editions.

Downloads and imports the Open Library data dump (editions).
Filtered to records with ISBNs or significant bibliographic data.

Download: https://openlibrary.org/developers/dumps
Format: TSV with JSON in the last column.

Usage:
    python scripts/ingest/openlibrary_import.py path/to/ol_dump_editions.txt
    python scripts/ingest/openlibrary_import.py path/to/ol_dump_editions.txt --limit 100000
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from api.database import init_pool, close_pool, execute

logger = logging.getLogger("gibson.ingest.openlibrary")


async def import_openlibrary(filepath: str, limit: int = 0):
    """
    Import Open Library editions dump.

    OL dump format: type\tkey\trevision\tlast_modified\tJSON
    We parse the JSON column for bibliographic data.
    """
    pool = await init_pool()
    stats = {"total": 0, "imported": 0, "skipped": 0, "errors": 0}

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                stats["total"] += 1

                if limit and stats["total"] > limit:
                    break

                try:
                    parts = line.strip().split("\t")
                    if len(parts) < 5:
                        stats["skipped"] += 1
                        continue

                    record_type = parts[0]
                    key = parts[1]
                    data = json.loads(parts[4])

                    # Filter: only editions with ISBNs or substantial data
                    isbn_13_list = data.get("isbn_13", [])
                    isbn_10_list = data.get("isbn_10", [])
                    title = data.get("title", "")

                    if not isbn_13_list and not isbn_10_list and not title:
                        stats["skipped"] += 1
                        continue

                    isbn_13 = isbn_13_list[0] if isbn_13_list else None
                    if not isbn_13 and isbn_10_list:
                        from api.services.barcode import isbn_10_to_13
                        isbn_13 = isbn_10_to_13(isbn_10_list[0].replace("-", ""))

                    authors = data.get("authors", [])
                    author_name = None
                    if authors and isinstance(authors[0], dict):
                        author_name = authors[0].get("name")

                    publishers = data.get("publishers", [])
                    publisher = publishers[0] if publishers else None
                    publish_date = data.get("publish_date")
                    pages = data.get("number_of_pages")
                    subjects = data.get("subjects", [])

                    raw = json.dumps({
                        "key": key,
                        "title": title,
                        "author": author_name,
                        "isbn_13": isbn_13,
                        "publisher": publisher,
                        "publish_year": publish_date,
                        "number_of_pages": pages,
                        "subjects": subjects[:10] if isinstance(subjects, list) else [],
                    })

                    await execute(
                        pool,
                        """INSERT INTO gibson_source_record
                           (source, source_id, raw_data, normalized_title, normalized_author, isbn_13, trust_tier)
                           VALUES ('open_library', $1, $2::jsonb, $3, $4, $5, 4)
                           ON CONFLICT DO NOTHING""",
                        f"ol-{key}",
                        raw,
                        title[:500] if title else None,
                        author_name[:500] if author_name else None,
                        isbn_13,
                    )
                    stats["imported"] += 1

                except (json.JSONDecodeError, IndexError, KeyError) as e:
                    stats["errors"] += 1

                if stats["total"] % 10000 == 0:
                    logger.info("Processed %d, imported %d, skipped %d",
                                stats["total"], stats["imported"], stats["skipped"])

    finally:
        await close_pool()

    logger.info("Open Library import complete: %s", json.dumps(stats))
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import Open Library editions dump")
    parser.add_argument("filepath", help="Path to OL dump file")
    parser.add_argument("--limit", type=int, default=0, help="Max records to process (0=unlimited)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(import_openlibrary(args.filepath, args.limit))

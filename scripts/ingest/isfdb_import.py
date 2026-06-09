"""
ISFDB Dump Import — 2.38M records.

Imports the Internet Speculative Fiction Database MySQL dump into
gibson_edition_source for Phase 2 local lookups.

Download: https://isfdb.org/wiki/index.php/ISFDB_Downloads
Format: MySQL dump → convert to CSV or parse SQL INSERT statements.

Usage:
    python scripts/ingest/isfdb_import.py path/to/isfdb_titles.csv
    python scripts/ingest/isfdb_import.py path/to/isfdb_titles.csv --batch-size 5000
"""

import argparse
import asyncio
import csv
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from api.database import init_pool, close_pool, execute

logger = logging.getLogger("gibson.ingest.isfdb")

BATCH_SIZE = 1000


async def import_isfdb(filepath: str, batch_size: int = BATCH_SIZE):
    """
    Import ISFDB records into gibson_edition_source.

    Expected CSV columns: title_id, title, author, year, isbn, publisher,
    title_type, series, series_num, language
    """
    pool = await init_pool()
    stats = {"total": 0, "imported": 0, "errors": 0}
    batch = []

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)

            for row in reader:
                stats["total"] += 1

                record = {
                    "source_id": f"isfdb-{row.get('title_id', stats['total'])}",
                    "raw_data": json.dumps(dict(row)),
                    "title": (row.get("title") or "")[:500],
                    "author": (row.get("author") or "")[:500],
                    "isbn": _normalize_isbn(row.get("isbn")),
                }
                batch.append(record)

                if len(batch) >= batch_size:
                    imported = await _flush_batch(batch, pool)
                    stats["imported"] += imported
                    batch = []
                    logger.info("Processed %d rows, imported %d", stats["total"], stats["imported"])

            # Final batch
            if batch:
                imported = await _flush_batch(batch, pool)
                stats["imported"] += imported

    finally:
        await close_pool()

    logger.info("ISFDB import complete: %s", json.dumps(stats))
    return stats


async def _flush_batch(batch: list[dict], pool) -> int:
    """Insert a batch of records."""
    count = 0
    for record in batch:
        try:
            await execute(
                pool,
                """INSERT INTO gibson_edition_source
                   (source, source_id, raw_data, normalized_title, normalized_author, isbn_13, trust_tier)
                   VALUES ('isfdb', $1, $2::jsonb, $3, $4, $5, 4)
                   ON CONFLICT DO NOTHING""",
                record["source_id"],
                record["raw_data"],
                record["title"] or None,
                record["author"] or None,
                record["isbn"],
            )
            count += 1
        except Exception as e:
            logger.debug("Batch insert error: %s", e)
    return count


def _normalize_isbn(raw: str | None) -> str | None:
    """Normalize ISBN from ISFDB format."""
    if not raw:
        return None
    isbn = raw.replace("-", "").replace(" ", "").strip()
    if len(isbn) == 13 and isbn.startswith("978"):
        return isbn
    if len(isbn) == 10:
        from api.services.barcode import isbn_10_to_13
        return isbn_10_to_13(isbn)
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import ISFDB dump")
    parser.add_argument("filepath", help="Path to ISFDB CSV file")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(import_isfdb(args.filepath, args.batch_size))

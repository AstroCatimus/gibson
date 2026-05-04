"""
Kazam Legacy Inventory Import — 37,967 records.

Tab-delimited file from the Kazam POS system. Tier 3 trust level.
The `location` field = section code. Lower tiers never overwrite higher.
Conflicts are flagged, never auto-resolved.

Usage:
    python scripts/ingest/kazam_import.py path/to/kazam_export.tsv
    python scripts/ingest/kazam_import.py path/to/kazam_export.tsv --dry-run
"""

import argparse
import asyncio
import csv
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from api.config import get_settings
from api.database import init_pool, close_pool, fetch, fetchrow, execute
from api.services.barcode import normalize_isbn_13, validate_isbn_13, isbn_10_to_13

logger = logging.getLogger("gibson.ingest.kazam")

TRUST_TIER = 3  # Kazam is Tier 3 — below Amazon (2) and manual entry (1)


async def import_kazam(filepath: str, store_id: str, dry_run: bool = False):
    """
    Import Kazam tab-delimited export into Gibson.

    For each record:
    1. Normalize ISBN if present
    2. Check for existing record by ISBN
    3. If match found and higher-trust data exists, flag conflict
    4. If no match, create placeholder stock item routed to NEEDS_IDENTIFICATION
    5. Preserve raw Kazam record as JSONB in source_record
    """
    pool = await init_pool()

    stats = {"total": 0, "imported": 0, "matched_isbn": 0, "conflicts": 0, "errors": 0, "skipped": 0}

    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter="\t")

            for row in reader:
                stats["total"] += 1

                try:
                    await process_kazam_row(row, store_id, pool, stats, dry_run)
                except Exception as e:
                    stats["errors"] += 1
                    logger.error("Row %d error: %s — %s", stats["total"], str(e), row.get("title", "?"))

                if stats["total"] % 1000 == 0:
                    logger.info("Processed %d rows...", stats["total"])

    finally:
        await close_pool()

    logger.info("Import complete: %s", json.dumps(stats, indent=2))
    return stats


async def process_kazam_row(row: dict, store_id: str, pool, stats: dict, dry_run: bool):
    """Process a single Kazam record."""
    title = (row.get("title") or "").strip()
    author = (row.get("author") or "").strip()
    isbn_raw = (row.get("isbn") or "").strip()
    price_str = (row.get("price") or "0").strip()
    location = (row.get("location") or "").strip()  # Section code
    condition = (row.get("condition") or "").strip()

    if not title and not isbn_raw:
        stats["skipped"] += 1
        return

    # Normalize ISBN
    isbn_13 = None
    if isbn_raw:
        isbn_raw = isbn_raw.replace("-", "").replace(" ", "")
        if len(isbn_raw) == 10:
            isbn_13 = isbn_10_to_13(isbn_raw)
        elif len(isbn_raw) == 13:
            isbn_13 = isbn_raw
        if isbn_13 and not validate_isbn_13(isbn_13):
            isbn_13 = None

    # Parse price
    try:
        price = float(price_str.replace("$", "").replace(",", ""))
    except ValueError:
        price = 0.0

    # Check for existing record by ISBN
    existing = None
    if isbn_13:
        existing = await fetchrow(
            pool,
            """SELECT e.edition_id, e.work_id, si.stock_item_id, si.store_id,
                      w.title as existing_title
               FROM gibson_edition e
               JOIN gibson_work w ON e.work_id = w.work_id
               LEFT JOIN gibson_stock_item si ON si.edition_id = e.edition_id AND si.store_id = $2
               WHERE e.isbn_13 = $1
               LIMIT 1""",
            isbn_13, store_id
        )

    if existing:
        stats["matched_isbn"] += 1
        # Flag conflict if titles don't match closely enough
        if existing["existing_title"] and title:
            if title.lower()[:20] != existing["existing_title"].lower()[:20]:
                stats["conflicts"] += 1
                logger.warning(
                    "Title conflict: Kazam='%s' vs existing='%s' (ISBN %s)",
                    title, existing["existing_title"], isbn_13
                )
    else:
        stats["imported"] += 1

    if dry_run:
        return

    # Store raw Kazam record as source_record
    raw_data = json.dumps(dict(row))
    await execute(
        pool,
        """INSERT INTO gibson_source_record
           (source, source_id, raw_data, normalized_title, normalized_author, isbn_13, trust_tier)
           VALUES ('kazam', $1, $2::jsonb, $3, $4, $5, $6)
           ON CONFLICT DO NOTHING""",
        f"kazam-{stats['total']}",
        raw_data,
        title[:500] if title else None,
        author[:500] if author else None,
        isbn_13,
        TRUST_TIER,
    )

    # If no existing stock item, create placeholder
    if not existing or not existing.get("stock_item_id"):
        edition_id = existing["edition_id"] if existing else None
        await execute(
            pool,
            """INSERT INTO gibson_stock_item
               (store_id, edition_id, status, section, asking_price,
                condition_grade, source, source_raw)
               VALUES ($1, $2, 'NEEDS_IDENTIFICATION', $3, $4, $5, 'kazam', $6::jsonb)""",
            store_id,
            edition_id,
            location or None,
            price,
            condition or None,
            raw_data,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import Kazam legacy inventory")
    parser.add_argument("filepath", help="Path to Kazam TSV export file")
    parser.add_argument("--store-id", default="a1b2c3d4-0001-4000-8000-000000000001", help="Store UUID")
    parser.add_argument("--dry-run", action="store_true", help="Parse and validate without writing")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(import_kazam(args.filepath, args.store_id, dry_run=args.dry_run))

"""
Amazon Legacy Inventory Import.

Tab-delimited export from Amazon Seller Central. Tier 2 trust level.
The `item-note` field has section appended after dash ("Bio/G").
Lower tiers never overwrite higher. Conflicts flagged, never auto-resolved.

Usage:
    python scripts/ingest/amazon_import.py path/to/amazon_export.txt
    python scripts/ingest/amazon_import.py path/to/amazon_export.txt --dry-run
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

logger = logging.getLogger("gibson.ingest.amazon")

TRUST_TIER = 2


def parse_section_from_item_note(note: str) -> str | None:
    """
    Extract section code from Amazon item-note field.

    Format: "Bio/G" → section "Bio", store indicator "G" (Graffiti)
    The part after the dash or slash is the section code.
    """
    if not note:
        return None
    parts = note.split("/")
    if parts:
        return parts[0].strip()
    return note.strip()


async def import_amazon(filepath: str, store_id: str, dry_run: bool = False):
    """Import Amazon tab-delimited export into Gibson."""
    pool = await init_pool()
    stats = {"total": 0, "imported": 0, "matched_isbn": 0, "conflicts": 0, "errors": 0, "skipped": 0}

    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter="\t")

            for row in reader:
                stats["total"] += 1
                try:
                    await process_amazon_row(row, store_id, pool, stats, dry_run)
                except Exception as e:
                    stats["errors"] += 1
                    logger.error("Row %d error: %s", stats["total"], str(e))

                if stats["total"] % 500 == 0:
                    logger.info("Processed %d rows...", stats["total"])

    finally:
        await close_pool()

    logger.info("Import complete: %s", json.dumps(stats, indent=2))
    return stats


async def process_amazon_row(row: dict, store_id: str, pool, stats: dict, dry_run: bool):
    """Process a single Amazon listing record."""
    # Amazon export fields vary; common ones:
    asin = (row.get("asin1") or row.get("asin") or "").strip()
    sku = (row.get("seller-sku") or "").strip()
    title = (row.get("item-name") or row.get("product-name") or "").strip()
    price_str = (row.get("price") or row.get("item-price") or "0").strip()
    item_note = (row.get("item-note") or row.get("item-description") or "").strip()
    condition_str = (row.get("item-condition") or "").strip()

    if not title and not asin:
        stats["skipped"] += 1
        return

    # ASIN to ISBN: 10-digit ASINs starting with 0 are usually ISBN-10s
    isbn_13 = None
    if asin and len(asin) == 10 and asin[0] in "0123456789":
        isbn_13 = isbn_10_to_13(asin)
        if isbn_13 and not validate_isbn_13(isbn_13):
            isbn_13 = None

    section = parse_section_from_item_note(item_note)

    try:
        price = float(price_str.replace("$", "").replace(",", ""))
    except ValueError:
        price = 0.0

    # Check existing
    existing = None
    if isbn_13:
        existing = await fetchrow(
            pool,
            """SELECT e.edition_id, w.title as existing_title
               FROM gibson_edition e
               JOIN gibson_work w ON e.work_id = w.work_id
               WHERE e.isbn_13 = $1 LIMIT 1""",
            isbn_13
        )
        if existing:
            stats["matched_isbn"] += 1

    if not existing:
        stats["imported"] += 1

    if dry_run:
        return

    raw_data = json.dumps(dict(row))
    await execute(
        pool,
        """INSERT INTO gibson_source_record
           (source, source_id, raw_data, normalized_title, isbn_13, trust_tier)
           VALUES ('amazon', $1, $2::jsonb, $3, $4, $5)
           ON CONFLICT DO NOTHING""",
        f"amazon-{asin or sku or stats['total']}",
        raw_data,
        title[:500] if title else None,
        isbn_13,
        TRUST_TIER,
    )

    if not existing:
        await execute(
            pool,
            """INSERT INTO gibson_stock_item
               (store_id, status, section, asking_price, condition_grade, source, source_raw)
               VALUES ($1, 'NEEDS_IDENTIFICATION', $2, $3, $4, 'amazon', $5::jsonb)""",
            store_id,
            section,
            price,
            condition_str or None,
            raw_data,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import Amazon inventory export")
    parser.add_argument("filepath", help="Path to Amazon TSV export file")
    parser.add_argument("--store-id", default="a1b2c3d4-0001-4000-8000-000000000001")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(import_amazon(args.filepath, args.store_id, dry_run=args.dry_run))

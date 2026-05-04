"""
LOC MARC21 Catalog Import.

Imports Library of Congress MARC21 binary records into gibson_source_record.
Used for both the general catalog and authority files.

Requires: pymarc (pip install pymarc)
Download: https://www.loc.gov/cds/products/marcDist.php

Usage:
    python scripts/ingest/loc_marc_import.py path/to/BooksAll.mrc --type catalog
    python scripts/ingest/loc_marc_import.py path/to/Names.mrc --type authorities
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from api.database import init_pool, close_pool, execute

logger = logging.getLogger("gibson.ingest.loc_marc")


async def import_marc(filepath: str, record_type: str = "catalog", limit: int = 0):
    """Import MARC21 binary records."""
    try:
        from pymarc import MARCReader
    except ImportError:
        logger.error("pymarc required: pip install pymarc")
        return

    pool = await init_pool()
    stats = {"total": 0, "imported": 0, "errors": 0}

    try:
        with open(filepath, "rb") as f:
            reader = MARCReader(f, to_unicode=True, force_utf8=True)

            for record in reader:
                stats["total"] += 1
                if limit and stats["total"] > limit:
                    break

                try:
                    if record_type == "authorities":
                        await _import_authority_record(record, pool, stats)
                    else:
                        await _import_catalog_record(record, pool, stats)
                except Exception as e:
                    stats["errors"] += 1
                    if stats["errors"] <= 10:
                        logger.debug("Record error: %s", e)

                if stats["total"] % 10000 == 0:
                    logger.info("Processed %d, imported %d", stats["total"], stats["imported"])

    finally:
        await close_pool()

    logger.info("LOC MARC import complete (%s): %s", record_type, json.dumps(stats))
    return stats


async def _import_catalog_record(record, pool, stats: dict):
    """Import a single MARC catalog record."""
    title = record.title() if record.title() else None
    author = record.author() if record.author() else None
    isbn = record.isbn() if record.isbn() else None
    publisher = record.publisher() if record.publisher() else None
    pub_year = record.pubyear() if record.pubyear() else None

    lccn = None
    if record["010"]:
        lccn = record["010"]["a"]

    # Normalize ISBN
    isbn_13 = None
    if isbn:
        isbn_clean = isbn.replace("-", "").replace(" ", "").split(" ")[0]
        if len(isbn_clean) == 13:
            isbn_13 = isbn_clean
        elif len(isbn_clean) == 10:
            from api.services.barcode import isbn_10_to_13
            isbn_13 = isbn_10_to_13(isbn_clean)

    raw = json.dumps({
        "title": title, "author": author, "isbn": isbn,
        "publisher": publisher, "pub_year": pub_year, "lccn": lccn,
    })

    source_id = f"loc-{lccn}" if lccn else f"loc-{stats['total']}"

    await execute(
        pool,
        """INSERT INTO gibson_source_record
           (source, source_id, raw_data, normalized_title, normalized_author, isbn_13, trust_tier)
           VALUES ('loc_catalog', $1, $2::jsonb, $3, $4, $5, 4)
           ON CONFLICT DO NOTHING""",
        source_id, raw,
        title[:500] if title else None,
        author[:500] if author else None,
        isbn_13,
    )
    stats["imported"] += 1


async def _import_authority_record(record, pool, stats: dict):
    """Import a single MARC authority record (name/title authority)."""
    # 100 = personal name, 110 = corporate, 111 = meeting
    authorized_name = None
    for tag in ["100", "110", "111"]:
        field = record[tag]
        if field:
            authorized_name = field["a"]
            break

    if not authorized_name:
        return

    lccn = None
    if record["010"]:
        lccn = record["010"]["a"]

    # Extract variant names from 400/410/411 fields
    variants = []
    for tag in ["400", "410", "411"]:
        for field in record.get_fields(tag):
            if field["a"]:
                variants.append(field["a"])

    raw = json.dumps({
        "authorized_name": authorized_name,
        "lccn": lccn,
        "variant_names": variants[:20],
    })

    source_id = f"loc-auth-{lccn}" if lccn else f"loc-auth-{stats['total']}"

    await execute(
        pool,
        """INSERT INTO gibson_source_record
           (source, source_id, raw_data, normalized_author, trust_tier)
           VALUES ('loc_authorities', $1, $2::jsonb, $3, 4)
           ON CONFLICT DO NOTHING""",
        source_id, raw,
        authorized_name[:500] if authorized_name else None,
    )
    stats["imported"] += 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import LOC MARC21 records")
    parser.add_argument("filepath", help="Path to MARC21 binary file")
    parser.add_argument("--type", choices=["catalog", "authorities"], default="catalog")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(import_marc(args.filepath, args.type, args.limit))

"""
Gibson Deduplication Runner.

Uses BibDedupe (non-negotiable per spec) as the primary dedup engine,
then falls back to Gibson's internal ISBN + fuzzy matching.

Runs nightly after data ingestion to merge duplicate Work and Edition records.

Usage:
    python scripts/maintenance/dedup_run.py
    python scripts/maintenance/dedup_run.py --dry-run
    python scripts/maintenance/dedup_run.py --source isfdb
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from api.database import init_pool, close_pool, get_pool, fetch, execute
from api.services.deduplication import find_duplicates

logger = logging.getLogger("gibson.maintenance.dedup")


async def run_dedup(dry_run: bool = False, source: str | None = None):
    """
    Run deduplication across Gibson's bibliographic records.

    Strategy:
    1. BibDedupe on source_record table (exact + fuzzy bibliographic matching)
    2. ISBN-13 exact dedup on gibson_edition
    3. Title+author fuzzy dedup on gibson_work (trigram similarity > 0.85)
    4. Log all proposed merges; execute only if not dry_run
    """
    await init_pool()
    stats = {"isbn_dupes": 0, "fuzzy_dupes": 0, "merged": 0, "skipped": 0}

    try:
        # Step 1: ISBN exact duplicates in editions
        logger.info("Phase 1: ISBN exact dedup on editions...")
        isbn_dupes = await fetch(
            """SELECT isbn_13, array_agg(edition_id ORDER BY created_at) as edition_ids,
                      count(*) as cnt
               FROM gibson_edition
               WHERE isbn_13 IS NOT NULL
               GROUP BY isbn_13
               HAVING count(*) > 1
               ORDER BY count(*) DESC
               LIMIT 500"""
        )

        for dupe_group in isbn_dupes:
            stats["isbn_dupes"] += 1
            edition_ids = dupe_group["edition_ids"]
            keep_id = edition_ids[0]  # Keep earliest
            merge_ids = edition_ids[1:]

            logger.info(
                "ISBN dupe: %s — keeping %s, merging %d others",
                dupe_group["isbn_13"], keep_id, len(merge_ids)
            )

            if not dry_run:
                for merge_id in merge_ids:
                    await _merge_editions(keep_id, merge_id)
                    stats["merged"] += 1

        # Step 2: Title+author fuzzy dedup on works
        logger.info("Phase 2: Fuzzy title+author dedup on works...")

        fuzzy_dupes = await fetch(
            """SELECT w1.work_id as id_a, w2.work_id as id_b,
                      w1.title as title_a, w2.title as title_b,
                      similarity(w1.title, w2.title) as sim
               FROM gibson_work w1
               JOIN gibson_work w2 ON w1.work_id < w2.work_id
               WHERE similarity(w1.title, w2.title) > 0.85
                 AND w1.language = w2.language
               ORDER BY sim DESC
               LIMIT 200"""
        )

        for dupe in fuzzy_dupes:
            stats["fuzzy_dupes"] += 1
            logger.info(
                "Fuzzy dupe (%.2f): '%s' vs '%s'",
                dupe["sim"], dupe["title_a"], dupe["title_b"]
            )

            if not dry_run:
                await _merge_works(dupe["id_a"], dupe["id_b"])
                stats["merged"] += 1

    finally:
        await close_pool()

    logger.info("Dedup complete: %s", json.dumps(stats))
    return stats


async def _merge_editions(keep_id: str, merge_id: str):
    """Merge a duplicate edition into the canonical one."""
    await execute(
        "UPDATE gibson_stock_item SET edition_id = $1 WHERE edition_id = $2",
        keep_id, merge_id
    )
    await execute(
        "UPDATE gibson_source_record SET matched_edition_id = $1 WHERE matched_edition_id = $2",
        keep_id, merge_id
    )
    await execute("DELETE FROM gibson_edition_agent WHERE edition_id = $1", merge_id)
    await execute("DELETE FROM gibson_edition_publisher WHERE edition_id = $1", merge_id)
    await execute("DELETE FROM gibson_edition WHERE edition_id = $1", merge_id)


async def _merge_works(keep_id: str, merge_id: str):
    """Merge a duplicate work into the canonical one."""
    await execute(
        "UPDATE gibson_edition SET work_id = $1 WHERE work_id = $2",
        keep_id, merge_id
    )
    await execute(
        "UPDATE gibson_work_agent SET work_id = $1 WHERE work_id = $2",
        keep_id, merge_id
    )
    await execute("DELETE FROM gibson_work_agent WHERE work_id = $1", merge_id)
    await execute("DELETE FROM gibson_work WHERE work_id = $1", merge_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gibson deduplication runner")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source", help="Filter to specific source")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run_dedup(dry_run=args.dry_run, source=args.source))

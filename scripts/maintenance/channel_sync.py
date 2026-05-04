"""
Gibson Channel Sync — push inventory updates to sales channels.

Runs every 15 minutes via cron. Syncs to:
- Biblio (full catalogued inventory)
- Amazon (selective: ISBN + post-1970)
- eBay (selective)
- Website (Gibson as backend)

Channel routing rules from the spec:
- Biblio: everything with a Work+Edition+condition+price
- Amazon: ISBN required, post-1970, no signed/inscribed
- eBay: selective, dealer decision per item
- Whatnot: show-by-show, separate flow

Usage:
    python scripts/maintenance/channel_sync.py
    python scripts/maintenance/channel_sync.py --channel biblio
    python scripts/maintenance/channel_sync.py --dry-run
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from api.database import init_pool, close_pool, fetch, execute

logger = logging.getLogger("gibson.maintenance.channel_sync")


async def sync_channels(channel: str | None = None, dry_run: bool = False):
    """Sync inventory to sales channels."""
    pool = await init_pool()
    stats = {"biblio": 0, "amazon": 0, "ebay": 0, "website": 0, "errors": 0}

    try:
        channels_to_sync = [channel] if channel else ["biblio", "amazon", "website"]

        for ch in channels_to_sync:
            if ch == "biblio":
                stats["biblio"] = await _sync_biblio(pool, dry_run)
            elif ch == "amazon":
                stats["amazon"] = await _sync_amazon(pool, dry_run)
            elif ch == "website":
                stats["website"] = await _sync_website(pool, dry_run)

    except Exception as e:
        stats["errors"] += 1
        logger.error("Channel sync error: %s", e)
    finally:
        await close_pool()

    logger.info("Channel sync complete: %s", json.dumps(stats))
    return stats


async def _sync_biblio(pool, dry_run: bool) -> int:
    """
    Sync to Biblio — full catalogued inventory.

    Criteria: has Work + Edition + condition_grade + asking_price, status=AVAILABLE.
    """
    items = await fetch(
        pool,
        """SELECT si.stock_item_id, si.gibson_sku, si.asking_price, si.condition_grade,
                  w.title, e.isbn_13, e.publication_year, e.publisher_name,
                  a.name as author
           FROM gibson_stock_item si
           JOIN gibson_edition e ON si.edition_id = e.edition_id
           JOIN gibson_work w ON e.work_id = w.work_id
           LEFT JOIN gibson_edition_agent ea ON e.edition_id = ea.edition_id AND ea.role = 'author'
           LEFT JOIN gibson_agent a ON ea.agent_id = a.agent_id
           WHERE si.status = 'AVAILABLE'
             AND si.condition_grade IS NOT NULL
             AND si.asking_price > 0
             AND (si.channel_biblio_synced_at IS NULL
                  OR si.updated_at > si.channel_biblio_synced_at)
           LIMIT 500"""
    )

    logger.info("Biblio: %d items to sync", len(items))

    if not dry_run:
        from api.services.channels.biblio import sync_to_biblio
        for item in items:
            try:
                await sync_to_biblio(dict(item))
                await execute(
                    pool,
                    "UPDATE gibson_stock_item SET channel_biblio_synced_at = NOW() WHERE stock_item_id = $1",
                    item["stock_item_id"]
                )
            except Exception as e:
                logger.error("Biblio sync failed for %s: %s", item["gibson_sku"], e)

    return len(items)


async def _sync_amazon(pool, dry_run: bool) -> int:
    """
    Sync to Amazon — selective: ISBN required, post-1970, no signed/inscribed.
    """
    items = await fetch(
        pool,
        """SELECT si.stock_item_id, si.gibson_sku, si.asking_price, si.condition_grade,
                  w.title, e.isbn_13, e.publication_year,
                  a.name as author
           FROM gibson_stock_item si
           JOIN gibson_edition e ON si.edition_id = e.edition_id
           JOIN gibson_work w ON e.work_id = w.work_id
           LEFT JOIN gibson_edition_agent ea ON e.edition_id = ea.edition_id AND ea.role = 'author'
           LEFT JOIN gibson_agent a ON ea.agent_id = a.agent_id
           WHERE si.status = 'AVAILABLE'
             AND e.isbn_13 IS NOT NULL
             AND e.publication_year >= 1970
             AND si.signed = false
             AND si.inscribed = false
             AND si.asking_price > 0
             AND (si.channel_amazon_synced_at IS NULL
                  OR si.updated_at > si.channel_amazon_synced_at)
           LIMIT 500"""
    )

    logger.info("Amazon: %d items to sync", len(items))

    if not dry_run:
        from api.services.channels.amazon import sync_to_amazon
        for item in items:
            try:
                await sync_to_amazon(dict(item))
                await execute(
                    pool,
                    "UPDATE gibson_stock_item SET channel_amazon_synced_at = NOW() WHERE stock_item_id = $1",
                    item["stock_item_id"]
                )
            except Exception as e:
                logger.error("Amazon sync failed for %s: %s", item["gibson_sku"], e)

    return len(items)


async def _sync_website(pool, dry_run: bool) -> int:
    """Sync to website — Gibson serves as the backend directly."""
    # Website reads from the same DB — just count what's available
    row = await pool.fetchrow(
        "SELECT count(*) as cnt FROM gibson_stock_item WHERE status = 'AVAILABLE'"
    )
    count = row["cnt"] if row else 0
    logger.info("Website: %d items available", count)
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gibson channel sync")
    parser.add_argument("--channel", choices=["biblio", "amazon", "ebay", "website"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(sync_channels(channel=args.channel, dry_run=args.dry_run))

"""
Gibson order sync worker.
Runs every 2 minutes. Polls connected platforms for new orders.
When a sale is detected: marks the stock item SOLD, delists from all other platforms.

Two-layer reliability:
  1. Webhooks (Amazon EventBridge, eBay Platform Notifications) — real-time
  2. This polling worker — catches anything webhooks miss
"""

import asyncio
import datetime
import logging

from api.database import fetch, fetchrow, execute
from api.services.channels import get_adapter

logger = logging.getLogger("gibson.order_sync")

POLL_INTERVAL_SECONDS = 120  # 2 minutes


async def _process_order(seller_sku: str, platform: str, platform_order_id: str, sold_at_str: str):
    """Mark a sold item and delist it everywhere else."""
    row = await fetchrow(
        "SELECT stock_item_id, store_id, status FROM gibson_stock_item WHERE gibson_sku = $1",
        seller_sku,
    )
    if not row:
        logger.warning("order_sync: unknown SKU %s from %s order %s", seller_sku, platform, platform_order_id)
        return
    if row["status"] == "SOLD":
        return  # already handled

    stock_item_id = str(row["stock_item_id"])
    store_id = str(row["store_id"])

    # Parse sold_at
    try:
        sold_at = datetime.datetime.fromisoformat(sold_at_str.replace("Z", "+00:00"))
    except Exception:
        sold_at = datetime.datetime.now(datetime.timezone.utc)

    # Mark the stock item SOLD
    await execute(
        "UPDATE gibson_stock_item SET status = 'SOLD', updated_at = now() WHERE stock_item_id = $1",
        stock_item_id,
    )

    # Mark the platform listing SOLD
    await execute(
        """
        UPDATE gibson_listing
        SET status = 'SOLD', sold_at = $1, updated_at = now()
        WHERE stock_item_id = $2 AND platform = $3
        """,
        sold_at, stock_item_id, platform,
    )

    logger.info("order_sync: %s sold via %s (order %s)", seller_sku, platform, platform_order_id)

    # Delist from all other active platforms
    other_listings = await fetch(
        """
        SELECT gl.platform, gl.platform_listing_id, gl.listing_payload,
               gsi.access_token, gsi.refresh_token, gsi.token_expires_at,
               gsi.platform_seller_id, gsi.platform_meta
        FROM gibson_listing gl
        JOIN gibson_store_integration gsi
          ON gsi.store_id = gl.store_id AND gsi.platform = gl.platform
        WHERE gl.stock_item_id = $1 AND gl.status = 'ACTIVE' AND gl.platform != $2
        """,
        stock_item_id, platform,
    )

    for listing_row in other_listings:
        other_platform = listing_row["platform"]
        try:
            adapter = get_adapter(other_platform)
            await adapter.delist_item(dict(listing_row), dict(listing_row))
            await execute(
                "UPDATE gibson_listing SET status = 'DELISTED', updated_at = now() WHERE stock_item_id = $1 AND platform = $2",
                stock_item_id, other_platform,
            )
            logger.info("order_sync: delisted %s from %s after sale on %s", seller_sku, other_platform, platform)
        except Exception as e:
            logger.error("order_sync: delist from %s failed for %s: %s", other_platform, seller_sku, e)


async def _poll_platform(integration: dict):
    """Poll one integration for new orders since last check."""
    platform = integration["platform"]
    store_id = str(integration["store_id"])
    # Use updated_at as "last checked" — reasonable proxy
    since_raw = integration.get("updated_at") or datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
    if isinstance(since_raw, str):
        since = datetime.datetime.fromisoformat(since_raw.replace("Z", "+00:00"))
    else:
        since = since_raw.replace(tzinfo=datetime.timezone.utc) if since_raw.tzinfo is None else since_raw
    # Always look back at least 1 hour to catch any missed webhooks
    lookback = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
    since = min(since, lookback)

    try:
        adapter = get_adapter(platform)
        orders = await adapter.get_new_orders(since, dict(integration))
        for order in orders:
            if order.get("seller_sku"):
                await _process_order(
                    seller_sku=order["seller_sku"],
                    platform=platform,
                    platform_order_id=order.get("platform_order_id", ""),
                    sold_at_str=order.get("sold_at") or "",
                )
        # Update last-checked timestamp
        await execute(
            "UPDATE gibson_store_integration SET updated_at = now() WHERE integration_id = $1",
            str(integration["integration_id"]),
        )
    except Exception as e:
        logger.warning("order_sync: poll failed for %s store %s: %s", platform, store_id, e)


async def _check_pending_amazon_feeds():
    """
    For Amazon listings stuck in PENDING, poll the feed status.
    When DONE, verify condition_note persisted (GitHub issue #4653 workaround).
    """
    pending = await fetch(
        """
        SELECT gl.listing_id, gl.stock_item_id, gl.store_id, gl.platform_feed_id,
               gl.platform_listing_id,
               gsi.access_token, gsi.refresh_token, gsi.token_expires_at,
               gsi.platform_seller_id, gsi.platform_meta
        FROM gibson_listing gl
        JOIN gibson_store_integration gsi
          ON gsi.store_id = gl.store_id AND gsi.platform = gl.platform
        WHERE gl.platform = 'amazon' AND gl.status = 'PENDING'
          AND gl.platform_feed_id IS NOT NULL
        """,
    )

    from api.services.channels.amazon import AmazonAdapter
    adapter = AmazonAdapter()

    for row in pending:
        feed_id = row["platform_feed_id"]
        try:
            status = await adapter.poll_feed(feed_id, dict(row))
            if status == "DONE":
                sku = row["platform_listing_id"]
                note_ok = await adapter.verify_condition_note(sku, dict(row))
                new_status = "ACTIVE" if note_ok else "NEEDS_REVIEW"
                error = None if note_ok else "condition_note did not persist (Amazon bug #4653) — update manually in Seller Central"
                await execute(
                    """
                    UPDATE gibson_listing
                    SET status = $1, error_message = $2, updated_at = now()
                    WHERE listing_id = $3
                    """,
                    new_status, error, str(row["listing_id"]),
                )
                if new_status == "ACTIVE":
                    await execute(
                        "UPDATE gibson_stock_item SET status = 'LISTED', updated_at = now() WHERE stock_item_id = $1",
                        str(row["stock_item_id"]),
                    )
                logger.info("Amazon feed %s → %s for SKU %s", feed_id, new_status, sku)
            elif status in ("FATAL", "CANCELLED"):
                await execute(
                    "UPDATE gibson_listing SET status = 'FAILED', error_message = $1, updated_at = now() WHERE listing_id = $2",
                    f"Amazon feed {status}", str(row["listing_id"]),
                )
        except Exception as e:
            logger.warning("order_sync: feed poll failed %s: %s", feed_id, e)


async def order_sync_worker():
    """Background task. Runs for the lifetime of the API process."""
    logger.info("Order sync worker started (interval=%ds)", POLL_INTERVAL_SECONDS)
    while True:
        try:
            integrations = await fetch(
                "SELECT * FROM gibson_store_integration WHERE status = 'connected'",
            )
            for integration in integrations:
                await _poll_platform(integration)

            await _check_pending_amazon_feeds()

        except Exception as e:
            logger.warning("order_sync: sweep error: %s", e)

        await asyncio.sleep(POLL_INTERVAL_SECONDS)

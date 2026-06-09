"""
Gibson listings router.
Manages per-store marketplace connections and per-item listing lifecycle.

OAuth state is held in memory (short-lived — OAuth flows complete in seconds).
Tokens are stored in gibson_store_integration per store per platform.
"""

import datetime
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse

from api.dependencies import get_store_id
from api.database import fetch, fetchrow, execute
from api.services.channels import get_adapter

logger = logging.getLogger("gibson.listings")
router = APIRouter()

# Short-lived OAuth state tokens: { state_token: { store_id, platform, created_at } }
_oauth_states: dict = {}


def _purge_old_states():
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=10)
    stale = [k for k, v in _oauth_states.items() if v["created_at"] < cutoff]
    for k in stale:
        del _oauth_states[k]


# ── Enriched stock item query ─────────────────────────────────────────────────

async def _get_enriched_item(stock_item_id: str, store_id: str) -> dict:
    """Fetch a stock item with all fields needed for listing generation."""
    row = await fetchrow(
        """
        SELECT si.stock_item_id, si.gibson_sku, si.condition_grade, si.condition_notes,
               si.asking_price, si.images, si.amazon_asin, si.amazon_listing_id,
               si.is_signed, si.is_inscribed, si.store_id,
               e.isbn_13, e.publication_year, e.format,
               w.title, w.subtitle,
               (SELECT a.name_display
                FROM gibson_work_agent wa
                JOIN gibson_agent a ON a.agent_id = wa.agent_id
                WHERE wa.work_id = w.work_id AND wa.role = 'author'
                ORDER BY wa.role_order LIMIT 1) AS author,
               (SELECT pub.name_display
                FROM gibson_edition_publisher ep
                JOIN gibson_publisher pub ON pub.publisher_id = ep.publisher_id
                WHERE ep.edition_id = e.edition_id AND ep.role = 'publisher'
                LIMIT 1) AS publisher
        FROM gibson_stock_item si
        JOIN gibson_edition e ON e.edition_id = si.edition_id
        JOIN gibson_work w ON w.work_id = e.work_id
        WHERE si.stock_item_id = $1 AND si.store_id = $2
        """,
        stock_item_id, store_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Stock item not found")
    return dict(row)


# ── Platform connection management ────────────────────────────────────────────

@router.get("/platforms")
async def list_platforms(store_id: str = Depends(get_store_id)):
    """List all platform integrations for this store."""
    rows = await fetch(
        """
        SELECT platform, platform_seller_id, status, platform_meta,
               connected_at, token_expires_at
        FROM gibson_store_integration
        WHERE store_id = $1
        ORDER BY platform
        """,
        store_id,
    )
    return {"platforms": [dict(r) for r in rows]}


@router.delete("/platforms/{platform}")
async def disconnect_platform(
    platform: str,
    store_id: str = Depends(get_store_id),
):
    """Disconnect a marketplace integration for this store."""
    await execute(
        """
        UPDATE gibson_store_integration
        SET status = 'disconnected', updated_at = now()
        WHERE store_id = $1 AND platform = $2
        """,
        store_id, platform,
    )
    return {"status": "disconnected", "platform": platform}


# ── eBay OAuth ────────────────────────────────────────────────────────────────

@router.get("/connect/ebay")
async def connect_ebay_start(store_id: str = Depends(get_store_id)):
    """
    Step 1: return the eBay OAuth authorization URL.
    Mobile opens this URL in a browser/webview.
    """
    from api.services.channels.ebay import get_auth_url
    from api.config import settings

    _purge_old_states()
    state = str(uuid.uuid4())
    _oauth_states[state] = {
        "store_id": store_id,
        "platform": "ebay",
        "created_at": datetime.datetime.now(datetime.timezone.utc),
    }
    url = get_auth_url(state, settings.ebay_environment)
    return {"auth_url": url, "state": state}


@router.get("/connect/ebay/callback")
async def connect_ebay_callback(code: str, state: str, expires_in: int = 299):
    """
    Step 2: eBay redirects here with the authorization code.
    Exchanges code for tokens, stores integration, redirects to success.
    """
    from api.services.channels.ebay import exchange_code, fetch_business_policies
    from api.config import settings

    ctx = _oauth_states.pop(state, None)
    if not ctx:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    store_id = ctx["store_id"]
    tokens = await exchange_code(code, settings.ebay_environment)
    policies = await fetch_business_policies(tokens["access_token"], settings.ebay_environment)

    await execute(
        """
        INSERT INTO gibson_store_integration
            (store_id, platform, access_token, refresh_token, token_expires_at,
             status, platform_meta)
        VALUES ($1, 'ebay', $2, $3, $4, 'connected', $5::jsonb)
        ON CONFLICT (store_id, platform) DO UPDATE
          SET access_token = EXCLUDED.access_token,
              refresh_token = EXCLUDED.refresh_token,
              token_expires_at = EXCLUDED.token_expires_at,
              status = 'connected',
              platform_meta = EXCLUDED.platform_meta,
              updated_at = now()
        """,
        store_id,
        tokens["access_token"],
        tokens["refresh_token"],
        tokens["token_expires_at"],
        __import__("json").dumps({"policies": policies, "environment": settings.ebay_environment}),
    )
    logger.info("eBay connected for store %s", store_id)
    # TODO: redirect to app deep link / success page once website exists
    return {"status": "connected", "platform": "ebay", "policies": policies}


# ── Amazon OAuth ──────────────────────────────────────────────────────────────

@router.get("/connect/amazon")
async def connect_amazon_start(store_id: str = Depends(get_store_id)):
    """Step 1: return the Amazon seller authorization URL."""
    from api.services.channels.amazon import get_auth_url

    _purge_old_states()
    state = str(uuid.uuid4())
    _oauth_states[state] = {
        "store_id": store_id,
        "platform": "amazon",
        "created_at": datetime.datetime.now(datetime.timezone.utc),
    }
    url = get_auth_url(state)
    return {"auth_url": url, "state": state}


@router.get("/connect/amazon/callback")
async def connect_amazon_callback(
    spapi_oauth_code: str,
    selling_partner_id: str,
    state: str,
):
    """Step 2: Amazon redirects here. Exchange code for tokens."""
    from api.services.channels.amazon import exchange_code
    import json

    ctx = _oauth_states.pop(state, None)
    if not ctx:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    store_id = ctx["store_id"]
    tokens = await exchange_code(spapi_oauth_code, selling_partner_id)

    await execute(
        """
        INSERT INTO gibson_store_integration
            (store_id, platform, platform_seller_id, access_token, refresh_token,
             token_expires_at, status, platform_meta)
        VALUES ($1, 'amazon', $2, $3, $4, $5, 'connected', $6::jsonb)
        ON CONFLICT (store_id, platform) DO UPDATE
          SET platform_seller_id = EXCLUDED.platform_seller_id,
              access_token = EXCLUDED.access_token,
              refresh_token = EXCLUDED.refresh_token,
              token_expires_at = EXCLUDED.token_expires_at,
              status = 'connected',
              platform_meta = EXCLUDED.platform_meta,
              updated_at = now()
        """,
        store_id,
        selling_partner_id,
        tokens["access_token"],
        tokens["refresh_token"],
        tokens["token_expires_at"],
        json.dumps({"seller_id": selling_partner_id}),
    )
    logger.info("Amazon connected for store %s seller %s", store_id, selling_partner_id)
    return {"status": "connected", "platform": "amazon", "seller_id": selling_partner_id}


# ── eBay policy configuration ─────────────────────────────────────────────────

@router.patch("/platforms/ebay/policies")
async def set_ebay_policies(
    payload: dict,
    store_id: str = Depends(get_store_id),
):
    """
    Store eBay business policy IDs for this store.
    Required before any eBay listing can be published.
    Body: { fulfillment_policy_id, payment_policy_id, return_policy_id,
            merchant_location_key? }
    """
    import json

    row = await fetchrow(
        "SELECT platform_meta FROM gibson_store_integration WHERE store_id = $1 AND platform = 'ebay'",
        store_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="eBay not connected for this store")

    meta = dict(row["platform_meta"] or {})
    for field in ("fulfillment_policy_id", "payment_policy_id", "return_policy_id", "merchant_location_key"):
        if field in payload:
            meta[field] = payload[field]

    await execute(
        "UPDATE gibson_store_integration SET platform_meta = $1::jsonb, updated_at = now() WHERE store_id = $2 AND platform = 'ebay'",
        json.dumps(meta), store_id,
    )
    return {"status": "updated", "platform_meta": meta}


# ── Listing lifecycle ─────────────────────────────────────────────────────────

@router.post("/{stock_item_id}/description")
async def generate_description(
    stock_item_id: str,
    payload: dict,
    store_id: str = Depends(get_store_id),
):
    """
    Generate a two-zone listing description for a stock item.

    Body:
      platform          — 'ebay' | 'amazon' | 'biblio'
      deep_lookup_result — optional DeepLookupResult dict (from /deep-lookup/run)

    Returns:
      verified_facts    — template-built facts block (condition, jacket, signed, edition)
      narrative         — Haiku-suggested prose (dealer MUST review before posting)
      full_description  — both zones joined
      character_count   — length of full_description
      within_limit      — whether it fits the platform character cap
    """
    from api.services.description_builder import build_description

    platform = payload.get("platform", "ebay").lower()
    if platform not in ("ebay", "amazon", "biblio"):
        raise HTTPException(status_code=400, detail="platform must be ebay, amazon, or biblio")

    deep_lookup = payload.get("deep_lookup_result")

    item = await _get_enriched_item(stock_item_id, store_id)
    result = await build_description(item, platform, deep_lookup)
    return result


@router.get("/{stock_item_id}")
async def get_listings(
    stock_item_id: str,
    store_id: str = Depends(get_store_id),
):
    """Get current listing status for a stock item across all platforms."""
    rows = await fetch(
        """
        SELECT platform, platform_listing_id, platform_item_url,
               listed_price, status, error_message, created_at, updated_at, sold_at
        FROM gibson_listing
        WHERE stock_item_id = $1 AND store_id = $2
        ORDER BY platform
        """,
        stock_item_id, store_id,
    )
    return {"listings": [dict(r) for r in rows]}


@router.post("/{stock_item_id}/list")
async def list_item(
    stock_item_id: str,
    payload: dict,
    store_id: str = Depends(get_store_id),
):
    """
    List a stock item on one or more platforms.
    Body: { platforms: ['ebay', 'amazon'] }
    Returns per-platform results.
    """
    import json

    platforms = payload.get("platforms", [])
    if not platforms:
        raise HTTPException(status_code=400, detail="platforms list required")

    stock_item = await _get_enriched_item(stock_item_id, store_id)
    results = {}

    for platform in platforms:
        try:
            integration_row = await fetchrow(
                "SELECT * FROM gibson_store_integration WHERE store_id = $1 AND platform = $2 AND status = 'connected'",
                store_id, platform,
            )
            if not integration_row:
                results[platform] = {"status": "FAILED", "error": f"{platform} not connected"}
                continue

            integration = dict(integration_row)
            adapter = get_adapter(platform)
            result = await adapter.list_item(stock_item, integration)

            await execute(
                """
                INSERT INTO gibson_listing
                    (stock_item_id, store_id, platform, platform_listing_id,
                     platform_feed_id, platform_item_url, listed_price,
                     status, listing_payload)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
                ON CONFLICT (stock_item_id, platform) DO UPDATE
                  SET platform_listing_id = EXCLUDED.platform_listing_id,
                      platform_feed_id = EXCLUDED.platform_feed_id,
                      platform_item_url = EXCLUDED.platform_item_url,
                      listed_price = EXCLUDED.listed_price,
                      status = EXCLUDED.status,
                      listing_payload = EXCLUDED.listing_payload,
                      updated_at = now()
                """,
                stock_item_id, store_id, platform,
                result["platform_listing_id"],
                result.get("platform_feed_id"),
                result.get("platform_item_url"),
                stock_item.get("asking_price"),
                result["status"],
                json.dumps(result["payload"]),
            )

            # Update listing_channels on stock item
            await execute(
                """
                UPDATE gibson_stock_item
                SET listing_channels = array_append(
                    array_remove(listing_channels, $1), $1
                ),
                status = 'LISTED',
                updated_at = now()
                WHERE stock_item_id = $2
                """,
                platform, stock_item_id,
            )

            results[platform] = {"status": result["status"], "url": result.get("platform_item_url")}
            logger.info("Listed %s on %s → %s", stock_item["gibson_sku"], platform, result["status"])

        except Exception as e:
            logger.error("Failed to list %s on %s: %s", stock_item_id, platform, e)
            await execute(
                """
                INSERT INTO gibson_listing (stock_item_id, store_id, platform, status, error_message)
                VALUES ($1, $2, $3, 'FAILED', $4)
                ON CONFLICT (stock_item_id, platform) DO UPDATE
                  SET status = 'FAILED', error_message = EXCLUDED.error_message, updated_at = now()
                """,
                stock_item_id, store_id, platform, str(e)[:500],
            )
            results[platform] = {"status": "FAILED", "error": str(e)}

    return {"results": results}


@router.post("/{stock_item_id}/delist")
async def delist_item(
    stock_item_id: str,
    payload: dict,
    store_id: str = Depends(get_store_id),
):
    """
    Remove a listing from one or more platforms.
    Body: { platforms: ['ebay'] }
    """
    platforms = payload.get("platforms", [])
    results = {}

    for platform in platforms:
        listing_row = await fetchrow(
            "SELECT * FROM gibson_listing WHERE stock_item_id = $1 AND platform = $2 AND store_id = $3",
            stock_item_id, platform, store_id,
        )
        if not listing_row:
            results[platform] = {"status": "not_listed"}
            continue

        integration_row = await fetchrow(
            "SELECT * FROM gibson_store_integration WHERE store_id = $1 AND platform = $2",
            store_id, platform,
        )
        try:
            adapter = get_adapter(platform)
            success = await adapter.delist_item(dict(listing_row), dict(integration_row) if integration_row else {})

            await execute(
                """
                UPDATE gibson_listing SET status = 'DELISTED', updated_at = now()
                WHERE stock_item_id = $1 AND platform = $2
                """,
                stock_item_id, platform,
            )
            await execute(
                """
                UPDATE gibson_stock_item
                SET listing_channels = array_remove(listing_channels, $1),
                    updated_at = now()
                WHERE stock_item_id = $2
                """,
                platform, stock_item_id,
            )
            results[platform] = {"status": "delisted" if success else "failed"}
        except Exception as e:
            logger.error("Delist failed %s on %s: %s", stock_item_id, platform, e)
            results[platform] = {"status": "failed", "error": str(e)}

    return {"results": results}


@router.patch("/{stock_item_id}/price")
async def update_listing_price(
    stock_item_id: str,
    payload: dict,
    store_id: str = Depends(get_store_id),
):
    """
    Push a price change to all active listings for this stock item.
    Body: { price: 12.99 }
    Called automatically when dealer updates asking_price on the stock item.
    """
    new_price = payload.get("price")
    if new_price is None:
        raise HTTPException(status_code=400, detail="price required")

    active_listings = await fetch(
        """
        SELECT gl.*, gsi.access_token, gsi.refresh_token, gsi.token_expires_at,
               gsi.platform_seller_id, gsi.platform_meta
        FROM gibson_listing gl
        JOIN gibson_store_integration gsi
          ON gsi.store_id = gl.store_id AND gsi.platform = gl.platform
        WHERE gl.stock_item_id = $1 AND gl.store_id = $2 AND gl.status = 'ACTIVE'
        """,
        stock_item_id, store_id,
    )

    results = {}
    for row in active_listings:
        listing = dict(row)
        platform = listing["platform"]
        try:
            adapter = get_adapter(platform)
            ok = await adapter.update_price(listing, float(new_price), listing)
            results[platform] = {"status": "updated" if ok else "failed"}
        except Exception as e:
            results[platform] = {"status": "failed", "error": str(e)}

    return {"results": results}

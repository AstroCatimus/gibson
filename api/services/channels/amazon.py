"""
Gibson Amazon adapter — SP-API via JSON_LISTINGS_FEED.

Uses the Feeds API (not Listings Items API directly) because of
GitHub issue #4653: condition_note is silently dropped by putListingsItem
for ABIS_BOOK. The Feeds API persists it correctly.

After feed completion, getListingsItem is called to verify condition_note
actually saved. If not, listing is marked NEEDS_REVIEW.

Confirmed field structure from research (real payload from GitHub #4653):
  productType: ABIS_BOOK, requirements: LISTING_OFFER_ONLY
  condition_type: used_like_new / used_very_good / used_good / used_acceptable
  condition_note: plain text only, no HTML, no URLs, max 2000 chars
  Images: NOT required (rides existing product page)
  feedType: "JSON_LISTINGS_FEED"
"""

import datetime
import json
import logging

import httpx

from api.config import settings
from api.services.channels.base import PlatformAdapter

logger = logging.getLogger("gibson.channels.amazon")

SP_API_BASE = "https://sellingpartnerapi-na.amazon.com"
LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"

CONDITION_MAP = {
    "Fine":       "used_like_new",
    "Very Good+": "used_like_new",
    "Very Good":  "used_very_good",
    "Good+":      "used_good",
    "Good":       "used_good",
    "Fair":       "used_acceptable",
    "Poor":       "used_acceptable",
}


class AmazonAdapter(PlatformAdapter):

    async def _get_access_token(self, integration: dict) -> str:
        """Exchange refresh token for a fresh LWA access token."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                LWA_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": integration["refresh_token"],
                    "client_id": settings.amazon_lwa_client_id,
                    "client_secret": settings.amazon_lwa_client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()
        return data["access_token"]

    async def refresh_token(self, integration: dict) -> dict:
        """Amazon access tokens expire after 1 hour — always re-fetch via LWA."""
        access_token = await self._get_access_token(integration)
        expires_at = (
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
        )
        return {
            "access_token": access_token,
            "token_expires_at": expires_at.isoformat(),
        }

    def _sp_headers(self, access_token: str) -> dict:
        return {
            "x-amz-access-token": access_token,
            "Content-Type": "application/json",
        }

    async def list_item(self, stock_item: dict, integration: dict) -> dict:
        integration = await self.ensure_fresh_token(integration)
        token = integration["access_token"]
        meta = integration.get("platform_meta", {})
        marketplace_id = meta.get("marketplace_id", settings.amazon_marketplace_id)
        seller_id = meta.get("seller_id") or integration.get("platform_seller_id", "")
        sku = stock_item["gibson_sku"]

        asin = stock_item.get("amazon_asin")
        if not asin:
            raise ValueError(f"Cannot list on Amazon without ASIN. SKU {sku} has none.")

        condition_type = CONDITION_MAP.get(stock_item.get("condition_grade", ""), "used_good")
        condition_note = (stock_item.get("condition_notes") or "")[:2000]

        payload = {
            "header": {
                "sellerId": seller_id,
                "version": "2.0",
                "issueLocale": "en_US",
            },
            "messages": [
                {
                    "messageId": 1,
                    "sku": sku,
                    "operationType": "UPDATE",
                    "productType": "ABIS_BOOK",
                    "requirements": "LISTING_OFFER_ONLY",
                    "attributes": {
                        "merchant_suggested_asin": [
                            {"value": asin, "marketplace_id": marketplace_id}
                        ],
                        "condition_type": [
                            {"value": condition_type, "marketplace_id": marketplace_id}
                        ],
                        "condition_note": [
                            {"value": condition_note, "marketplace_id": marketplace_id}
                        ],
                        "purchasable_offer": [
                            {
                                "currency": "USD",
                                "audience": "ALL",
                                "marketplace_id": marketplace_id,
                                "our_price": [
                                    {
                                        "schedule": [
                                            {
                                                "value_with_tax": round(
                                                    stock_item.get("asking_price") or 0, 2
                                                )
                                            }
                                        ]
                                    }
                                ],
                            }
                        ],
                        "fulfillment_availability": [
                            {
                                "fulfillment_channel_code": "DEFAULT",
                                "marketplace_id": marketplace_id,
                            }
                        ],
                    },
                }
            ],
        }

        feed_id = await self._submit_feed(payload, marketplace_id, token)
        logger.info("Amazon feed submitted for SKU %s → feedId %s", sku, feed_id)

        return {
            "platform_listing_id": sku,
            "platform_feed_id": feed_id,
            "platform_item_url": None,
            "status": "PENDING",
            "payload": payload,
        }

    async def _submit_feed(self, payload: dict, marketplace_id: str, token: str) -> str:
        """
        Full 3-step Amazon feed submission:
          1. Create feed document → get presigned upload URL
          2. Upload JSON payload to presigned URL
          3. Create feed referencing the document
        Returns the feedId.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1 — create document
            r = await client.post(
                f"{SP_API_BASE}/feeds/2021-06-30/documents",
                headers=self._sp_headers(token),
                json={"contentType": "application/json"},
            )
            r.raise_for_status()
            doc = r.json()
            doc_id = doc["feedDocumentId"]
            upload_url = doc["url"]

            # Step 2 — upload payload to presigned URL
            r = await client.put(
                upload_url,
                content=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json; charset=UTF-8"},
            )
            r.raise_for_status()

            # Step 3 — create the feed
            r = await client.post(
                f"{SP_API_BASE}/feeds/2021-06-30/feeds",
                headers=self._sp_headers(token),
                json={
                    "feedType": "JSON_LISTINGS_FEED",
                    "marketplaceIds": [marketplace_id],
                    "inputFeedDocumentId": doc_id,
                },
            )
            r.raise_for_status()
            return r.json()["feedId"]

    async def poll_feed(self, feed_id: str, integration: dict) -> str:
        """
        Poll feed status. Returns: 'DONE' | 'IN_PROGRESS' | 'FATAL' | 'CANCELLED'.
        Call from the order-sync worker until done.
        """
        integration = await self.ensure_fresh_token(integration)
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f"{SP_API_BASE}/feeds/2021-06-30/feeds/{feed_id}",
                headers=self._sp_headers(integration["access_token"]),
            )
            r.raise_for_status()
            return r.json().get("processingStatus", "IN_PROGRESS")

    async def verify_condition_note(self, sku: str, integration: dict) -> bool:
        """
        Workaround for GitHub issue #4653: condition_note is sometimes silently
        dropped by Amazon. After a feed completes, call this to verify it persisted.
        Returns True if condition_note is present on the live listing.
        """
        integration = await self.ensure_fresh_token(integration)
        meta = integration.get("platform_meta", {})
        seller_id = meta.get("seller_id") or integration.get("platform_seller_id", "")
        marketplace_id = meta.get("marketplace_id", settings.amazon_marketplace_id)

        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f"{SP_API_BASE}/listings/2021-08-01/items/{seller_id}/{sku}",
                headers=self._sp_headers(integration["access_token"]),
                params={"marketplaceIds": marketplace_id, "includedData": "attributes"},
            )
            if r.status_code != 200:
                return False
            attrs = r.json().get("attributes", {})
            note = attrs.get("condition_note", [])
            return bool(note and note[0].get("value"))

    async def delist_item(self, listing: dict, integration: dict) -> bool:
        integration = await self.ensure_fresh_token(integration)
        meta = integration.get("platform_meta", {})
        seller_id = meta.get("seller_id") or integration.get("platform_seller_id", "")
        sku = listing.get("platform_listing_id")
        marketplace_id = meta.get("marketplace_id", settings.amazon_marketplace_id)

        if not sku or not seller_id:
            return False

        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.delete(
                f"{SP_API_BASE}/listings/2021-08-01/items/{seller_id}/{sku}",
                headers=self._sp_headers(integration["access_token"]),
                params={"marketplaceIds": marketplace_id},
            )

        if r.status_code in (200, 204, 404):
            logger.info("Amazon delisted SKU %s", sku)
            return True
        logger.warning("Amazon delist failed for SKU %s: %s", sku, r.status_code)
        return False

    async def update_price(self, listing: dict, new_price: float, integration: dict) -> bool:
        """Price update resubmits the full stored payload with updated price."""
        integration = await self.ensure_fresh_token(integration)
        meta = integration.get("platform_meta", {})
        marketplace_id = meta.get("marketplace_id", settings.amazon_marketplace_id)
        stored = listing.get("listing_payload")
        if not stored:
            return False

        # Update price in stored payload — always resubmit all fields
        msg = stored["messages"][0]
        for offer in msg["attributes"].get("purchasable_offer", []):
            for price in offer.get("our_price", []):
                for sched in price.get("schedule", []):
                    sched["value_with_tax"] = round(new_price, 2)

        feed_id = await self._submit_feed(
            stored, marketplace_id, integration["access_token"]
        )
        logger.info("Amazon price update feed %s for SKU %s", feed_id, listing["platform_listing_id"])
        return bool(feed_id)

    async def get_new_orders(
        self, since: datetime.datetime, integration: dict
    ) -> list[dict]:
        integration = await self.ensure_fresh_token(integration)
        meta = integration.get("platform_meta", {})
        marketplace_id = meta.get("marketplace_id", settings.amazon_marketplace_id)
        since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")

        orders = []
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(
                f"{SP_API_BASE}/orders/v0/orders",
                headers=self._sp_headers(integration["access_token"]),
                params={
                    "MarketplaceIds": marketplace_id,
                    "CreatedAfter": since_str,
                    "OrderStatuses": "Shipped,Delivered",
                },
            )
            if r.status_code != 200:
                logger.warning("Amazon get_new_orders failed: %s", r.status_code)
                return []

            for order in r.json().get("Orders", []):
                order_id = order["AmazonOrderId"]
                # Fetch order items to get SKUs
                ri = await client.get(
                    f"{SP_API_BASE}/orders/v0/orders/{order_id}/orderItems",
                    headers=self._sp_headers(integration["access_token"]),
                )
                if ri.status_code != 200:
                    continue
                for item in ri.json().get("OrderItems", []):
                    orders.append({
                        "platform_order_id": order_id,
                        "seller_sku": item.get("SellerSKU"),
                        "platform_listing_id": item.get("SellerSKU"),
                        "sold_at": order.get("PurchaseDate"),
                    })
        return orders


# ── OAuth helpers ────────────────────────────────────────────────────────────

def get_auth_url(state: str) -> str:
    """Build the Amazon SP-API seller authorization URL."""
    from urllib.parse import urlencode
    params = {
        "application_id": settings.amazon_lwa_client_id,
        "state": state,
        "version": "beta",
    }
    return f"https://sellercentral.amazon.com/apps/authorize/consent?{urlencode(params)}"


async def exchange_code(code: str, seller_id: str) -> dict:
    """
    Exchange an SP-API authorization code for LWA refresh token.
    seller_id comes from the callback's 'selling_partner_id' param.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            LWA_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.amazon_lwa_client_id,
                "client_secret": settings.amazon_lwa_client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        data = resp.json()

    expires_at = (
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
    )
    return {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "token_expires_at": expires_at.isoformat(),
        "platform_seller_id": seller_id,
    }

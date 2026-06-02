"""
Gibson eBay adapter — uses eBay Sell REST APIs (Inventory + Fulfillment).
NOT the Trading API (sunset) or Finding API (decommissioned Feb 2025).

Confirmed field requirements from research:
  - Category ID 267 (Books, US)
  - ConditionEnum: LIKE_NEW / USED_VERY_GOOD / USED_GOOD / USED_ACCEPTABLE
  - Title max ~80 chars
  - conditionDescription max 1,000 chars
  - listingDescription: HTML supported, required to publish
  - At least 1 image URL required to publish
  - Business policy IDs (fulfillment, payment, return) required to publish
  - Format: FIXED_PRICE, duration: GTC (Good Till Cancelled)
"""

import base64
import datetime
import logging
import re

import httpx

from api.config import settings
from api.services.channels.base import PlatformAdapter

logger = logging.getLogger("gibson.channels.ebay")

# eBay US Books category
BOOKS_CATEGORY_ID = "267"

CONDITION_MAP = {
    "Fine":       "LIKE_NEW",
    "Very Good+": "LIKE_NEW",
    "Very Good":  "USED_VERY_GOOD",
    "Good+":      "USED_GOOD",
    "Good":       "USED_GOOD",
    "Fair":       "USED_ACCEPTABLE",
    "Poor":       "USED_ACCEPTABLE",
}

CONDITION_DISPLAY = {
    "Fine":       "Fine",
    "Very Good+": "Very Good+",
    "Very Good":  "Very Good",
    "Good+":      "Good+",
    "Good":       "Good",
    "Fair":       "Fair",
    "Poor":       "Poor (Reading Copy)",
}


def _api_base(environment: str = "production") -> str:
    if environment == "sandbox":
        return "https://api.sandbox.ebay.com"
    return "https://api.ebay.com"


def _auth_base(environment: str = "production") -> str:
    if environment == "sandbox":
        return "https://auth.sandbox.ebay.com"
    return "https://auth.ebay.com"


def _build_title(stock_item: dict) -> str:
    """Build an eBay-safe title. Truncates at word boundary to fit 80 chars."""
    title = (stock_item.get("title") or "").strip()
    author = (stock_item.get("author") or "").strip()
    year = stock_item.get("publication_year")
    fmt = (stock_item.get("format") or "").strip()

    suffix_parts = []
    if author:
        suffix_parts.append(f"by {author}")
    if year:
        suffix_parts.append(f"({year})")
    if fmt:
        suffix_parts.append(fmt)
    suffix = " ".join(suffix_parts)

    full = f"{title} {suffix}".strip() if suffix else title
    if len(full) <= 80:
        return full

    # Truncate title at word boundary to make room for suffix
    available = 80 - (len(suffix) + 1 if suffix else 0)
    if available < 10:
        return full[:80]
    truncated = title[:available].rsplit(" ", 1)[0]
    return f"{truncated} {suffix}".strip() if suffix else truncated


def _build_description(stock_item: dict) -> str:
    """Build HTML listing description."""
    grade = stock_item.get("condition_grade") or ""
    notes = (stock_item.get("condition_notes") or "").strip()
    title = (stock_item.get("title") or "").strip()
    author = (stock_item.get("author") or "").strip()
    isbn = stock_item.get("isbn_13") or ""
    year = stock_item.get("publication_year") or ""

    lines = [f"<h2>{title}</h2>"]
    if author:
        lines.append(f"<p><strong>Author:</strong> {author}</p>")
    if isbn:
        lines.append(f"<p><strong>ISBN:</strong> {isbn}</p>")
    if year:
        lines.append(f"<p><strong>Year:</strong> {year}</p>")
    lines.append(f"<p><strong>Condition:</strong> {CONDITION_DISPLAY.get(grade, grade)}</p>")
    if notes:
        lines.append(f"<p>{notes}</p>")
    lines.append(
        "<p><em>All books are packed carefully and shipped promptly. "
        "Please message us with any questions.</em></p>"
    )
    return "\n".join(lines)


def _build_aspects(stock_item: dict) -> list[dict]:
    """Build eBay item specifics (aspects) for a book."""
    aspects = []
    if stock_item.get("author"):
        aspects.append({"name": "Author", "value": [stock_item["author"]]})
    if stock_item.get("publication_year"):
        aspects.append({"name": "Publication Year", "value": [str(stock_item["publication_year"])]})
    if stock_item.get("publisher"):
        aspects.append({"name": "Publisher", "value": [stock_item["publisher"]]})
    if stock_item.get("format"):
        aspects.append({"name": "Format", "value": [stock_item["format"]]})
    if stock_item.get("isbn_13"):
        aspects.append({"name": "ISBN", "value": [stock_item["isbn_13"]]})
    aspects.append({"name": "Language", "value": ["English"]})
    return aspects


class EbayAdapter(PlatformAdapter):

    def _headers(self, access_token: str) -> dict:
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Content-Language": "en-US",
            "Accept": "application/json",
        }

    def _env(self, integration: dict) -> str:
        return integration.get("platform_meta", {}).get("environment", settings.ebay_environment)

    async def refresh_token(self, integration: dict) -> dict:
        """Exchange refresh token for new access token."""
        env = self._env(integration)
        token_url = f"{_api_base(env)}/identity/v1/oauth2/token"
        credentials = base64.b64encode(
            f"{settings.ebay_app_id}:{settings.ebay_cert_id}".encode()
        ).decode()

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                token_url,
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": integration["refresh_token"],
                    "scope": (
                        "https://api.ebay.com/oauth/api_scope/sell.inventory "
                        "https://api.ebay.com/oauth/api_scope/sell.fulfillment "
                        "https://api.ebay.com/oauth/api_scope/sell.account"
                    ),
                },
            )
            resp.raise_for_status()
            data = resp.json()

        expires_at = (
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(seconds=data["expires_in"])
        )
        return {
            "access_token": data["access_token"],
            "token_expires_at": expires_at.isoformat(),
        }

    async def list_item(self, stock_item: dict, integration: dict) -> dict:
        integration = await self.ensure_fresh_token(integration)
        env = self._env(integration)
        base = _api_base(env)
        token = integration["access_token"]
        meta = integration.get("platform_meta", {})
        sku = stock_item["gibson_sku"]

        images = stock_item.get("images") or []
        if not images:
            raise ValueError(f"eBay requires at least one photo. SKU {sku} has none.")

        condition = CONDITION_MAP.get(stock_item.get("condition_grade", ""), "USED_GOOD")
        condition_desc = (stock_item.get("condition_notes") or "")[:1000]

        # Step 1 — create/replace inventory item
        inventory_payload = {
            "product": {
                "title": _build_title(stock_item),
                "imageUrls": images,
                "aspects": _build_aspects(stock_item),
            },
            "condition": condition,
            "conditionDescription": condition_desc,
            "availability": {
                "shipToLocationAvailability": {"quantity": 1}
            },
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.put(
                f"{base}/sell/inventory/v1/inventory_item/{sku}",
                headers=self._headers(token),
                json=inventory_payload,
            )
            if r.status_code not in (200, 204):
                raise RuntimeError(f"eBay createInventoryItem failed: {r.status_code} {r.text[:300]}")

            # Step 2 — create offer
            offer_payload = {
                "sku": sku,
                "marketplaceId": "EBAY_US",
                "format": "FIXED_PRICE",
                "listingDuration": "GTC",
                "availableQuantity": 1,
                "categoryId": BOOKS_CATEGORY_ID,
                "listingDescription": _build_description(stock_item),
                "pricingSummary": {
                    "price": {
                        "currency": "USD",
                        "value": str(round(stock_item.get("asking_price") or 0, 2)),
                    }
                },
                "listingPolicies": {
                    "fulfillmentPolicyId": meta.get("fulfillment_policy_id", ""),
                    "paymentPolicyId": meta.get("payment_policy_id", ""),
                    "returnPolicyId": meta.get("return_policy_id", ""),
                },
                "merchantLocationKey": meta.get("merchant_location_key", "default"),
            }

            r = await client.post(
                f"{base}/sell/inventory/v1/offer",
                headers=self._headers(token),
                json=offer_payload,
            )
            if r.status_code not in (200, 201):
                raise RuntimeError(f"eBay createOffer failed: {r.status_code} {r.text[:300]}")
            offer_id = r.json()["offerId"]

            # Step 3 — publish
            r = await client.post(
                f"{base}/sell/inventory/v1/offer/{offer_id}/publish",
                headers=self._headers(token),
            )
            if r.status_code not in (200, 201):
                raise RuntimeError(f"eBay publishOffer failed: {r.status_code} {r.text[:300]}")
            listing_id = r.json().get("listingId", offer_id)

        logger.info("eBay listed SKU %s → listingId %s offerId %s", sku, listing_id, offer_id)
        full_payload = {"inventory_item": inventory_payload, "offer": offer_payload, "offer_id": offer_id}
        return {
            "platform_listing_id": offer_id,
            "platform_item_url": f"https://www.ebay.com/itm/{listing_id}",
            "platform_feed_id": None,
            "status": "ACTIVE",
            "payload": full_payload,
        }

    async def delist_item(self, listing: dict, integration: dict) -> bool:
        integration = await self.ensure_fresh_token(integration)
        offer_id = listing.get("platform_listing_id")
        if not offer_id:
            return True

        env = self._env(integration)
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.delete(
                f"{_api_base(env)}/sell/inventory/v1/offer/{offer_id}",
                headers=self._headers(integration["access_token"]),
            )
        if r.status_code in (200, 204, 404):
            logger.info("eBay delisted offer %s", offer_id)
            return True
        logger.warning("eBay delist failed for offer %s: %s", offer_id, r.status_code)
        return False

    async def update_price(self, listing: dict, new_price: float, integration: dict) -> bool:
        integration = await self.ensure_fresh_token(integration)
        offer_id = listing.get("platform_listing_id")
        if not offer_id:
            return False

        env = self._env(integration)
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.patch(
                f"{_api_base(env)}/sell/inventory/v1/offer/{offer_id}",
                headers=self._headers(integration["access_token"]),
                json={
                    "pricingSummary": {
                        "price": {"currency": "USD", "value": str(round(new_price, 2))}
                    }
                },
            )
        return r.status_code in (200, 204)

    async def get_new_orders(
        self, since: datetime.datetime, integration: dict
    ) -> list[dict]:
        integration = await self.ensure_fresh_token(integration)
        env = self._env(integration)
        since_str = since.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        orders = []
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(
                f"{_api_base(env)}/sell/fulfillment/v1/order",
                headers=self._headers(integration["access_token"]),
                params={"filter": f"creationdate:[{since_str}..]", "limit": 50},
            )
            if r.status_code != 200:
                logger.warning("eBay get_new_orders failed: %s", r.status_code)
                return []

            for order in r.json().get("orders", []):
                if order.get("orderFulfillmentStatus") in ("NOT_STARTED", "IN_PROGRESS", "FULFILLED"):
                    for line in order.get("lineItems", []):
                        orders.append({
                            "platform_order_id": order["orderId"],
                            "seller_sku": line.get("sku"),
                            "platform_listing_id": line.get("legacyItemId"),
                            "sold_at": order.get("creationDate"),
                        })
        return orders


# ── OAuth helpers (called from listings router) ──────────────────────────────

def get_auth_url(state: str, environment: str = "production") -> str:
    """Build the eBay OAuth authorization URL."""
    from urllib.parse import urlencode
    params = {
        "client_id": settings.ebay_app_id,
        "response_type": "code",
        "redirect_uri": settings.ebay_ru_name,
        "scope": (
            "https://api.ebay.com/oauth/api_scope/sell.inventory "
            "https://api.ebay.com/oauth/api_scope/sell.fulfillment "
            "https://api.ebay.com/oauth/api_scope/sell.account"
        ),
        "state": state,
    }
    base = _auth_base(environment)
    return f"{base}/oauth2/authorize?{urlencode(params)}"


async def exchange_code(code: str, environment: str = "production") -> dict:
    """Exchange authorization code for access + refresh tokens."""
    credentials = base64.b64encode(
        f"{settings.ebay_app_id}:{settings.ebay_cert_id}".encode()
    ).decode()
    token_url = f"{_api_base(environment)}/identity/v1/oauth2/token"

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            token_url,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.ebay_ru_name,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    expires_at = (
        datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(seconds=data["expires_in"])
    )
    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", ""),
        "token_expires_at": expires_at.isoformat(),
    }


async def fetch_business_policies(access_token: str, environment: str = "production") -> dict:
    """
    Fetch the seller's eBay business policies.
    Returns { fulfillment: [...], payment: [...], return: [...] }
    so the store can pick which to use.
    """
    base = _api_base(environment)
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    result: dict = {}

    async with httpx.AsyncClient(timeout=15.0) as client:
        for policy_type in ("fulfillment_policy", "payment_policy", "return_policy"):
            r = await client.get(
                f"{base}/sell/account/v1/{policy_type}",
                headers=headers,
                params={"marketplace_id": "EBAY_US"},
            )
            if r.status_code == 200:
                key = policy_type.replace("_policy", "")
                result[key] = r.json().get(f"{key}Policies", [])

    return result

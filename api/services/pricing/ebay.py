"""
Gibson eBay pricing services.
eBay sold = realized prices (high weight, labeled SOLD)
eBay active = asking prices (medium weight, labeled ASKING)
"""

import httpx
from typing import Optional
from api.config import settings
from api.models.pricing import PriceComp


async def fetch_ebay_sold(
    isbn: Optional[str] = None,
    title: Optional[str] = None,
    author: Optional[str] = None,
) -> list[PriceComp]:
    """
    Fetch eBay completed/sold listings.
    Returns realized prices labeled SOLD.
    """
    if not settings.ebay_app_id:
        return []

    try:
        query = isbn or f"{title} {author}".strip()
        if not query:
            return []

        async with httpx.AsyncClient(timeout=10.0) as client:
            # eBay Finding API — findCompletedItems
            response = await client.get(
                "https://svcs.ebay.com/services/search/FindingService/v1",
                params={
                    "OPERATION-NAME": "findCompletedItems",
                    "SERVICE-VERSION": "1.13.0",
                    "SECURITY-APPNAME": settings.ebay_app_id,
                    "RESPONSE-DATA-FORMAT": "JSON",
                    "keywords": query,
                    "categoryId": "261186",  # Books category
                    "itemFilter(0).name": "SoldItemsOnly",
                    "itemFilter(0).value": "true",
                    "itemFilter(1).name": "Condition",
                    "itemFilter(1).value": "4000",  # Very Good
                    "sortOrder": "EndTimeSoonest",
                    "paginationInput.entriesPerPage": "10",
                },
            )

            if response.status_code != 200:
                return []

            data = response.json()
            return _parse_ebay_results(data, "realized")

    except Exception:
        return []


async def fetch_ebay_active(
    isbn: Optional[str] = None,
    title: Optional[str] = None,
    author: Optional[str] = None,
) -> list[PriceComp]:
    """
    Fetch current eBay active listings.
    Returns asking prices labeled ASKING.
    """
    if not settings.ebay_app_id:
        return []

    try:
        query = isbn or f"{title} {author}".strip()
        if not query:
            return []

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://svcs.ebay.com/services/search/FindingService/v1",
                params={
                    "OPERATION-NAME": "findItemsByKeywords",
                    "SERVICE-VERSION": "1.13.0",
                    "SECURITY-APPNAME": settings.ebay_app_id,
                    "RESPONSE-DATA-FORMAT": "JSON",
                    "keywords": query,
                    "categoryId": "261186",
                    "sortOrder": "PricePlusShippingLowest",
                    "paginationInput.entriesPerPage": "10",
                },
            )

            if response.status_code != 200:
                return []

            data = response.json()
            return _parse_ebay_results(data, "asking")

    except Exception:
        return []


def _parse_ebay_results(data: dict, price_type: str) -> list[PriceComp]:
    """Parse eBay API response into PriceComp list."""
    comps = []
    try:
        response_key = "findCompletedItemsResponse" if price_type == "realized" else "findItemsByKeywordsResponse"
        items = data.get(response_key, [{}])[0].get("searchResult", [{}])[0].get("item", [])

        for item in items[:10]:
            price_info = item.get("sellingStatus", [{}])[0]
            price_val = price_info.get("currentPrice", [{}])[0].get("__value__")
            if price_val:
                comps.append(PriceComp(
                    source="ebay",
                    price_type=price_type,
                    amount=float(price_val),
                    url=item.get("viewItemURL", [None])[0],
                    label="SOLD" if price_type == "realized" else "ASKING",
                ))
    except (KeyError, IndexError, TypeError):
        pass
    return comps

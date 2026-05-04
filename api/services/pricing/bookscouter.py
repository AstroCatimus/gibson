"""
Gibson BookScouter pricing service.
Trend data only. Supplemental weight. Labeled: TREND.
"""

import httpx
from typing import Optional
from api.config import settings
from api.models.pricing import PriceComp


async def fetch_bookscouter(isbn: Optional[str] = None) -> list[PriceComp]:
    """
    Fetch BookScouter trend data.
    Returns trend information labeled TREND.
    """
    if not isbn or not settings.bookscouter_api_key:
        return []

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"https://api.bookscouter.com/v3/prices/buy/{isbn}",
                headers={"Authorization": f"Bearer {settings.bookscouter_api_key}"},
            )

            if response.status_code != 200:
                return []

            data = response.json()
            comps = []

            for vendor in data.get("vendors", []):
                price = vendor.get("price")
                if price and float(price) > 0:
                    comps.append(PriceComp(
                        source="bookscouter",
                        price_type="trend",
                        amount=float(price),
                        label="TREND",
                    ))

            return comps

    except Exception:
        return []

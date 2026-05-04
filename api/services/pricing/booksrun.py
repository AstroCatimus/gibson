"""
Gibson BooksRun pricing service.
Low weight. Fire on all ISBNs, weight near zero pre-1990 and specialist.
Post-1990 commodity only.
"""

import httpx
from typing import Optional
from api.config import settings
from api.models.pricing import PriceComp


async def fetch_booksrun(isbn: Optional[str] = None) -> list[PriceComp]:
    """
    Fetch BooksRun pricing data.
    Low weight in the pricing stack — post-1990 commodity books only.
    """
    if not isbn or not settings.booksrun_api_key:
        return []

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # BooksRun API v3
            params = {"key": settings.booksrun_api_key}
            if settings.booksrun_affiliate_id:
                params["afk"] = settings.booksrun_affiliate_id
            response = await client.get(
                f"https://booksrun.com/api/v3/price/buy/{isbn}",
                params=params,
            )

            if response.status_code != 200:
                return []

            data = response.json()
            result = data.get("result", {})

            comps = []
            # Buyback prices
            for condition in ["new", "like_new", "very_good", "good", "acceptable"]:
                price = result.get("offers", {}).get(condition, {}).get("price")
                if price and float(price) > 0:
                    comps.append(PriceComp(
                        source="booksrun",
                        price_type="asking",
                        amount=float(price),
                        condition=condition.replace("_", " ").title(),
                        label="ASKING",
                    ))

            return comps

    except Exception:
        return []

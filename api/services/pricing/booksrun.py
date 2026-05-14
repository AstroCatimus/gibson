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
            offers = data.get("result", {}).get("offers", {})

            comps = []

            # BooksRun's own prices
            br = offers.get("booksrun", {})
            for cond, label in [("used", "Used"), ("new", "New")]:
                entry = br.get(cond)
                if isinstance(entry, dict):
                    price = entry.get("price")
                    if price and float(price) > 0:
                        comps.append(PriceComp(
                            source="booksrun",
                            price_type="asking",
                            amount=float(price),
                            condition=label,
                            label="ASKING",
                        ))

            # Marketplace sellers — use for range signal
            for seller in offers.get("marketplace", []):
                for cond in ("used", "new"):
                    entry = seller.get(cond)
                    if isinstance(entry, dict):
                        price = entry.get("price")
                        if price and float(price) > 0:
                            comps.append(PriceComp(
                                source="booksrun_marketplace",
                                price_type="asking",
                                amount=float(price),
                                condition=entry.get("condition", cond.title()),
                                label="ASKING",
                            ))

            return comps

    except Exception:
        return []

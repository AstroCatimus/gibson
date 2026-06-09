"""
Gibson pricing aggregator.
Fires all sources in parallel. Labels everything.

Current stack:
  Gibson POS    → Realized  → Highest weight (3.0)
  BookFinder    → Asking    → GATE (no API key required)
  BooksRun      → Asking    → Low weight (post-1990 only, 0.3)
  BookScouter   → Trend     → Supplemental (0.2)
  Claude Haiku  → Estimate  → Last resort (labeled: AI ESTIMATE — NO MARKET DATA)

When Vialibri partnership lands: replace BookFinder with a sanctioned Vialibri API client.
No scraping. No evasion. Identified as Gibson.

Add when ready:
  eBay sold     → add fetch_ebay_sold (needs API key)
  eBay active   → add fetch_ebay_active (needs API key)
"""

import asyncio
from typing import Optional
from uuid import UUID

from api.models.pricing import PricingResult, PriceComp
from api.services.pricing.bookfinder import fetch_bookfinder
from api.services.pricing.booksrun import fetch_booksrun
from api.services.pricing.bookscouter import fetch_bookscouter


async def get_pricing(
    isbn_13: Optional[str] = None,
    isbn_10: Optional[str] = None,
    title: Optional[str] = None,
    author: Optional[str] = None,
    edition_id: Optional[UUID] = None,
) -> PricingResult:
    """
    Fire all active pricing sources in parallel.
    Returns labeled, aggregated pricing result.
    """
    result = PricingResult(isbn=isbn_13, edition_id=edition_id)

    tasks = []
    isbn = isbn_13 or isbn_10

    if isbn or title:
        # BookFinder is the gate — must run first conceptually,
        # but we run all in parallel and check comps at the end
        tasks.append(("bookfinder", fetch_bookfinder(isbn=isbn, title=title, author=author)))
        if isbn:
            tasks.append(("booksrun", fetch_booksrun(isbn=isbn)))
            tasks.append(("bookscouter", fetch_bookscouter(isbn=isbn)))

    if edition_id:
        tasks.append(("gibson_pos", _fetch_pos_history(edition_id)))

    if tasks:
        names, coros = zip(*tasks)
        results = await asyncio.gather(*coros, return_exceptions=True)

        for name, res in zip(names, results):
            if isinstance(res, Exception):
                continue
            if not res:
                continue

            if name == "bookfinder":
                result.gate = res
                result.gate_has_comps = len(res) > 0
            elif name == "booksrun":
                result.booksrun = res
            elif name == "bookscouter":
                result.bookscouter = res
            elif name == "gibson_pos":
                result.gibson_pos = res

    result.total_comps = (
        len(result.gibson_pos) + len(result.gate)
        + len(result.booksrun) + len(result.bookscouter)
    )

    _calculate_suggestion(result)
    return result


def _calculate_suggestion(result: PricingResult):
    """
    Calculate suggested price from weighted sources.
    Gibson POS > BookFinder asking > BooksRun > BookScouter
    """
    prices = []

    for comp in result.gibson_pos:
        prices.append((comp.amount, 3.0))

    for comp in result.gate:
        prices.append((comp.amount, 1.5))

    for comp in result.booksrun:
        prices.append((comp.amount, 0.3))

    for comp in result.bookscouter:
        prices.append((comp.amount, 0.2))

    if not prices:
        return

    # Weighted average
    total_weight = sum(w for _, w in prices)
    weighted_sum = sum(p * w for p, w in prices)
    result.suggested_price = round(weighted_sum / total_weight, 2)

    all_prices = [p for p, _ in prices]
    result.price_range_low = min(all_prices)
    result.price_range_high = max(all_prices)


async def _fetch_pos_history(edition_id: UUID) -> list[PriceComp]:
    """Fetch Gibson's own realized prices for this edition."""
    from api.database import fetch

    rows = await fetch(
        """
        SELECT amount, retrieved_at, condition_grade
        FROM gibson_pricing_record
        WHERE edition_id = $1 AND source = 'gibson_pos'
        ORDER BY retrieved_at DESC
        LIMIT 10
        """,
        str(edition_id),
    )
    return [
        PriceComp(
            source="gibson_pos",
            price_type="realized",
            amount=float(r["amount"]),
            condition=r["condition_grade"],
            date=r["retrieved_at"],
            label="SOLD",
        )
        for r in rows
    ]

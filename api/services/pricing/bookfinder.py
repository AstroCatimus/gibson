"""
BookFinder.com pricing service — stand-in for Vialibri.

Aggregates AbeBooks, Alibris, ThriftBooks, and ~30 other dealers.
No account needed. Used as THE GATE until Vialibri is stable.

Same gate logic applies: no comps = dealer decides before online listing.
"""

import asyncio
import logging
import random
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from api.models.pricing import PriceComp

logger = logging.getLogger("gibson.pricing.bookfinder")

BOOKFINDER_BASE = "https://www.bookfinder.com"


async def fetch_bookfinder(
    isbn: Optional[str] = None,
    title: Optional[str] = None,
    author: Optional[str] = None,
) -> list[PriceComp]:
    """
    Search BookFinder for used/collectible asking prices.

    ISBN search is most reliable. Title+author fallback.
    Returns empty list on any failure — gate triggers, dealer decides.
    """
    if not isbn and not title:
        return []

    try:
        url, params = _build_search(isbn, title, author)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.bookfinder.com/",
        }

        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            # Small delay — be a polite scraper
            await asyncio.sleep(random.uniform(0.5, 1.5))
            resp = await client.get(url, params=params, headers=headers)

            if not (200 <= resp.status_code < 300):
                logger.warning("BookFinder returned %d", resp.status_code)
                return []

            comps = _parse_results(resp.text)
            logger.info("BookFinder: %d comps for %s", len(comps), isbn or title)
            return comps

    except Exception as e:
        logger.warning("BookFinder fetch failed (gate triggered): %s", e)
        return []


def _build_search(isbn, title, author) -> tuple[str, dict]:
    """Build BookFinder search URL."""
    if isbn:
        # ISBN search via their direct ISBN URL
        clean = isbn.replace("-", "")
        return f"{BOOKFINDER_BASE}/search/", {
            "author": "",
            "title": "",
            "lang": "en",
            "isbn": clean,
            "new_used": "*",          # all conditions
            "destination": "us",
            "currency": "USD",
            "mode": "basic",
            "st": "sr",
            "ac": "qr",
        }
    else:
        return f"{BOOKFINDER_BASE}/search/", {
            "author": author or "",
            "title": title or "",
            "lang": "en",
            "isbn": "",
            "new_used": "*",
            "destination": "us",
            "currency": "USD",
            "mode": "basic",
            "st": "sr",
            "ac": "qr",
        }


def _parse_results(html: str) -> list[PriceComp]:
    """
    Parse BookFinder results page.

    Results are in a table with class 'results' or similar.
    Each row has: seller, condition, price, shipping.
    """
    comps = []

    try:
        soup = BeautifulSoup(html, "html.parser")

        # BookFinder result items — each listing has a price
        # Their structure: .price elements or spans with dollar amounts
        price_cells = soup.find_all(class_=re.compile(r"price", re.I))

        seen_prices = set()
        for cell in price_cells[:30]:
            text = cell.get_text(strip=True)
            # Match dollar amounts: $12.95, $1,234.00
            match = re.search(r"\$\s*([\d,]+(?:\.\d{2})?)", text)
            if not match:
                continue
            try:
                amount = float(match.group(1).replace(",", ""))
            except ValueError:
                continue

            # Sanity range and dedup
            if not (0.25 <= amount <= 25000):
                continue
            if amount in seen_prices:
                continue
            seen_prices.add(amount)

            # Try to get condition from parent row
            condition = None
            parent = cell.find_parent("tr") or cell.find_parent("li") or cell.find_parent("div")
            if parent:
                cond_el = parent.find(class_=re.compile(r"condition|quality", re.I))
                if cond_el:
                    condition = cond_el.get_text(strip=True)[:50]

            comps.append(PriceComp(
                source="bookfinder",
                price_type="asking",
                amount=amount,
                label="ASKING",
                currency="USD",
                condition=condition,
                seller=None,
            ))

        # Sort ascending — lowest comps first
        comps.sort(key=lambda c: c.amount)
        return comps[:15]

    except Exception as e:
        logger.error("BookFinder parse error: %s", e)
        return []

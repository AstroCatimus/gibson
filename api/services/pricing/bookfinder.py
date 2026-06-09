"""
BookFinder.com pricing service — stand-in gate until a sanctioned Vialibri API exists.

Gate rule: no comp found = dealer decides before online listing.
Parse rule: every PriceComp returned must correspond to one real listing.
            Price and condition must come from the same result element.
            If the page doesn't parse cleanly, return empty — silence is honest.
"""

import asyncio
import logging
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
    Fetch used/collectible asking prices from BookFinder.
    Returns empty list on any failure — gate triggers, dealer decides.
    """
    if not isbn and not title:
        return []

    try:
        url, params = _build_search(isbn, title, author)
        headers = {
            "User-Agent": "Gibson/1.0 (Alexandria Book Co-op; pricing lookup)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }

        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
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
    base_params = {
        "lang": "en",
        "new_used": "U",      # used only — we care about used/collectible
        "destination": "us",
        "currency": "USD",
        "mode": "basic",
        "st": "sr",
        "ac": "qr",
    }
    if isbn:
        return f"{BOOKFINDER_BASE}/search/", {
            **base_params,
            "isbn": isbn.replace("-", ""),
            "author": "",
            "title": "",
        }
    return f"{BOOKFINDER_BASE}/search/", {
        **base_params,
        "isbn": "",
        "author": author or "",
        "title": title or "",
    }


def _parse_results(html: str) -> list[PriceComp]:
    """
    Parse BookFinder results page into PriceComp objects.

    Finds the results container, then iterates individual listing rows.
    Price and condition are extracted from the *same* listing element —
    they are never mixed across different rows.

    Returns empty list if the page structure doesn't match or on any error.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")

        # BookFinder wraps all results in a container with id="booksResults"
        # or a <section>/<div> with class containing "results"
        results_container = (
            soup.find(id="booksResults")
            or soup.find(id="results")
            or soup.find(class_=re.compile(r"\bresults\b", re.I))
        )

        if not results_container:
            logger.debug("BookFinder: no results container found — returning empty")
            return []

        # Each listing is a <li> or <div> directly inside the container.
        # Try <li> first (most common BookFinder structure), fall back to divs.
        listing_elements = results_container.find_all("li", recursive=False)
        if not listing_elements:
            listing_elements = results_container.find_all(
                "div", class_=re.compile(r"\bresult\b|\blisting\b|\bitem\b", re.I),
                recursive=False,
            )

        if not listing_elements:
            logger.debug("BookFinder: no individual listing elements found — returning empty")
            return []

        comps = []
        seen_prices: set = set()

        for el in listing_elements[:20]:
            comp = _parse_single_listing(el)
            if comp is None:
                continue
            # Deduplicate by exact amount
            if comp.amount in seen_prices:
                continue
            seen_prices.add(comp.amount)
            comps.append(comp)

        comps.sort(key=lambda c: c.amount)
        return comps[:15]

    except Exception as e:
        logger.error("BookFinder parse error: %s", e)
        return []


def _parse_single_listing(el) -> Optional[PriceComp]:
    """
    Extract a PriceComp from a single listing element.
    Both price and condition must be found within this element.
    Returns None if price cannot be determined.
    """
    # ── Price ──────────────────────────────────────────────────────────────────
    # Look for an element whose class suggests it carries the price,
    # but only within this listing's subtree.
    price_el = (
        el.find(class_=re.compile(r"\bprice\b", re.I))
        or el.find("span", string=re.compile(r"\$"))
    )

    if not price_el:
        return None

    price_text = price_el.get_text(strip=True)
    price_match = re.search(r"\$\s*([\d,]+(?:\.\d{2})?)", price_text)
    if not price_match:
        return None

    try:
        amount = float(price_match.group(1).replace(",", ""))
    except ValueError:
        return None

    # Sanity check — exclude shipping costs, prices out of realistic book range
    if not (0.50 <= amount <= 25_000):
        return None

    # ── Condition ──────────────────────────────────────────────────────────────
    condition = None
    cond_el = el.find(class_=re.compile(r"\bcondition\b|\bquality\b", re.I))
    if cond_el:
        condition = cond_el.get_text(strip=True)[:80]

    # ── Seller ─────────────────────────────────────────────────────────────────
    seller = None
    seller_el = el.find(class_=re.compile(r"\bseller\b|\bmerchant\b|\bvendor\b", re.I))
    if seller_el:
        seller = seller_el.get_text(strip=True)[:100]

    return PriceComp(
        source="bookfinder",
        price_type="asking",
        amount=amount,
        label="ASKING",
        currency="USD",
        condition=condition,
        seller=seller,
    )

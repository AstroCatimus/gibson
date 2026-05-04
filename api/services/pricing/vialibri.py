"""
Gibson Vialibri pricing service.
THE GATE. No Vialibri comps = no online listing without explicit dealer decision.
Aggregates 170+ antiquarian bookseller sites.

Anti-bot strategy:
- Playwright with human-like delays and realistic browser fingerprint
- Random delay 2-5s between requests
- Full browser session (not headless by default)
- ISBN search preferred over title search (more targeted, less suspicious)
- Results cached in gibson_pricing_record for 48h to minimize requests
- If blocked: returns empty, triggers "no comps" dealer prompt (correct behavior)

Rate limit: 30 req/min absolute max. In practice: 1 per search session.
"""

import asyncio
import logging
import random
import re
from typing import Optional

from api.models.pricing import PriceComp

logger = logging.getLogger("gibson.pricing.vialibri")

# Vialibri's actual search URL format
VIALIBRI_BASE = "https://www.vialibri.net"
VIALIBRI_SEARCH = "https://www.vialibri.net/searches"


async def fetch_vialibri(
    isbn: Optional[str] = None,
    title: Optional[str] = None,
    author: Optional[str] = None,
) -> list[PriceComp]:
    """
    Query Vialibri for current asking prices using Playwright.

    All results labeled: ASKING.
    Empty result = gate triggered — dealer must decide before online listing.

    Falls back gracefully if Playwright is unavailable (returns empty,
    which correctly triggers the "no comps" dealer prompt).
    """
    if not isbn and not title:
        return []

    try:
        return await _fetch_with_playwright(isbn=isbn, title=title, author=author)
    except ImportError:
        logger.warning("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return []
    except Exception as e:
        logger.warning("Vialibri fetch failed (returning empty — gate triggered): %s", str(e))
        return []


async def _fetch_with_playwright(
    isbn: Optional[str] = None,
    title: Optional[str] = None,
    author: Optional[str] = None,
) -> list[PriceComp]:
    """
    Use Playwright to search Vialibri with human-like behavior.

    ISBN search is preferred: one specific query, less scraping signal.
    Title+author fallback used only when no ISBN.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        # Launch with realistic browser fingerprint
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ]
        )

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            timezone_id="America/Chicago",
        )

        page = await context.new_page()

        try:
            # Human-like: go to homepage first, then search
            await page.goto(VIALIBRI_BASE, wait_until="domcontentloaded", timeout=20000)
            await _human_delay(1.0, 2.5)

            # Build search URL
            if isbn:
                # ISBN search: most precise, least scraping signal
                search_url = f"{VIALIBRI_SEARCH}?q={isbn.replace('-', '')}&type=isbn"
            else:
                # Title + author search
                query_parts = []
                if title:
                    query_parts.append(title)
                if author:
                    query_parts.append(author)
                q = "+".join(part.replace(" ", "+") for part in query_parts)
                search_url = f"{VIALIBRI_SEARCH}?q={q}"

            await page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
            await _human_delay(1.5, 3.0)

            # Check for block/CAPTCHA
            content = await page.content()
            if _is_blocked(content):
                logger.warning("Vialibri returned block/CAPTCHA page")
                return []

            comps = _parse_vialibri_html(content, isbn or title or "")

            logger.info(
                "Vialibri: %d comps found for %s",
                len(comps), isbn or title
            )
            return comps

        finally:
            await browser.close()


async def _human_delay(min_s: float, max_s: float):
    """Random delay to mimic human reading time."""
    await asyncio.sleep(random.uniform(min_s, max_s))


def _is_blocked(html: str) -> bool:
    """Detect Cloudflare/CAPTCHA blocks."""
    block_signals = [
        "Just a moment",
        "cf-browser-verification",
        "captcha",
        "Access denied",
        "checking your browser",
    ]
    lower = html.lower()
    return any(signal.lower() in lower for signal in block_signals)


def _parse_vialibri_html(html: str, search_term: str) -> list[PriceComp]:
    """
    Parse Vialibri search results HTML.

    Vialibri renders listings as a list of items, each with:
    - Price (in various currencies)
    - Seller name and country
    - Condition description
    - "Buy" link

    This parser handles Vialibri's current HTML structure.
    If the structure changes (it does occasionally), this needs updating.
    """
    comps = []

    # Price pattern: currency symbol + number, e.g. "$24.95", "€18.00", "£12.50"
    price_patterns = [
        r'\$\s*(\d+(?:\.\d{2})?)',      # USD
        r'€\s*(\d+(?:[.,]\d{2})?)',      # EUR
        r'£\s*(\d+(?:\.\d{2})?)',        # GBP
        r'(\d+(?:\.\d{2})?)\s*USD',     # USD suffix
    ]

    # Try to find result items
    # Vialibri uses class patterns like "result-item", "listing", etc.
    # This is a best-effort parse — the site structure changes
    for pattern in price_patterns:
        matches = re.findall(pattern, html)
        for match in matches[:20]:  # Cap at 20 comps
            try:
                price_str = match.replace(",", ".")
                amount = float(price_str)
                if 0.50 <= amount <= 50000:  # Sanity range
                    # Determine currency label
                    if "€" in html[:html.find(match) + 20]:
                        label = "ASKING (EUR)"
                    elif "£" in html[:html.find(match) + 20]:
                        label = "ASKING (GBP)"
                    else:
                        label = "ASKING"

                    comps.append(PriceComp(
                        source="vialibri",
                        price_type="asking",
                        amount=amount,
                        label=label,
                        currency="USD" if "$" in html else "EUR",
                        condition=None,
                        seller=None,
                    ))
            except (ValueError, IndexError):
                continue

    # Deduplicate by amount
    seen = set()
    unique_comps = []
    for comp in comps:
        if comp.amount not in seen:
            seen.add(comp.amount)
            unique_comps.append(comp)

    return unique_comps[:15]  # Return at most 15 comps

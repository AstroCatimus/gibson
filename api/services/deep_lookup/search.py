import asyncio
import httpx
from api.config import settings


# ── Query construction ────────────────────────────────────────────────────────

def build_queries(
    title: str,
    author: str,
    year: int | None,
    publisher: str | None,
) -> list[str]:
    base = f"{title} {author}"
    pub  = publisher or ""
    yr   = str(year) if year else ""

    return [
        f"{base} {yr} {pub} first edition".strip(),
        f"{base} first edition signed copy value auction realized",
        f"{base} first edition points identification bibliography",
    ]


# ── Serper API call ───────────────────────────────────────────────────────────

async def serper_search(query: str) -> list[dict]:
    """
    POST https://google.serper.dev/search
    Auth: X-API-KEY header
    Returns organic results only.
    """
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            resp = await client.post(
                "https://google.serper.dev/search",
                headers={
                    "X-API-KEY": settings.serper_api_key,
                    "Content-Type": "application/json",
                },
                json={"q": query, "num": 5},
            )
            data = resp.json()
            return data.get("organic", [])
        except Exception:
            return []


# ── Snippet categorization ────────────────────────────────────────────────────

PRICE_SIGNALS     = ["$", "£", "€", "sold", "realized", "asking", "estimate"]
EDITION_SIGNALS   = ["first edition", "first printing", "first thus", "points", "issue"]
CONDITION_SIGNALS = ["near fine", "very good", "fine", "dust jacket", " dj "]
AUCTION_DOMAINS   = ["heritage.com", "ha.com", "swanngalleries.com", "pbagalleries.com",
                     "christies.com", "sothebys.com", "bonhams.com"]
DEALER_DOMAINS    = ["abebooks.com", "biblio.com", "alibris.com", "vialibri.net",
                     "bookfinder.com", "bauman.com", "bromerbooks.com", "raptisrarebooks.com"]
SIG_DOMAINS       = [".edu", "loc.gov", "wikipedia.org", "britannica.com",
                     "poetryfoundation.org", "thelibrary.org"]
NOISE_DOMAINS     = ["amazon.com", "goodreads.com", "barnesandnoble.com",
                     "thriftbooks.com", "ebay.com", "walmart.com", "target.com"]


def categorize(result: dict) -> str:
    """Returns 'PRICE', 'SIGNIFICANCE', or 'NOISE'"""
    url     = result.get("link", "").lower()
    snippet = result.get("snippet", "").lower()

    if any(d in url for d in NOISE_DOMAINS):
        return "NOISE"

    has_price   = any(s in snippet for s in PRICE_SIGNALS)
    has_edition = any(s in snippet for s in EDITION_SIGNALS + CONDITION_SIGNALS)

    if has_price and has_edition:
        return "PRICE"
    if any(d in url for d in AUCTION_DOMAINS + DEALER_DOMAINS) and has_price:
        return "PRICE"
    if any(d in url for d in SIG_DOMAINS):
        return "SIGNIFICANCE"
    if any(w in snippet for w in ["author", "novelist", "award", "prize",
                                   "pulitzer", "nobel", "published", "poet"]):
        return "SIGNIFICANCE"

    return "NOISE"


# ── Full page fetch (auction houses only, max 2 per lookup) ──────────────────

def should_fetch_full(result: dict, category: str) -> bool:
    url = result.get("link", "").lower()
    return category == "PRICE" and any(d in url for d in AUCTION_DOMAINS)


async def fetch_relevant_section(url: str) -> str | None:
    """
    Fetch a full page and extract the relevant section.
    Hard cap: 800 tokens (~3,200 chars) of extracted text.
    Returns None on failure — do not retry.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": "Gibson/1.0 (Alexandria Book Co-op)"},
                follow_redirects=True,
            )
            if resp.status_code != 200:
                return None
            text = resp.text

            import re
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()

            # Return first 3200 chars — roughly 800 tokens
            return text[:3200]
    except Exception:
        return None


# ── Output formatter ──────────────────────────────────────────────────────────

def format_search_context(
    title: str,
    author: str,
    year: int | None,
    price_results: list[dict],
    significance_results: list[dict],
) -> str:
    """
    Build the structured context block passed to Sonnet.
    Hard cap: ~400 tokens.
    """
    lines = [
        f"SEARCH RESULTS: {title} by {author} ({year or 'year unknown'})",
        "",
    ]

    if price_results:
        lines.append("MARKET COMPS:")
        for r in price_results[:4]:
            snippet = r.get("snippet", "")[:140]
            date    = r.get("date", "date unknown")
            link    = r.get("link", "")
            try:
                domain = link.split("/")[2].replace("www.", "")
            except Exception:
                domain = "unknown"
            lines.append(f"- {snippet} ({domain}, {date})")
            lines.append(f"  {link}")
    else:
        lines.append("MARKET COMPS: None found — book may be rare or niche.")

    lines.append("")

    if significance_results:
        lines.append("AUTHOR/TITLE CONTEXT:")
        for r in significance_results[:2]:
            lines.append(f"- {r.get('snippet', '')[:140]}")
    else:
        lines.append("AUTHOR/TITLE CONTEXT: None found.")

    lines.append("")

    if len(price_results) >= 3:
        lines.append("DATA CONFIDENCE: HIGH")
    elif len(price_results) >= 1:
        lines.append("DATA CONFIDENCE: MEDIUM")
    else:
        lines.append("DATA CONFIDENCE: LOW — rely on training knowledge for rarity assessment")

    return "\n".join(lines)


# ── Orchestrator ──────────────────────────────────────────────────────────────

async def run_search(
    title: str,
    author: str,
    year: int | None,
    publisher: str | None,
) -> str:
    """
    Run all searches, categorize results, fetch auction pages if warranted.
    Returns formatted context string for Sonnet.
    """
    queries = build_queries(title, author, year, publisher)

    # Fire all 3 queries concurrently
    all_results = await asyncio.gather(*[serper_search(q) for q in queries])

    # Flatten and deduplicate by URL
    seen_urls = set()
    flat = []
    for batch in all_results:
        for r in batch:
            url = r.get("link", "")
            if url not in seen_urls:
                seen_urls.add(url)
                flat.append(r)

    # Categorize
    price_results = []
    sig_results   = []
    fetch_targets = []

    for r in flat:
        cat = categorize(r)
        if cat == "PRICE":
            price_results.append(r)
            if len(fetch_targets) < 2 and should_fetch_full(r, cat):
                fetch_targets.append(r)
        elif cat == "SIGNIFICANCE":
            sig_results.append(r)

    # Fetch full pages for top auction results (max 2)
    for r in fetch_targets:
        full_text = await fetch_relevant_section(r["link"])
        if full_text:
            r["snippet"] = full_text[:400]

    return format_search_context(title, author, year, price_results, sig_results)

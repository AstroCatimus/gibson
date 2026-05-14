"""
Gibson Research Agent — Claude-driven book identification and pricing.

Claude receives a book query and a set of tools. It decides what to look up,
runs up to MAX_TOOL_CALLS rounds, then returns a structured record with
per-field confidence scores.

Speed constraints baked in:
  - Each tool call: 5s hard timeout (returns empty on timeout, Claude moves on)
  - Parallel tool calls: when Claude requests multiple tools at once,
    they fire concurrently via asyncio.gather
  - Max 6 tool calls total before Claude is forced to synthesize
  - System prompt uses prompt caching — ~95% cache hit rate in steady state

Usage:
    from agent.research import run_research
    result = await run_research(isbn="9780060892999", title="A Canticle for Leibowitz")
"""

import asyncio
import json
import logging
import time
from typing import Optional

import anthropic
import httpx

from api.config import settings
from api.services.open_library import fetch_by_isbn, search_by_text
from api.services.pricing.booksrun import fetch_booksrun
from api.services.pricing.bookscouter import fetch_bookscouter

logger = logging.getLogger("gibson.agent.research")

MAX_TOOL_CALLS = 6
TOOL_TIMEOUT   = 5.0   # seconds per individual tool call

# ─── Tool definitions ────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "lookup_open_library_isbn",
        "description": (
            "Look up a book by ISBN in Open Library. Returns title, author, publisher, "
            "year, page count, cover image. Best first call when ISBN is known."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "isbn": {"type": "string", "description": "ISBN-10 or ISBN-13, digits only"}
            },
            "required": ["isbn"],
        },
    },
    {
        "name": "search_open_library_text",
        "description": (
            "Search Open Library by title and optional author. Use when no ISBN is available "
            "or ISBN lookup returned nothing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title":  {"type": "string"},
                "author": {"type": "string"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "lookup_google_books",
        "description": (
            "Search Google Books for bibliographic data. Broad coverage, good for "
            "post-1970 books. Accepts ISBN or title+author."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "isbn":   {"type": "string"},
                "title":  {"type": "string"},
                "author": {"type": "string"},
            },
        },
    },
    {
        "name": "lookup_loc",
        "description": (
            "Search the Library of Congress catalog. Most authoritative source for "
            "bibliographic data, especially pre-1970 and rare books. Use for publisher, "
            "edition statement, subjects, and year confirmation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "isbn":   {"type": "string"},
                "title":  {"type": "string"},
                "author": {"type": "string"},
            },
        },
    },
    {
        "name": "lookup_booksrun",
        "description": (
            "Get current buyback and resale pricing from BooksRun. Best for post-1990 "
            "ISBN books. Returns price range across multiple conditions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "isbn": {"type": "string", "description": "ISBN-13 required"}
            },
            "required": ["isbn"],
        },
    },
    {
        "name": "lookup_bookscouter",
        "description": (
            "Get trend pricing data from BookScouter across 30+ vendors. "
            "Returns price range labeled TREND."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "isbn": {"type": "string", "description": "ISBN-13 required"}
            },
            "required": ["isbn"],
        },
    },
]

# ─── System prompt (cached) ───────────────────────────────────────────────────

SYSTEM_PROMPT = """You are Gibson's bibliographic research engine for Alexandria Book Co-op.

Given a book query, use the available tools to find:
1. BIBLIOGRAPHIC DATA: title, author, publisher, year, edition statement, subjects, page count
2. PRICING DATA: current market value across multiple sources

SOURCE PRIORITY:
- Bibliographic: LOC (most authoritative) > Open Library > Google Books
- Pricing: BooksRun + BookScouter (call both if ISBN available)
- For pre-1970 or no-ISBN books: LOC is the first call, not the last

EFFICIENCY RULES:
- You have a maximum of 6 tool calls. Use them wisely.
- If ISBN is provided: call lookup_open_library_isbn AND lookup_booksrun in your first response (they run in parallel)
- If no ISBN: call search_open_library_text AND lookup_loc together
- Only call LOC if you need authoritative confirmation or the other sources were sparse
- Stop calling tools once you have title, author, year, publisher, and at least one pricing signal

OUTPUT: When you have enough data, return ONLY a JSON object in this exact schema:
{
  "title":             {"value": str,        "confidence": 0.0-1.0, "source": str},
  "author":            {"value": str,        "confidence": 0.0-1.0, "source": str},
  "publisher":         {"value": str|null,   "confidence": 0.0-1.0, "source": str},
  "year":              {"value": int|null,   "confidence": 0.0-1.0, "source": str},
  "isbn_13":           {"value": str|null,   "confidence": 0.0-1.0, "source": str},
  "edition_statement": {"value": str|null,   "confidence": 0.0-1.0, "source": str},
  "subjects":          {"value": [str],      "confidence": 0.0-1.0, "source": str},
  "page_count":        {"value": int|null,   "confidence": 0.0-1.0, "source": str},
  "pricing": {
    "suggested_price": float|null,
    "range_low":       float|null,
    "range_high":      float|null,
    "comp_count":      int,
    "sources":         [str]
  },
  "conflicts": [{"field": str, "values": [{"source": str, "value": any}]}],
  "overall_confidence": 0.0-1.0,
  "routing": "CONFIRM" | "REVIEW" | "GHOST_BOOK" | "NEEDS_RESEARCH"
}

Routing rules:
- CONFIRM:        overall_confidence >= 0.85, no major conflicts
- REVIEW:         0.60 <= overall_confidence < 0.85, or conflicts present
- GHOST_BOOK:     no institutional record found anywhere, pre-ISBN era
- NEEDS_RESEARCH: some data found but insufficient for pricing or edition confirmation

Honest uncertainty: if a source didn't provide a field, set confidence to 0. Never fabricate."""


# ─── Tool executors ──────────────────────────────────────────────────────────

async def _run_tool(name: str, inputs: dict) -> dict:
    """Execute a single tool with timeout. Returns result or error dict."""
    try:
        result = await asyncio.wait_for(_dispatch_tool(name, inputs), timeout=TOOL_TIMEOUT)
        return {"ok": True, "data": result}
    except asyncio.TimeoutError:
        logger.warning("Tool %s timed out after %.1fs", name, TOOL_TIMEOUT)
        return {"ok": False, "error": f"{name} timed out after {TOOL_TIMEOUT}s"}
    except Exception as e:
        logger.warning("Tool %s failed: %s", name, str(e))
        return {"ok": False, "error": str(e)}


async def _dispatch_tool(name: str, inputs: dict):
    """Route tool name to its implementation."""
    if name == "lookup_open_library_isbn":
        return await fetch_by_isbn(inputs["isbn"])

    if name == "search_open_library_text":
        return await search_by_text(inputs["title"], inputs.get("author"))

    if name == "lookup_google_books":
        return await _google_books(
            isbn=inputs.get("isbn"),
            title=inputs.get("title"),
            author=inputs.get("author"),
        )

    if name == "lookup_loc":
        return await _loc_catalog(
            isbn=inputs.get("isbn"),
            title=inputs.get("title"),
            author=inputs.get("author"),
        )

    if name == "lookup_booksrun":
        comps = await fetch_booksrun(isbn=inputs["isbn"])
        return [{"amount": c.amount, "label": c.label, "source": c.source} for c in comps]

    if name == "lookup_bookscouter":
        comps = await fetch_bookscouter(isbn=inputs["isbn"])
        return [{"amount": c.amount, "label": c.label, "source": c.source} for c in comps]

    return {"error": f"Unknown tool: {name}"}


# ─── Free external lookups ───────────────────────────────────────────────────

async def _google_books(
    isbn: Optional[str] = None,
    title: Optional[str] = None,
    author: Optional[str] = None,
) -> Optional[dict]:
    """Google Books API — no key required for basic searches."""
    if isbn:
        q = f"isbn:{isbn.replace('-', '')}"
    elif title:
        q = f"intitle:{title}"
        if author:
            q += f"+inauthor:{author}"
    else:
        return None

    try:
        async with httpx.AsyncClient(timeout=TOOL_TIMEOUT) as client:
            resp = await client.get(
                "https://www.googleapis.com/books/v1/volumes",
                params={"q": q, "maxResults": 3, "fields":
                        "items(volumeInfo(title,authors,publisher,publishedDate,"
                        "industryIdentifiers,pageCount,categories,subtitle))"},
            )
            if resp.status_code != 200:
                return None
            items = resp.json().get("items", [])
            if not items:
                return None
            info = items[0]["volumeInfo"]
            isbn13 = next(
                (i["identifier"] for i in info.get("industryIdentifiers", [])
                 if i["type"] == "ISBN_13"), None
            )
            return {
                "title":       info.get("title"),
                "subtitle":    info.get("subtitle"),
                "authors":     info.get("authors", []),
                "publisher":   info.get("publisher"),
                "year":        (info.get("publishedDate") or "")[:4] or None,
                "isbn_13":     isbn13,
                "page_count":  info.get("pageCount"),
                "subjects":    info.get("categories", []),
                "source":      "google_books",
                "confidence":  0.80,
            }
    except Exception as e:
        logger.debug("Google Books failed: %s", e)
        return None


async def _loc_catalog(
    isbn: Optional[str] = None,
    title: Optional[str] = None,
    author: Optional[str] = None,
) -> Optional[dict]:
    """Library of Congress catalog search — free, no key required."""
    if isbn:
        query = isbn.replace("-", "")
    elif title:
        query = f"{title} {author or ''}".strip()
    else:
        return None

    try:
        async with httpx.AsyncClient(timeout=TOOL_TIMEOUT) as client:
            resp = await client.get(
                "https://www.loc.gov/books/",
                params={"q": query, "fo": "json", "c": 3},
                headers={"User-Agent": "Gibson/1.0 (Alexandria Book Co-op)"},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            results = data.get("results", [])
            if not results:
                return None
            r = results[0]
            contributors = r.get("contributors", [])
            author_name = contributors[0].get("label") if contributors else None
            subjects = [s.get("label", "") for s in r.get("subjects", [])]
            return {
                "title":             r.get("title"),
                "author":            author_name,
                "publisher":         r.get("publisher"),
                "year":              r.get("date"),
                "edition_statement": r.get("edition"),
                "subjects":          subjects[:5],
                "url":               r.get("url"),
                "source":            "loc",
                "confidence":        0.90,
            }
    except Exception as e:
        logger.debug("LOC catalog search failed: %s", e)
        return None


# ─── Agent loop ───────────────────────────────────────────────────────────────

async def run_research(
    isbn:   Optional[str] = None,
    title:  Optional[str] = None,
    author: Optional[str] = None,
    year:   Optional[int] = None,
    model:  Optional[str] = None,
) -> dict:
    """
    Run the research agent for a single book.

    Returns a structured record with per-field confidence scores.
    Never raises — returns a NEEDS_RESEARCH record on total failure.
    """
    start = time.monotonic()
    model = model or settings.anthropic_research_model

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    # Build the initial user message
    query_parts = []
    if isbn:   query_parts.append(f"ISBN: {isbn}")
    if title:  query_parts.append(f"Title: {title}")
    if author: query_parts.append(f"Author: {author}")
    if year:   query_parts.append(f"Year: {year}")
    user_message = "Research this book:\n" + "\n".join(query_parts)

    messages = [{"role": "user", "content": user_message}]
    tool_calls_made = 0

    try:
        while tool_calls_made < MAX_TOOL_CALLS:
            response = await client.messages.create(
                model=model,
                max_tokens=2048,
                system=[{
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},  # prompt caching
                }],
                tools=TOOLS,
                messages=messages,
            )

            # Add assistant response to history
            messages.append({"role": "assistant", "content": response.content})

            # If Claude is done, parse the result
            if response.stop_reason == "end_turn":
                text = next(
                    (b.text for b in response.content if hasattr(b, "text")), ""
                )
                return _parse_result(text, tool_calls_made, time.monotonic() - start)

            # If Claude wants tools, execute them all in parallel
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            if not tool_use_blocks:
                break

            tool_calls_made += len(tool_use_blocks)

            # Fire all requested tools concurrently
            tasks = [_run_tool(b.name, b.input) for b in tool_use_blocks]
            results = await asyncio.gather(*tasks)

            # Return results to Claude
            tool_results = [
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result["data"] if result["ok"] else result, default=str),
                }
                for block, result in zip(tool_use_blocks, results)
            ]
            messages.append({"role": "user", "content": tool_results})

            logger.info(
                "Research: %d tool calls made (%s), continuing",
                tool_calls_made,
                ", ".join(b.name for b in tool_use_blocks),
            )

        # Hit the tool call cap — ask Claude to synthesize what it has
        messages.append({
            "role": "user",
            "content": "You have reached the tool call limit. Synthesize everything collected into the JSON output now."
        })
        final = await client.messages.create(
            model=model,
            max_tokens=2048,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            tools=TOOLS,
            messages=messages,
        )
        text = next((b.text for b in final.content if hasattr(b, "text")), "")
        return _parse_result(text, tool_calls_made, time.monotonic() - start)

    except Exception as e:
        logger.error("Research agent failed: %s", str(e))
        return _fallback(isbn, title, author, year, time.monotonic() - start)


def _parse_result(text: str, tool_calls_made: int, elapsed: float) -> dict:
    """Extract and validate the JSON result from Claude's response."""
    try:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        result = json.loads(text.strip())
        result["tool_calls_made"] = tool_calls_made
        result["elapsed_seconds"] = round(elapsed, 2)
        logger.info(
            "Research complete: confidence=%.2f routing=%s tools=%d elapsed=%.2fs",
            result.get("overall_confidence", 0),
            result.get("routing", "UNKNOWN"),
            tool_calls_made,
            elapsed,
        )
        return result
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("Failed to parse research result: %s", e)
        return _fallback(None, None, None, None, elapsed)


def _fallback(isbn, title, author, year, elapsed: float) -> dict:
    """Minimal record returned when the agent fails entirely."""
    return {
        "title":             {"value": title,  "confidence": 0.0, "source": "input"},
        "author":            {"value": author, "confidence": 0.0, "source": "input"},
        "publisher":         {"value": None,   "confidence": 0.0, "source": None},
        "year":              {"value": year,   "confidence": 0.0, "source": "input"},
        "isbn_13":           {"value": isbn,   "confidence": 0.0, "source": "input"},
        "edition_statement": {"value": None,   "confidence": 0.0, "source": None},
        "subjects":          {"value": [],     "confidence": 0.0, "source": None},
        "page_count":        {"value": None,   "confidence": 0.0, "source": None},
        "pricing": {
            "suggested_price": None,
            "range_low":       None,
            "range_high":      None,
            "comp_count":      0,
            "sources":         [],
        },
        "conflicts":          [],
        "overall_confidence": 0.0,
        "routing":            "NEEDS_RESEARCH",
        "tool_calls_made":    0,
        "elapsed_seconds":    round(elapsed, 2),
    }

"""
Gibson Ghost Book Agent — research pipeline for pre-ISBN / no-institutional-record material.

Ghost Books are items where:
- No ISBN exists
- No institutional catalog (LOC, WorldCat, etc.) has a record
- Standard identification pipeline returned no confident match

The Ghost Book agent runs specialized sources (zinecat, printed_matter, qzap,
factsheet_five) and attempts to build a minimal bibliographic record from
whatever evidence exists. Every Ghost Book gets a USBN computed from
title + author + year as printed.
"""

import asyncio
import hashlib
import logging
from typing import Any

from api.config import get_settings
from api.database import fetch, fetchrow, execute, get_pool
from agent.runner import load_cascade, resolve_source_list, run_phase
from agent.synthesis import synthesize
from agent.usbn import compute_usbn

logger = logging.getLogger("gibson.ghostbook")


async def process_ghost_book_queue(pool):
    """
    Process all items in the Ghost Book queue.

    Fetches unresolved ghost book records, runs specialized sources,
    attempts synthesis, and updates status.
    """
    cascade = load_cascade()
    items = await fetch(
        pool,
        """SELECT gbr.ghost_book_id, gbr.physical_description, gbr.ocr_text_raw,
                  gbr.cover_photo_url, gbr.research_status, gbr.estimated_year,
                  gbr.estimated_language, gbr.source_record
           FROM gibson_ghost_book_record gbr
           WHERE gbr.research_status IN ('QUEUED', 'RESEARCHING')
           ORDER BY gbr.created_at ASC
           LIMIT 50"""
    )

    logger.info("Ghost Book queue: %d items", len(items))

    for item in items:
        try:
            await process_single_ghost(dict(item), cascade, pool)
        except Exception as e:
            logger.error("Ghost Book %s failed: %s", item["ghost_book_id"], str(e))
            await execute(
                pool,
                """UPDATE gibson_ghost_book_record
                   SET research_status = 'ERROR', updated_at = NOW()
                   WHERE ghost_book_id = $1""",
                item["ghost_book_id"]
            )


async def process_single_ghost(item: dict, cascade: dict, pool):
    """
    Run the Ghost Book research pipeline for a single item.

    1. Extract what we can from OCR text and physical description
    2. Compute USBN from best-guess title/author/year
    3. Run specialized Ghost Book sources
    4. Run standard phase 3 sources as fallback
    5. Synthesize results
    6. Update record with findings
    """
    ghost_id = item["ghost_book_id"]
    logger.info("Processing Ghost Book %s", ghost_id)

    await execute(
        pool,
        "UPDATE gibson_ghost_book_record SET research_status = 'RESEARCHING', updated_at = NOW() WHERE ghost_book_id = $1",
        ghost_id
    )

    # Build query from whatever evidence we have
    query = _build_query_from_ghost(item)

    # Compute USBN if we have enough data
    usbn = None
    if query.get("title") and query.get("author"):
        usbn = compute_usbn(
            title=query["title"],
            author=query["author"],
            year=query.get("year")
        )
        query["usbn"] = usbn

    # Determine signals
    signals = ["pre_isbn"]
    if item.get("estimated_language", "").lower() == "german":
        signals.append("language_german")

    # Check if this looks like a zine
    description = (item.get("physical_description") or "").lower()
    if any(word in description for word in ("zine", "chapbook", "pamphlet", "stapled")):
        signals.append("format_zine")

    # Run Ghost Book specialized sources first
    ghost_sources = resolve_source_list(cascade, "phase_3", signals)
    results = {}

    phase_3_results = await run_phase(ghost_sources, cascade, query, pool)
    results["phase_3_ghost"] = phase_3_results

    # Log source hits
    for source_result in phase_3_results:
        if source_result.get("results"):
            await execute(
                pool,
                """INSERT INTO gibson_ghost_book_source_hit
                   (ghost_book_id, source_name, hit_type, raw_response, match_confidence)
                   VALUES ($1, $2, $3, $4::jsonb, $5)""",
                ghost_id,
                source_result["source"],
                "MATCH" if source_result["results"] else "NO_MATCH",
                "[]",  # Would serialize results in production
                _best_source_confidence(source_result)
            )

    # Synthesize whatever we found
    synthesis_result = await synthesize(results, query)

    # Update ghost book record
    new_status = "RESOLVED" if synthesis_result.get("overall_confidence", 0) > 0.6 else "UNRESOLVED"

    await execute(
        pool,
        """UPDATE gibson_ghost_book_record
           SET research_status = $2,
               usbn = $3,
               updated_at = NOW()
           WHERE ghost_book_id = $1""",
        ghost_id,
        new_status,
        usbn
    )

    logger.info(
        "Ghost Book %s → %s (confidence: %.2f, usbn: %s)",
        ghost_id, new_status,
        synthesis_result.get("overall_confidence", 0),
        usbn
    )


def _build_query_from_ghost(item: dict) -> dict:
    """Extract search parameters from Ghost Book record fields."""
    ocr_text = item.get("ocr_text_raw") or ""
    description = item.get("physical_description") or ""

    # Best-effort extraction from OCR text
    lines = [l.strip() for l in ocr_text.split("\n") if l.strip()]
    title = lines[0] if lines else None
    author = lines[1] if len(lines) > 1 else None

    return {
        "title": title,
        "author": author,
        "year": item.get("estimated_year"),
        "language": item.get("estimated_language"),
        "description": description,
        "ocr_text": ocr_text,
    }


def _best_source_confidence(source_result: dict) -> float:
    """Get the best confidence from a source result."""
    best = 0.0
    for r in source_result.get("results", []):
        conf = r.get("confidence", 0.0)
        if conf > best:
            best = conf
    return best


async def main():
    """Run the Ghost Book agent."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    pool = await get_pool()
    try:
        await process_ghost_book_queue(pool)
    finally:
        pass  # Pool managed by main app lifecycle


if __name__ == "__main__":
    asyncio.run(main())

"""
Gibson Agent Runner — overnight research and source cascade execution.

Loads source_cascade.yaml, resolves signal overrides for each item,
runs phases in order, stores results. Scheduled via cron at 2 AM.

Usage:
    python -m agent.runner                    # process full queue
    python -m agent.runner --item <uuid>      # single item
    python -m agent.runner --dry-run          # log plan without executing
"""

import asyncio
import importlib
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from api.config import settings
from api.database import init_pool, close_pool, get_pool, fetch, fetchrow, execute
from agent.synthesis import synthesize

logger = logging.getLogger("gibson.agent")

CASCADE_PATH = Path(__file__).parent / "source_cascade.yaml"


def load_cascade() -> dict:
    """Load and parse source_cascade.yaml."""
    with open(CASCADE_PATH) as f:
        return yaml.safe_load(f)


def resolve_source_list(cascade: dict, phase_key: str, signals: list[str]) -> list[str]:
    """
    Build the final source list for a phase, applying signal overrides.

    Signal overrides can prepend, append, or replace the default list.
    Prepend adds to front, append adds to end, replace swaps entirely.
    """
    default_key = f"{phase_key}_default" if not phase_key.endswith("_default") else phase_key
    base = list(cascade.get(default_key, cascade.get(phase_key, [])))

    for signal_name in signals:
        signal_config = cascade.get("signals", {}).get(signal_name, {})

        replace_key = f"{phase_key.replace('_default', '')}_replace"
        prepend_key = f"{phase_key.replace('_default', '')}_prepend"
        append_key = f"{phase_key.replace('_default', '')}_append"

        if replace_key in signal_config:
            base = list(signal_config[replace_key])
        if prepend_key in signal_config:
            prepend = list(signal_config[prepend_key])
            base = prepend + [s for s in base if s not in prepend]
        if append_key in signal_config:
            append_list = list(signal_config[append_key])
            base = base + [s for s in append_list if s not in base]

    return base


def detect_signals(item: dict) -> list[str]:
    """
    Detect which signal overrides apply based on item metadata.

    Examines language, date, genre, format, value signals, and special markers.
    """
    signals = []

    language = (item.get("language") or "").lower()
    if language == "german" or item.get("fraktur_detected"):
        signals.append("language_german")
    if language == "french":
        signals.append("language_french")
    if language == "latin":
        signals.append("language_latin")

    year = item.get("publication_year")
    if year:
        if year < 1501:
            signals.append("pre_1501")
        elif year < 1700:
            signals.append("pre_1700")
        elif year < 1800:
            signals.append("pre_1800")

    if not item.get("isbn_13"):
        signals.append("pre_isbn")

    genre = (item.get("genre") or "").lower()
    if genre in ("science fiction", "fantasy", "sf"):
        signals.append("genre_sf_fantasy")
    elif genre in ("mystery", "crime", "thriller", "detective"):
        signals.append("genre_mystery_crime")
    elif genre in ("poetry", "literary criticism", "literary"):
        signals.append("genre_poetry_literary")
    elif genre in ("children", "childrens", "juvenile"):
        signals.append("genre_childrens")

    book_format = (item.get("format") or "").lower()
    if book_format == "zine":
        signals.append("format_zine")
    elif book_format in ("academic", "scholarly"):
        signals.append("format_academic_scholarly")
    elif book_format in ("government", "government document"):
        signals.append("format_government_document")

    subject = (item.get("subject") or "").lower()
    if "music" in subject:
        signals.append("subject_music")

    if item.get("illustrated_plates"):
        signals.append("illustrated_plates")
    if item.get("signed") or item.get("inscribed"):
        signals.append("signed_inscribed")

    price_signal = item.get("price_signal", 0)
    if (year and year < 1900) or price_signal > 50:
        signals.append("auction_value_signal")

    return signals


def load_source_module(source_name: str, cascade: dict):
    """
    Dynamically load a source module from agent/sources/.

    Each source module must implement:
        async def search(query: dict, pool) -> list[dict]
    """
    source_def = cascade.get("sources", {}).get(source_name, {})
    filename = source_def.get("file", f"{source_name}.py")
    module_name = f"agent.sources.{filename.replace('.py', '')}"
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError:
        logger.warning("Source module not found: %s (expected %s)", source_name, module_name)
        return None


async def run_source(source_name: str, source_module, query: dict, pool) -> dict:
    """Run a single source with timeout and error handling."""
    start = time.monotonic()
    try:
        results = await asyncio.wait_for(
            source_module.search(query, pool),
            timeout=30.0
        )
        elapsed = time.monotonic() - start
        logger.info("Source %s returned %d results in %.2fs", source_name, len(results), elapsed)
        return {"source": source_name, "results": results, "elapsed": elapsed, "error": None}
    except asyncio.TimeoutError:
        logger.warning("Source %s timed out after 30s", source_name)
        return {"source": source_name, "results": [], "elapsed": 30.0, "error": "timeout"}
    except Exception as e:
        elapsed = time.monotonic() - start
        logger.error("Source %s failed: %s", source_name, str(e))
        return {"source": source_name, "results": [], "elapsed": elapsed, "error": str(e)}


async def run_phase(phase_sources: list[str], cascade: dict, query: dict, pool) -> list[dict]:
    """Run all sources in a phase concurrently."""
    tasks = []
    for source_name in phase_sources:
        module = load_source_module(source_name, cascade)
        if module:
            tasks.append(run_source(source_name, module, query, pool))
    if not tasks:
        return []
    return await asyncio.gather(*tasks)


async def process_item(item: dict, cascade: dict, pool, dry_run: bool = False) -> dict:
    """
    Run the full source cascade for a single research queue item.

    Phases run in order: 1 (local) → 2 (bulk local) → 3 (APIs) → 4 (pricing) → 5 (deep).
    Each phase can short-circuit if identification confidence exceeds threshold.
    Phase 4 fires only when identification clears 70%.
    """
    signals = detect_signals(item)
    logger.info("Item %s — signals: %s", item.get("stock_item_id", "?"), signals)

    query = {
        "isbn_13": item.get("isbn_13"),
        "isbn_10": item.get("isbn_10"),
        "title": item.get("title"),
        "author": item.get("author"),
        "publisher": item.get("publisher"),
        "year": item.get("publication_year"),
        "language": item.get("language"),
        "subject": item.get("subject"),
    }

    all_results = {}
    identification_confidence = 0.0

    # Phase 1: Local DB
    p1_sources = resolve_source_list(cascade, "phase_1", signals)
    if dry_run:
        logger.info("DRY RUN phase_1: %s", p1_sources)
    else:
        p1_results = await run_phase(p1_sources, cascade, query, pool)
        all_results["phase_1"] = p1_results
        identification_confidence = _best_confidence(p1_results)

    if identification_confidence >= 0.95:
        logger.info("High confidence after phase 1, skipping remaining phases")
        return all_results

    # Phase 2: Bulk local
    p2_sources = resolve_source_list(cascade, "phase_2", signals)
    if dry_run:
        logger.info("DRY RUN phase_2: %s", p2_sources)
    else:
        p2_results = await run_phase(p2_sources, cascade, query, pool)
        all_results["phase_2"] = p2_results
        identification_confidence = max(identification_confidence, _best_confidence(p2_results))

    if identification_confidence >= 0.90:
        logger.info("High confidence after phase 2, running pricing only")

    # Phase 3: External APIs
    p3_sources = resolve_source_list(cascade, "phase_3", signals)
    if dry_run:
        logger.info("DRY RUN phase_3: %s", p3_sources)
    else:
        p3_results = await run_phase(p3_sources, cascade, query, pool)
        all_results["phase_3"] = p3_results
        identification_confidence = max(identification_confidence, _best_confidence(p3_results))

    # Phase 4: Pricing (only fires when identification > 70%)
    if identification_confidence >= 0.70:
        p4_sources = resolve_source_list(cascade, "phase_4_pricing", signals)
        if dry_run:
            logger.info("DRY RUN phase_4: %s", p4_sources)
        else:
            p4_results = await run_phase(p4_sources, cascade, query, pool)
            all_results["phase_4"] = p4_results
    else:
        logger.info("Identification confidence %.2f < 0.70, skipping pricing phase", identification_confidence)

    # Phase 5: Overnight deep research
    p5_sources = resolve_source_list(cascade, "phase_5", signals)
    if dry_run:
        logger.info("DRY RUN phase_5: %s", p5_sources)
    else:
        p5_results = await run_phase(p5_sources, cascade, query, pool)
        all_results["phase_5"] = p5_results

    # Synthesis — Claude Haiku merges all results into a single authoritative record.
    # Only runs if we actually fetched results (not dry-run, not empty).
    if not dry_run and any(all_results.values()):
        try:
            synthesis_result = await synthesize(all_results, query)
            all_results["synthesis"] = synthesis_result
            logger.info(
                "Item %s synthesis: confidence=%.2f routing=%s",
                item.get("stock_item_id", "?"),
                synthesis_result.get("overall_confidence", 0),
                synthesis_result.get("routing_recommendation", "UNKNOWN"),
            )
        except Exception as e:
            logger.error("Synthesis failed for item %s: %s", item.get("stock_item_id", "?"), str(e))

    return all_results


def _best_confidence(phase_results: list[dict]) -> float:
    """Extract the best identification confidence from a phase's results."""
    best = 0.0
    for result in phase_results:
        for r in result.get("results", []):
            conf = r.get("confidence", 0.0)
            if conf > best:
                best = conf
    return best


async def store_results(item_id: str, results: dict):
    """Persist research results back to the database."""
    import json
    await execute(
        """UPDATE gibson_stock_item
           SET research_results = $2::jsonb,
               research_completed_at = NOW(),
               status = CASE
                   WHEN status = 'PENDING_IDENTIFICATION' THEN 'PRICING_RESEARCH'
                   ELSE status
               END
           WHERE stock_item_id = $1""",
        item_id,
        json.dumps(results, default=str),
    )


async def get_research_queue() -> list[dict]:
    """Fetch items waiting for overnight research."""
    rows = await fetch(
        """SELECT si.stock_item_id, si.isbn_13, si.status,
                  w.title, w.language,
                  ea.name as author,
                  e.publication_year, e.publisher_name
           FROM gibson_stock_item si
           LEFT JOIN gibson_edition e ON si.edition_id = e.edition_id
           LEFT JOIN gibson_work w ON e.work_id = w.work_id
           LEFT JOIN gibson_edition_agent ea_j ON e.edition_id = ea_j.edition_id
           LEFT JOIN gibson_agent ea ON ea_j.agent_id = ea.agent_id AND ea_j.role = 'author'
           WHERE si.status IN ('PENDING_IDENTIFICATION', 'NEEDS_RESEARCH')
           ORDER BY si.created_at ASC
           LIMIT 200"""
    )
    return [dict(r) for r in rows]


async def main(item_id: str | None = None, dry_run: bool = False):
    """Main entry point for the agent runner."""
    await init_pool()
    pool = get_pool()   # pool passed to source modules which use pool.fetch() directly
    cascade = load_cascade()

    try:
        if item_id:
            row = await fetchrow(
                """SELECT si.stock_item_id, si.edition_id, si.store_id,
                          si.gibson_sku, si.status, si.condition_grade,
                          si.asking_price, si.trust_tier,
                          si.shelf_verification_status, si.research_results,
                          e.isbn_13, e.isbn_10, e.publication_year,
                          w.title, w.language,
                          a.name_display as author
                   FROM gibson_stock_item si
                   LEFT JOIN gibson_edition e ON si.edition_id = e.edition_id
                   LEFT JOIN gibson_work w ON e.work_id = w.work_id
                   LEFT JOIN gibson_work_agent wa ON w.work_id = wa.work_id AND wa.role = 'author'
                   LEFT JOIN gibson_agent a ON wa.agent_id = a.agent_id
                   WHERE si.stock_item_id = $1""",
                item_id
            )
            if not row:
                logger.error("Item %s not found", item_id)
                return
            items = [dict(row)]
        else:
            items = await get_research_queue()

        logger.info("Processing %d items", len(items))
        for item in items:
            results = await process_item(item, cascade, pool, dry_run=dry_run)
            if not dry_run:
                await store_results(str(item["stock_item_id"]), results)
            logger.info("Completed item %s", item.get("stock_item_id"))

    finally:
        await close_pool()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Gibson overnight research agent")
    parser.add_argument("--item", help="Process a single stock_item_id")
    parser.add_argument("--dry-run", action="store_true", help="Log plan without executing")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    asyncio.run(main(item_id=args.item, dry_run=args.dry_run))

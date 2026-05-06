"""
Gibson Synthesis — Claude Haiku merges multi-source results into a single record.

Takes raw results from the source cascade runner and produces a unified
bibliographic record with confidence scores on every field. This is the
last step before a record enters the review queue or auto-confirms.
"""

import json
import logging
from typing import Any

import anthropic

from api.config import settings

logger = logging.getLogger("gibson.synthesis")

SYNTHESIS_SYSTEM_PROMPT = """You are Gibson's bibliographic synthesis engine.

You receive raw search results from multiple bibliographic and pricing sources
for a single book. Your job: merge them into one authoritative record.

Rules:
1. Every field gets a confidence score 0.00-1.00.
2. When sources agree, confidence is high. When they conflict, note the conflict.
3. Prefer institutional sources (LOC, DNB, BNF) over commercial sources for bibliographic data.
4. Prefer auction realized prices (SOLD) over asking prices for pricing.
5. Never fabricate data. If no source provides a field, set it to null with confidence 0.
6. Flag anything that looks like a Ghost Book candidate (pre-ISBN, no institutional record).
7. Output valid JSON matching the schema exactly.

Output schema:
{
  "title": {"value": str, "confidence": float, "sources": [str]},
  "author": {"value": str, "confidence": float, "sources": [str]},
  "publisher": {"value": str | null, "confidence": float, "sources": [str]},
  "publication_year": {"value": int | null, "confidence": float, "sources": [str]},
  "isbn_13": {"value": str | null, "confidence": float, "sources": [str]},
  "language": {"value": str, "confidence": float, "sources": [str]},
  "edition_statement": {"value": str | null, "confidence": float, "sources": [str]},
  "page_count": {"value": int | null, "confidence": float, "sources": [str]},
  "subjects": {"value": [str], "confidence": float, "sources": [str]},
  "suggested_section": {"value": str, "confidence": float},
  "pricing": {
    "suggested_price": float | null,
    "price_range_low": float | null,
    "price_range_high": float | null,
    "vialibri_has_comps": bool,
    "comp_count": int,
    "sources_used": [str]
  },
  "conflicts": [{"field": str, "values": [{"source": str, "value": any}]}],
  "ghost_book_candidate": bool,
  "overall_confidence": float,
  "routing_recommendation": "CONFIRM" | "REVIEW" | "GHOST_BOOK" | "NEEDS_RESEARCH"
}"""


async def synthesize(source_results: dict[str, list[dict]], original_query: dict) -> dict:
    """
    Merge multi-source results into a single bibliographic record via Claude Haiku.

    Args:
        source_results: Phase-keyed dict of source results from the runner.
        original_query: The original search query (ISBN, title, author, etc.)

    Returns:
        Synthesized record with per-field confidence scores.
    """
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    # Flatten results for the prompt
    flat_results = []
    for phase, phase_results in source_results.items():
        for source_result in phase_results:
            source_name = source_result.get("source", "unknown")
            for record in source_result.get("results", []):
                flat_results.append({"source": source_name, "phase": phase, **record})

    user_message = f"""Original query: {json.dumps(original_query)}

Source results ({len(flat_results)} records from {len(source_results)} phases):
{json.dumps(flat_results, indent=2, default=str)}

Synthesize into a single authoritative record."""

    try:
        response = await client.messages.create(
            model=settings.anthropic_synthesis_model,
            max_tokens=2000,
            system=SYNTHESIS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}]
        )

        text = response.content[0].text
        # Extract JSON from response
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        result = json.loads(text.strip())
        logger.info(
            "Synthesis complete: confidence=%.2f routing=%s",
            result.get("overall_confidence", 0),
            result.get("routing_recommendation", "UNKNOWN")
        )
        return result

    except json.JSONDecodeError as e:
        logger.error("Failed to parse synthesis response: %s", str(e))
        return _fallback_synthesis(flat_results, original_query)
    except Exception as e:
        logger.error("Synthesis API call failed: %s", str(e))
        return _fallback_synthesis(flat_results, original_query)


def _fallback_synthesis(flat_results: list[dict], query: dict) -> dict:
    """
    Rule-based fallback when Claude is unavailable.

    Picks the most common value for each field across sources.
    Crude but keeps the pipeline moving.
    """
    from collections import Counter

    def most_common(field: str) -> tuple[Any, float]:
        values = [r.get(field) for r in flat_results if r.get(field)]
        if not values:
            return None, 0.0
        counter = Counter(str(v) for v in values)
        best_val, count = counter.most_common(1)[0]
        confidence = count / len(values) if values else 0.0
        # Try to return original type
        for r in flat_results:
            if str(r.get(field)) == best_val:
                return r[field], confidence
        return best_val, confidence

    title_val, title_conf = most_common("title")
    author_val, author_conf = most_common("author")
    publisher_val, publisher_conf = most_common("publisher")
    year_val, year_conf = most_common("publication_year")
    isbn_val, isbn_conf = most_common("isbn_13")

    has_any_result = any(r for r in flat_results)

    return {
        "title": {"value": title_val or query.get("title"), "confidence": title_conf, "sources": []},
        "author": {"value": author_val or query.get("author"), "confidence": author_conf, "sources": []},
        "publisher": {"value": publisher_val, "confidence": publisher_conf, "sources": []},
        "publication_year": {"value": year_val, "confidence": year_conf, "sources": []},
        "isbn_13": {"value": isbn_val or query.get("isbn_13"), "confidence": isbn_conf, "sources": []},
        "language": {"value": "en", "confidence": 0.5, "sources": []},
        "edition_statement": {"value": None, "confidence": 0.0, "sources": []},
        "page_count": {"value": None, "confidence": 0.0, "sources": []},
        "subjects": {"value": [], "confidence": 0.0, "sources": []},
        "suggested_section": {"value": "", "confidence": 0.0},
        "pricing": {
            "suggested_price": None,
            "price_range_low": None,
            "price_range_high": None,
            "vialibri_has_comps": False,
            "comp_count": 0,
            "sources_used": []
        },
        "conflicts": [],
        "ghost_book_candidate": not has_any_result and not isbn_val,
        "overall_confidence": max(title_conf, author_conf) * 0.8,
        "routing_recommendation": "REVIEW" if has_any_result else "GHOST_BOOK"
    }

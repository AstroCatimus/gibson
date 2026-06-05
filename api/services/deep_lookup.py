"""
Gibson deep lookup service — three-stage rare book assessment.

Stage 1: Rule-based trigger (free — pure logic, no Claude)
Stage 2: Sonnet metadata-only triage (cheap — no tools, no images, ~600 tokens)
Stage 3: Sonnet full lookup (expensive — web search + images, ~3000–6000 tokens)

Only Stage 3 spends real money. It only runs when Stage 1 AND Stage 2 both flag
the book as potentially collectible.

Research notes:
- Every edition point claim must cite a source URL or be marked unverified
- Signature transcription is OK; authentication is not — disclaimer is non-suppressible
- Dust jacket presence/absence is often 75-90% of value for pre-1970 books
- Hallucination risk is highest for regional/small-press/specialty titles
- Web search tool: {"type": "web_search_20260209"} in tools array
"""

import json
import logging
from typing import Optional

from api.config import settings
from api.models.identification import DeepLookupResult, DeepLookupSource

logger = logging.getLogger("gibson.deep_lookup")


# ── Stage 1: Rule-based trigger ───────────────────────────────────────────────

def should_suggest(
    title: Optional[str],
    author: Optional[str],
    publisher: Optional[str],
    publication_year: Optional[int],
    isbn_13: Optional[str],
    format_: Optional[str],
    suggested_price: Optional[float],
    price_range_high: Optional[float],
    has_pricing_comps: bool,
    identification_confidence: float,
) -> dict:
    """
    Pure logic — no Claude calls. Returns {suggest: bool, reason: str}.
    Fast enough to run on every identification result.
    """
    year = publication_year
    fmt  = (format_ or "").lower()

    # Hard exclusions — never suggest
    if "mass_market" in fmt or fmt == "mmpb":
        return {"suggest": False, "reason": ""}
    if identification_confidence < 0.60:
        return {"suggest": False, "reason": ""}

    reasons = []

    # Hard signals — any one is sufficient
    if not isbn_13 and year and year < 1975:
        reasons.append(f"pre-ISBN era ({year})")

    if year and year < 1960:
        reasons.append(f"published {year}")

    if (
        suggested_price
        and price_range_high
        and price_range_high > suggested_price * 2.5
    ):
        ratio = round(price_range_high / suggested_price, 1)
        reasons.append(f"market high is {ratio}× Gibson's suggestion")

    if not has_pricing_comps and year and year < 1985:
        reasons.append("no market comps found")

    if reasons:
        return {"suggest": True, "reason": " · ".join(reasons[:3])}

    # Soft signals — need at least 2
    soft = []
    if year and year < 1980:
        soft.append(f"pre-1980 ({year})")
    if "hardcover" in fmt and year and year < 1985:
        soft.append("hardcover")
    if not isbn_13 and year and year < 1985:
        soft.append("no ISBN")
    if year and year > 1990 and not has_pricing_comps:
        soft.append("no comps")

    if len(soft) >= 2:
        return {"suggest": True, "reason": " · ".join(soft[:3])}

    return {"suggest": False, "reason": ""}


# ── Stage 2: Sonnet metadata triage ───────────────────────────────────────────

async def triage(
    title: Optional[str],
    author: Optional[str],
    publisher: Optional[str],
    year: Optional[int],
    isbn: Optional[str],
) -> dict:
    """
    Sonnet judges collectibility from metadata alone.
    No tools, no images — fast and cheap (~600 tokens).
    Returns {proceed: bool, confidence: str, reason: str}.
    """
    if not settings.anthropic_api_key:
        return {"proceed": True, "confidence": "low", "reason": "API not configured — defaulting to full lookup"}

    import anthropic
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    prompt = f"""You are a rare book specialist with deep knowledge of 20th-century literary firsts, collectible publishers, and author significance.

Based only on the bibliographic metadata below, make a quick yes/no judgment on whether this book is potentially collectible or significantly more valuable than a common used copy.

Title: {title or "Unknown"}
Author: {author or "Unknown"}
Publisher: {publisher or "Unknown"}
Year: {year or "Unknown"}
ISBN: {isbn if isbn else "None (pre-ISBN era)"}

Return ONLY a JSON object — no other text:
{{
  "proceed": true or false,
  "confidence": "high", "medium", or "low",
  "reason": "one sentence explaining the decision"
}}

Guidelines:
- Return true if: the author has won major literary prizes, the publisher is a known collectible imprint (Black Sparrow, City Lights, New Directions, etc.), the author's first editions are actively collected, or the title is known to have valuable variants
- Return false if: you are confident this is a common mass-market title with large print runs and no collectible interest
- When genuinely uncertain, return true with confidence "low" — missing a valuable book costs more than an extra lookup
- Do NOT fabricate specific edition points or prices — just judge collectibility potential"""

    try:
        response = await client.messages.create(
            model=settings.anthropic_vision_escalation_model,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        result = json.loads(text)
        logger.info(
            "Deep lookup triage: proceed=%s confidence=%s reason=%s",
            result.get("proceed"), result.get("confidence"), result.get("reason"),
        )
        return result
    except Exception as e:
        logger.warning("Triage failed: %s — defaulting to proceed", e)
        return {"proceed": True, "confidence": "low", "reason": "Triage error — running full lookup"}


# ── Stage 3: Sonnet full deep lookup ──────────────────────────────────────────

_SYSTEM = """You are a rare book specialist helping a used bookstore dealer assess a book's collectibility and value.

CRITICAL RULES — follow these exactly:
1. Every factual claim about edition points, auction prices, or bibliographic details MUST be grounded in:
   a) A web search result you retrieve (cite the URL in source_url fields)
   b) Something directly visible in provided photographs (cite as "visible in photo")
   c) If from training knowledge only, it MUST go in the "unverified_claims" list and be marked "UNVERIFIED — confirm physically"
2. NEVER fabricate edition points, specific auction prices, or bibliographic data
3. For signatures/inscriptions: transcribe what you can read, describe the type, but ALWAYS include the authentication note
4. Dust jacket value: always quantify the DJ premium when relevant to the value assessment
5. When uncertain about anything, say so — a conservative accurate assessment is more useful than a confident wrong one
6. Think through the evidence step by step before producing your final JSON

Use web search to research:
- Auction realized prices (Heritage Auctions, Swann Galleries, PBA Galleries)
- Current asking prices (AbeBooks collector listings, Vialibri)
- Edition identification guides and first edition points for this specific title
- Author's awards, significance, and bibliographic importance
- Publisher significance if small/independent press"""

_SCHEMA_PROMPT = """After your research, return ONLY a valid JSON object matching this schema exactly.
No prose before or after the JSON.

{
  "significance_score": <float 0.0-1.0>,
  "significance_summary": "<2-3 sentences summarising what makes this notable, or why it is not>",
  "edition_assessment": {
    "printing": "<first|later|unknown>",
    "evidence": ["<specific observable evidence from photos or cited sources>"],
    "confidence": "<high|medium|low>",
    "source_url": "<URL or null>",
    "points_to_check": ["<specific physical inspection item for dealer to verify>"]
  },
  "author_significance": {
    "summary": "<one sentence or null>",
    "awards": ["<award name and year>"],
    "source_url": "<URL or null>"
  },
  "market_value": {
    "assessed_low": <float or null>,
    "assessed_high": <float or null>,
    "reasoning": "<one sentence citing source>",
    "with_dj": "<range string e.g. '$120-200' or null>",
    "without_dj": "<range string e.g. '$15-25' or null>",
    "source_url": "<URL or null>"
  },
  "signature_inscription": {
    "detected": <true|false>,
    "transcription": "<text or null>",
    "type": "<signed|inscribed|association|bookplate|facsimile|null>"
  },
  "sources": [
    {"title": "<source name>", "url": "<URL>", "reasoning": "<one line: what this source contributed>"}
  ],
  "unverified_claims": ["<any claim from training data without a web search citation>"],
  "photo_request": {
    "needed": <true|false>,
    "page": "<specific page or section e.g. 'Page 57' or 'Copyright page' or null>",
    "reason": "<exactly why this page would confirm or change the assessment, or null>"
  }
}"""


async def run_deep_lookup(
    title: Optional[str],
    author: Optional[str],
    publisher: Optional[str],
    year: Optional[int],
    isbn: Optional[str],
    images: list[str],           # base64 images already available
    additional_image: Optional[str] = None,  # extra page requested by Claude
) -> DeepLookupResult:
    """
    Stage 3: Full deep lookup with web search and image analysis.
    Expensive — only call after Stage 1 + Stage 2 both cleared.
    """
    if not settings.anthropic_api_key:
        return DeepLookupResult(
            triage_proceed=True,
            triage_reason="",
            significance_summary="API not configured.",
        )

    import anthropic
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    # Build image content blocks
    content = []
    all_images = list(images)
    if additional_image:
        all_images.append(additional_image)

    image_labels = ["Front cover", "Title page", "Copyright page"]
    for i, img_b64 in enumerate(all_images):
        label = image_labels[i] if i < len(image_labels) else f"Additional page {i - len(image_labels) + 1}"
        content.append({
            "type": "text",
            "text": f"[Image {i+1}: {label}]",
        })
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": img_b64,
            },
        })

    # Build the user prompt
    meta_lines = [
        f"Title: {title or 'Unknown'}",
        f"Author: {author or 'Unknown'}",
        f"Publisher: {publisher or 'Unknown'}",
        f"Year: {year or 'Unknown'}",
        f"ISBN: {isbn if isbn else 'None (pre-ISBN era)'}",
    ]
    if not all_images:
        meta_lines.append("\nNote: No photographs available — base assessment on web research only.")
    elif additional_image:
        meta_lines.append(f"\nNote: {len(all_images)} images provided including a dealer-supplied additional page.")
    else:
        meta_lines.append(f"\nNote: {len(all_images)} standard scan image(s) provided (cover, title page, copyright page).")

    content.append({
        "type": "text",
        "text": "\n".join(meta_lines) + "\n\n" + _SCHEMA_PROMPT,
    })

    try:
        logger.info(
            "Deep lookup Stage 3: %r by %r (%s) — %d images",
            title, author, year, len(all_images),
        )
        response = await client.messages.create(
            model=settings.anthropic_vision_escalation_model,
            max_tokens=4096,
            system=_SYSTEM,
            tools=[{"type": "web_search_20260209"}],
            messages=[{"role": "user", "content": content}],
        )

        # Extract text from response — may contain multiple content blocks
        # (tool_use, tool_result, and text blocks from web search iterations)
        text_parts = []
        for block in response.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
            elif isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block["text"])

        raw = "\n".join(text_parts).strip()

        # Extract JSON
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0]
        # Find the outermost JSON object
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start >= 0 and end > start:
            raw = raw[start:end]

        data = json.loads(raw)
        return _parse_result(data)

    except json.JSONDecodeError as e:
        logger.error("Deep lookup JSON parse failed: %s", e)
        return DeepLookupResult(
            triage_proceed=True,
            triage_reason="",
            significance_summary="Deep lookup completed but result could not be parsed.",
            unverified_claims=["Result parsing failed — run again or check manually."],
        )
    except Exception as e:
        logger.error("Deep lookup Stage 3 failed: %s", e)
        return DeepLookupResult(
            triage_proceed=True,
            triage_reason="",
            significance_summary=f"Deep lookup failed: {str(e)[:100]}",
        )


def _parse_result(data: dict) -> DeepLookupResult:
    """Parse Claude's JSON response into a DeepLookupResult."""
    ea  = data.get("edition_assessment") or {}
    ai  = data.get("author_significance") or {}
    mv  = data.get("market_value") or {}
    sig = data.get("signature_inscription") or {}
    pr  = data.get("photo_request") or {}

    sources = [
        DeepLookupSource(
            title=s.get("title", ""),
            url=s.get("url"),
            reasoning=s.get("reasoning", ""),
        )
        for s in (data.get("sources") or [])
    ]

    return DeepLookupResult(
        triage_proceed=True,
        significance_score=float(data.get("significance_score") or 0),
        significance_summary=data.get("significance_summary"),

        edition_printing=ea.get("printing", "unknown"),
        edition_evidence=ea.get("evidence") or [],
        edition_confidence=ea.get("confidence", "low"),
        edition_source_url=ea.get("source_url"),
        points_to_check=ea.get("points_to_check") or [],

        author_significance=ai.get("summary"),
        author_awards=ai.get("awards") or [],
        author_source_url=ai.get("source_url"),

        assessed_value_low=_to_float(mv.get("assessed_low")),
        assessed_value_high=_to_float(mv.get("assessed_high")),
        assessed_value_reasoning=mv.get("reasoning"),
        value_with_dj=mv.get("with_dj"),
        value_without_dj=mv.get("without_dj"),
        value_source_url=mv.get("source_url"),

        signature_detected=bool(sig.get("detected")),
        signature_transcription=sig.get("transcription"),
        signature_type=sig.get("type"),

        sources=sources,
        unverified_claims=data.get("unverified_claims") or [],

        needs_photo=bool(pr.get("needed")),
        photo_request_page=pr.get("page"),
        photo_request_reason=pr.get("reason"),
    )


def _to_float(val) -> Optional[float]:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


# ── Save findings to stock item ───────────────────────────────────────────────

async def save_to_stock_item(stock_item_id: str, result: DeepLookupResult):
    """
    Write deep lookup findings back to the stock item.
    - Appends to condition_notes (never overwrites dealer text)
    - Sets is_signed / is_inscribed if confirmed
    Never called automatically — only when dealer explicitly saves.
    """
    from api.database import fetchrow, execute

    row = await fetchrow(
        "SELECT condition_notes, is_signed, is_inscribed FROM gibson_stock_item WHERE stock_item_id = $1",
        stock_item_id,
    )
    if not row:
        return

    # Build the note to append
    note_parts = []

    if result.edition_printing == "first" and result.edition_confidence in ("high", "medium"):
        note_parts.append(f"Likely first edition/printing ({result.edition_confidence} confidence).")

    if result.signature_detected and result.signature_transcription:
        sig_type = result.signature_type or "inscription"
        note_parts.append(f"{sig_type.capitalize()}: \"{result.signature_transcription}\".")

    if result.significance_summary:
        note_parts.append(result.significance_summary)

    if result.unverified_claims:
        note_parts.append("Note: some details unverified — confirm physically.")

    new_note = " ".join(note_parts)
    existing = (row["condition_notes"] or "").strip()
    if existing and new_note:
        combined = f"{existing} {new_note}"
    else:
        combined = new_note or existing

    updates = {"condition_notes": combined or None}
    if result.signature_detected:
        if result.signature_type in ("signed",):
            updates["is_signed"] = True
        elif result.signature_type in ("inscribed", "association"):
            updates["is_inscribed"] = True

    set_clauses = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(updates))
    values = list(updates.values())

    await execute(
        f"UPDATE gibson_stock_item SET {set_clauses}, updated_at = now() WHERE stock_item_id = $1",
        stock_item_id, *values,
    )
    logger.info("Saved deep lookup findings to stock item %s", stock_item_id)

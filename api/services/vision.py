"""
Gibson vision service.
Claude Vision with OCR text — hybrid always.
Image + OCR text always sent together. Architectural invariant.
Never image alone, never OCR alone.

Model strategy:
  - Primary: Haiku (fast, cheap — handles most clear covers)
  - Escalation: Sonnet (only when Haiku confidence < vision_escalation_threshold)
  Most scans will never touch Sonnet.
"""

import base64
import logging
import time
from typing import Optional
from uuid import UUID, uuid4

from api.config import settings
from api.models.identification import IdentificationResult, VisionExtractionResult

logger = logging.getLogger("gibson.vision")


async def identify_from_image(
    image_base64: str,
    additional_images: list[str] = [],
) -> IdentificationResult:
    """
    Standard Path identification from cover photo.
    1. Run OCR ensemble (EasyOCR + PaddleOCR)
    2. Send image + OCR text to Claude Vision (Sonnet)
    3. Return structured JSON with per-field confidence
    """
    start = time.time()

    # Claude Vision reads the cover directly — no OCR pre-processing needed
    extraction = await call_claude_vision(
        image_base64=image_base64,
        additional_images=additional_images,
    )

    # Escalate to Sonnet if Haiku didn't clear the threshold
    if (
        extraction.overall_confidence < settings.vision_escalation_threshold
        and settings.anthropic_vision_escalation_model != settings.anthropic_vision_model
    ):
        logger.info("Escalating to Sonnet (confidence=%.2f)", extraction.overall_confidence)
        extraction = await call_claude_vision(
            image_base64=image_base64,
            additional_images=additional_images,
            model_override=settings.anthropic_vision_escalation_model,
        )

    # Step 3: Cross-reference with Open Library to fill gaps and confirm
    from api.services.open_library import fetch_by_isbn, search_by_text

    ol = None
    if extraction.isbn:
        ol = await fetch_by_isbn(extraction.isbn)
    if not ol and extraction.title and extraction.author:
        ol = await search_by_text(extraction.title, extraction.author)

    if ol:
        ol_authors = ol.get("authors") or []
        # Fill any fields Claude missed
        title    = extraction.title    or ol.get("title")
        author   = extraction.author   or (ol_authors[0] if ol_authors else None)
        publisher = extraction.publisher or ol.get("publisher")
        pub_year = extraction.publication_year
        if not pub_year:
            import re as _re
            pub_date = ol.get("published_date") or ""
            m = _re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", pub_date)
            pub_year = int(m.group(1)) if m else None
        isbn     = extraction.isbn or ol.get("isbn")
        cover_url = ol.get("cover_image_url") or None
        # OL confirmation bumps confidence slightly when it agrees on title
        ol_agrees = ol.get("title", "").lower().strip() == (extraction.title or "").lower().strip()
        confidence = min(1.0, extraction.overall_confidence + (0.05 if ol_agrees else 0.0))
    else:
        title     = extraction.title
        author    = extraction.author
        publisher = extraction.publisher
        pub_year  = extraction.publication_year
        isbn      = extraction.isbn
        cover_url = None
        confidence = extraction.overall_confidence

    elapsed = int((time.time() - start) * 1000)

    follow_up = None
    if confidence < 0.85 and confidence >= 0.50:
        follow_up = _determine_follow_up(extraction)

    return IdentificationResult(
        path="standard_path",
        title=title,
        author=author,
        publisher=publisher,
        publication_year=pub_year,
        isbn_13=isbn,
        format=extraction.format,
        confidence=confidence,
        per_field_confidence={
            "title": extraction.title_confidence,
            "author": extraction.author_confidence,
            "publisher": extraction.publisher_confidence,
            "year": extraction.year_confidence,
        },
        follow_up_needed=follow_up is not None,
        follow_up_request=follow_up,
        routing_decision="confirm" if confidence >= 0.85 else "follow_up",
        cover_image_url=cover_url,
        needs_cover_photo=not bool(cover_url),
    )


async def call_claude_vision(
    image_base64: str,
    additional_images: list[str] = [],
    model_override: Optional[str] = None,
) -> VisionExtractionResult:
    """
    Call Claude Vision with image + OCR text.
    Defaults to the configured vision model (Haiku).
    Pass model_override=settings.anthropic_vision_escalation_model for Sonnet escalation.
    Returns structured bibliographic extraction.
    """
    if not settings.anthropic_api_key:
        return VisionExtractionResult(
            title="[Vision API not configured]",
            overall_confidence=0.0,
        )

    model = model_override or settings.anthropic_vision_model

    try:
        import anthropic
        import json

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        # Build image content blocks
        content = []
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": image_base64,
            },
        })

        for img in additional_images:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": img,
                },
            })

        # Label each image so Claude knows what it's looking at
        image_labels = ["Front cover"]
        if additional_images:
            if len(additional_images) >= 1:
                image_labels.append("Title page")
            if len(additional_images) >= 2:
                image_labels.append("Copyright page")
        images_description = "\n".join(f"Image {i+1}: {label}" for i, label in enumerate(image_labels))

        content.append({
            "type": "text",
            "text": f"""You are Gibson, a bibliographic identification system for a used bookstore.

You have been given {len(image_labels)} image(s) of a book:
{images_description}

Use ALL provided images to extract the most accurate bibliographic information possible.
The title page and copyright page (when provided) are authoritative — prefer them over the cover for title, author, publisher, and year.

Return a JSON object with these fields:
- title: string (the book's title)
- subtitle: string or null
- author: string (primary author)
- publisher: string or null
- publication_year: integer or null
- edition_statement: string or null (e.g., "First Edition", "Third Printing")
- format: one of: hardcover, paperback, mass_market_paperback, trade_paperback, other
- isbn: string or null (if visible on back cover)
- language: string (ISO 639-1, default "en")
- genre_signals: list of strings
- title_confidence: float 0-1
- author_confidence: float 0-1
- publisher_confidence: float 0-1
- year_confidence: float 0-1
- overall_confidence: float 0-1

If you cannot determine a field, set it to null and its confidence to 0.
Be conservative with confidence scores — only rate above 0.85 when very certain.""",
        })

        logger.info("Calling Claude Vision (%s) for cover photo", model)
        response = await client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": content}],
        )

        text = response.content[0].text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        data = json.loads(text.strip())
        logger.info(
            "Vision result: title=%r confidence=%.2f",
            data.get("title"), data.get("overall_confidence", 0),
        )
        return VisionExtractionResult(**data)

    except Exception as e:
        logger.error("Vision call failed: %s", str(e))
        return VisionExtractionResult(
            title=None,
            overall_confidence=0.0,
        )


async def process_follow_up(
    identification_id: UUID,
    image_base64: Optional[str] = None,
    yes_no_answer: Optional[bool] = None,
    text_answer: Optional[str] = None,
) -> IdentificationResult:
    """Process a follow-up response from the dealer."""
    # Re-run identification with additional context
    if image_base64:
        return await identify_from_image(image_base64)

    return IdentificationResult(
        path="standard_path",
        confidence=0.0,
        routing_decision="slow_path",
        follow_up_request="Queue for overnight research, or mark in-store only?",
    )


async def identify_shelf_spines(image_base64: str) -> list[dict]:
    """
    Send a shelf photograph to Claude Sonnet. Always Sonnet — shelf scenes
    with worn spines, tight shelving, and varying fonts need it.
    Results in ~8-12 seconds.
    """
    try:
        import anthropic, json

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        response = await client.messages.create(
            model=settings.anthropic_vision_escalation_model,
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_base64,
                        },
                    },
                    {
                        "type": "text",
                        "text": """You are Gibson, a bibliographic identification system for a used bookstore.

This is a photograph of a bookshelf. Identify every book spine you can read.

For each visible spine return a JSON object with these exact fields:
- title: string — the book title as printed on the spine (null if unreadable)
- author: string or null — author name if visible on spine
- isbn: string or null — ISBN or barcode number if visible
- overall_confidence: float 0.0–1.0 — how clearly you can read this spine
  Use 0.8+ only when you can clearly read title AND author.
  Use 0.4–0.7 when you can read the title but author is unclear or absent.
  Use below 0.3 when the spine is worn, obscured, or only partially visible.
- notes: string or null — e.g. "partially obscured by adjacent book", "spine heavily worn", "shelved spine-in"

Return ONLY a valid JSON array of these objects. No other text.
Include every spine you can see, even partially. Do not invent or guess titles — only report what you can actually read from the image.
If you cannot read any spines at all, return an empty array [].""",
                    },
                ],
            }],
        )

        text = response.content[0].text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        spines = json.loads(text)
        if not isinstance(spines, list):
            return []
        return spines

    except Exception:
        return []


def _determine_follow_up(extraction: VisionExtractionResult) -> Optional[str]:
    """
    Gibson asks for exactly one thing. Never "I need more information."
    Determine the most useful follow-up based on what's missing.
    """
    if extraction.year_confidence < 0.5 and extraction.title_confidence > 0.7:
        return "Copyright page — I can see the title but need the publication year."

    if extraction.title_confidence < 0.5:
        return "Title page — the cover is ambiguous. Can you photograph the title page?"

    if extraction.publisher_confidence < 0.5 and extraction.title_confidence > 0.7:
        return "Copyright page — I need to confirm the publisher."

    if extraction.author_confidence < 0.5:
        return "Title page — I can't read the author clearly from the cover."

    return "Copyright page — I need more information to confirm this edition."

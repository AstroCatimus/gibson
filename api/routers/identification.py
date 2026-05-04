"""
Gibson identification pipeline router.
Camera → Barcode (fast) or Cover Photo (standard) → Identification.

CAPTURE FLOW:
1. Camera opens, ZXing-js on live feed
2a. Barcode detected → Fast Path fires
2b. No barcode → "Take cover photo" → Standard Path
3. Confidence ≥ 85% → one-tap confirm
4. Confidence < 85% → Gibson requests exactly one more photo
5. Still < 85% → "Queue for overnight research, or mark in-store only?"
"""

from fastapi import APIRouter, Depends, UploadFile, File, Form
from uuid import UUID, uuid4
from typing import Optional
import time

from api.dependencies import get_store_id, get_employee_id
from api.models.identification import (
    BarcodeResult,
    IdentificationRequest,
    IdentificationResult,
    FollowUpRequest,
)
from api.models.catalogue import MobileConfirmRequest

router = APIRouter()


@router.post("/barcode", response_model=IdentificationResult)
async def fast_path_barcode(
    barcode: BarcodeResult,
    store_id: str = Depends(get_store_id),
):
    """
    Fast Path — barcode detected in camera feed.
    Decode → ISBN-13 normalize → validate → parallel lookup:
      Local DB | Vialibri | eBay sold | BooksRun (low weight)
    Target: under 5 seconds.
    """
    start = time.time()

    # ISBN normalization and validation
    isbn = barcode.isbn_13
    if not isbn or len(isbn) != 13:
        return IdentificationResult(
            path="fast_path",
            confidence=0.0,
            routing_decision="slow_path",
            follow_up_request="Invalid barcode. Take a cover photo instead.",
        )

    # Local DB lookup
    from api.services.barcode import lookup_isbn, lookup_copies
    from api.services.pricing.aggregator import get_pricing
    from api.services.open_library import enrich_edition
    from api.models.identification import StockCopy

    db_result = await lookup_isbn(isbn)
    if db_result:
        db_result = await enrich_edition(db_result)
    pricing = await get_pricing(isbn_13=isbn)

    if db_result:
        elapsed = int((time.time() - start) * 1000)
        # Fetch all physical copies in this store
        copies_raw = await lookup_copies(str(db_result["edition_id"]), store_id)
        copies = [StockCopy(**c) for c in copies_raw]
        return IdentificationResult(
            path="fast_path",
            work_id=db_result.get("work_id"),
            edition_id=db_result.get("edition_id"),
            title=db_result.get("title"),
            author=db_result.get("author"),
            publisher=db_result.get("publisher"),
            publication_year=db_result.get("publication_year"),
            isbn_13=isbn,
            format=db_result.get("format"),
            confidence=db_result.get("confidence", 0.9),
            suggested_price=pricing.suggested_price if pricing else None,
            price_range={"low": pricing.price_range_low, "high": pricing.price_range_high} if pricing else None,
            suggested_section=db_result.get("section"),
            routing_decision="confirm",
            copies=copies,
        )

    # Not in local DB — try Open Library
    from api.services.open_library import fetch_by_isbn as ol_fetch

    meta = await ol_fetch(isbn)

    if meta:
        elapsed = int((time.time() - start) * 1000)
        authors = meta.get("authors") or []
        author_str = authors[0] if authors else None
        pub_year = meta.get("publication_year")
        if not pub_year:
            import re
            pub_date = meta.get("published_date") or ""
            if pub_date:
                m = re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", pub_date)
                pub_year = int(m.group(1)) if m else None

        cover_url = meta.get("cover_image_url") or None
        source = meta.get("source", "external")
        confidence = meta.get("confidence", 0.85)

        return IdentificationResult(
            path="fast_path",
            isbn_13=isbn,
            title=meta.get("title"),
            author=author_str,
            publisher=meta.get("publisher"),
            publication_year=pub_year,
            format=meta.get("format"),
            confidence=confidence,
            suggested_price=pricing.suggested_price if pricing else None,
            price_range={"low": pricing.price_range_low, "high": pricing.price_range_high} if pricing else None,
            routing_decision="confirm" if confidence >= 0.85 else "follow_up",
            follow_up_needed=confidence < 0.85,
            follow_up_request="Take a cover photo to confirm condition." if confidence < 0.85 else None,
            cover_image_url=cover_url,
            needs_cover_photo=not bool(cover_url),
            raw_data={"source": source, "elapsed_ms": elapsed},
        )

    # Nothing found anywhere — escalate to photo identification
    elapsed = int((time.time() - start) * 1000)
    return IdentificationResult(
        path="fast_path",
        isbn_13=isbn,
        confidence=0.1,
        suggested_price=pricing.suggested_price if pricing else None,
        price_range={"low": pricing.price_range_low, "high": pricing.price_range_high} if pricing else None,
        routing_decision="follow_up",
        follow_up_needed=True,
        follow_up_request="ISBN not found in any database. Take a cover photo for identification.",
    )


@router.post("/photo", response_model=IdentificationResult)
async def standard_path_photo(
    request: IdentificationRequest,
):
    """
    Standard Path — cover photo submitted.
    Cover image → EasyOCR + PaddleOCR ensemble
    → Claude Vision (Sonnet): image + OCR text always (hybrid always)
    → Structured JSON with per-field confidence scores
    → ≥ 85%: present result
    → < 85%: request one targeted photo
    → Pricing fires when identification clears 70%
    """
    from api.services.vision import identify_from_image
    from api.services.pricing.aggregator import get_pricing
    from api.services.open_library import fetch_by_isbn as ol_fetch_isbn, search_by_text as ol_search

    result = await identify_from_image(
        image_base64=request.image_base64,
        additional_images=request.additional_images,
    )

    # Cross-reference with Open Library to confirm and fill gaps
    if result.confidence >= 0.50:
        ol = None
        if result.isbn_13:
            ol = await ol_fetch_isbn(result.isbn_13)
        if not ol and result.title:
            ol = await ol_search(result.title, author=result.author)

        if ol:
            ol_authors = ol.get("authors") or []
            # Fill any fields Claude left blank or low-confidence
            if not result.title and ol.get("title"):
                result.title = ol.get("title")
            if not result.author and ol_authors:
                result.author = ol_authors[0]
            if not result.publisher and ol.get("publisher"):
                result.publisher = ol.get("publisher")
            if not result.publication_year and ol.get("publication_year"):
                result.publication_year = ol.get("publication_year")
            if not result.isbn_13 and ol.get("isbn"):
                result.isbn_13 = ol.get("isbn")
            # Always take OL cover if we don't have one
            cover_url = ol.get("cover_image_url") or None
            if cover_url:
                result.cover_image_url = cover_url
                result.needs_cover_photo = False
            else:
                result.needs_cover_photo = True
            # OL confirmation bumps confidence slightly
            result.confidence = min(result.confidence + 0.05, 1.0)
            result.raw_data = (result.raw_data or {})
            result.raw_data["ol_confirmed"] = True

    # Fire pricing when identification clears 70%
    pricing = None
    if result.confidence >= 0.70 and result.isbn_13:
        pricing = await get_pricing(isbn_13=result.isbn_13)
    elif result.confidence >= 0.70 and result.title:
        pricing = await get_pricing(title=result.title, author=result.author)

    if pricing:
        result.suggested_price = pricing.suggested_price
        result.price_range = {"low": pricing.price_range_low, "high": pricing.price_range_high}

    # Routing decision
    if result.confidence >= 0.85:
        result.routing_decision = "confirm"
    elif result.confidence >= 0.50:
        result.routing_decision = "follow_up"
        result.follow_up_needed = True
        # Gibson asks for exactly one thing
    else:
        result.routing_decision = "slow_path"
        result.follow_up_request = "Queue for overnight research, or mark in-store only?"

    return result


@router.post("/follow-up", response_model=IdentificationResult)
async def follow_up(request: FollowUpRequest):
    """
    Gibson asked for one more thing. Dealer provides it.
    If still < 85%: "Queue for overnight research, or mark in-store only?"
    """
    from api.services.vision import process_follow_up

    result = await process_follow_up(
        identification_id=request.identification_id,
        image_base64=request.image_base64,
        yes_no_answer=request.yes_no_answer,
        text_answer=request.text_answer,
    )
    return result


@router.post("/confirm")
async def confirm_identification(
    request: MobileConfirmRequest,
    store_id: str = Depends(get_store_id),
    employee_id: Optional[str] = Depends(get_employee_id),
):
    """
    Dealer confirms identification with one tap.
    Creates Work, Edition, Stock Item as needed.
    Returns the new stock_item_id and a gibson_sku.

    Logic:
    1. If edition_id provided → use that edition.
    2. Else if isbn_13 provided → look up edition by ISBN.
    3. If no edition found → create Work (+ Agent) + Edition.
    4. Create Stock Item under the dealer's store.
    """
    from api.database import fetchrow, execute

    # ── 1. Resolve edition ──────────────────────────────────────
    edition_id: Optional[str] = None

    if request.edition_id:
        edition_id = request.edition_id

    elif request.isbn_13:
        row = await fetchrow(
            "SELECT edition_id FROM gibson_edition WHERE isbn_13 = $1",
            request.isbn_13,
        )
        if row:
            edition_id = str(row["edition_id"])

    # ── 2. Create Work + Edition if needed ──────────────────────
    if not edition_id:
        title = request.title or "Untitled"
        title_sort = title.lower().lstrip("the ").lstrip("a ").lstrip("an ").strip()

        work_row = await fetchrow(
            """
            INSERT INTO gibson_work (title, title_sort, work_type, confidence)
            VALUES ($1, $2, 'monograph', 0.75)
            RETURNING work_id
            """,
            title, title_sort,
        )
        work_id = str(work_row["work_id"])

        # Create agent if author supplied
        if request.author:
            author_name = request.author.strip()
            # Sort name: "Last, First" heuristic
            parts = author_name.rsplit(" ", 1)
            name_sort = f"{parts[-1]}, {parts[0]}" if len(parts) > 1 else author_name

            # Check for existing agent first to avoid duplicate creation
            agent_row = await fetchrow(
                "SELECT agent_id FROM gibson_agent WHERE name_display = $1",
                author_name,
            )
            if not agent_row:
                agent_row = await fetchrow(
                    """
                    INSERT INTO gibson_agent (name_display, name_sort, agent_type)
                    VALUES ($1, $2, 'person')
                    RETURNING agent_id
                    """,
                    author_name, name_sort,
                )

            if agent_row:
                await execute(
                    """
                    INSERT INTO gibson_work_agent (work_id, agent_id, role, role_order)
                    VALUES ($1, $2, 'author', 1)
                    ON CONFLICT DO NOTHING
                    """,
                    work_id, str(agent_row["agent_id"]),
                )

        edition_row = await fetchrow(
            """
            INSERT INTO gibson_edition (work_id, isbn_13, publication_year, confidence)
            VALUES ($1, $2, $3, 0.75)
            RETURNING edition_id
            """,
            work_id, request.isbn_13, request.publication_year,
        )
        edition_id = str(edition_row["edition_id"])

    # ── 3. Generate SKU ─────────────────────────────────────────
    sku = None
    if employee_id:
        initials_row = await fetchrow(
            "SELECT initials FROM gibson_employee WHERE employee_id = $1",
            employee_id,
        )
        if initials_row and initials_row["initials"]:
            seq = await fetchrow("SELECT nextval('gibson_sku_seq') as seq")
            sku = f"{initials_row['initials']}-{seq['seq']}"

    if not sku:
        # Fallback SKU from store prefix + sequence
        seq = await fetchrow("SELECT nextval('gibson_sku_seq') as seq")
        prefix_row = await fetchrow(
            "SELECT prefix FROM gibson_store WHERE store_id = $1", store_id
        )
        prefix = prefix_row["prefix"] if prefix_row else "GS"
        sku = f"{prefix}-{seq['seq']}"

    # ── 4. Resolve section → location_id (create if new) ────────
    location_id = None
    if request.section:
        loc_row = await fetchrow(
            "SELECT location_id FROM gibson_location WHERE store_id = $1 AND section = $2",
            store_id, request.section,
        )
        if loc_row:
            location_id = str(loc_row["location_id"])
        else:
            new_loc = await fetchrow(
                """
                INSERT INTO gibson_location (store_id, section, section_code)
                VALUES ($1, $2, $3)
                RETURNING location_id
                """,
                store_id, request.section,
                request.section[:6].upper().replace(" ", ""),
            )
            location_id = str(new_loc["location_id"])

    # ── 5. Create Stock Item ─────────────────────────────────────
    item_row = await fetchrow(
        """
        INSERT INTO gibson_stock_item (
            edition_id, gibson_sku, store_id,
            condition_grade, condition_mode,
            asking_price, is_signed, is_inscribed,
            location_id
        )
        VALUES ($1, $2, $3, $4, 'tap', $5, $6, $7, $8)
        RETURNING stock_item_id, gibson_sku, status, created_at
        """,
        edition_id, sku, store_id,
        request.condition_grade, request.asking_price,
        request.is_signed, request.is_inscribed,
        location_id,
    )

    return {
        "status": "confirmed",
        "stock_item_id": str(item_row["stock_item_id"]),
        "gibson_sku": item_row["gibson_sku"],
        "edition_id": edition_id,
        "inventory_status": item_row["status"],
        "created_at": item_row["created_at"].isoformat(),
    }



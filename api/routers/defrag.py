"""
Gibson Defrag — Shelf Verification Router.
Walks the inventory section by section, card by card.
FOUND / FOUND_UPDATE / NOT_FOUND / SKIP actions.
"""

from fastapi import APIRouter, Depends, Query, Body
from typing import Optional
from uuid import uuid4
import json

from api.dependencies import get_store_id, get_employee_id
from api.database import fetch, fetchrow, execute

router = APIRouter()


@router.get("/stats")
async def defrag_stats(store_id: str = Depends(get_store_id)):
    """Overall verification progress for the store."""
    row = await fetchrow(
        """
        SELECT
            COUNT(*)                                                        AS total,
            COUNT(*) FILTER (WHERE shelf_verification_status = 'VERIFIED')  AS verified,
            COUNT(*) FILTER (WHERE shelf_verification_status = 'MISSING')   AS missing,
            COUNT(*) FILTER (WHERE shelf_verification_status = 'UNVERIFIED')AS unverified,
            COUNT(*) FILTER (WHERE trust_tier = 1)                          AS tier1,
            COUNT(*) FILTER (WHERE trust_tier = 2)                          AS tier2,
            COUNT(*) FILTER (WHERE trust_tier = 3)                          AS tier3
        FROM gibson_stock_item
        WHERE store_id = $1
          AND status NOT IN ('WITHDRAWN','SOLD')
        """,
        store_id,
    )
    # Price staleness counts
    staleness = await fetchrow(
        """
        SELECT
            COUNT(*) FILTER (WHERE price_last_refreshed IS NULL)                   AS legacy,
            COUNT(*) FILTER (WHERE price_last_refreshed > now() - INTERVAL '30 days')  AS fresh,
            COUNT(*) FILTER (
                WHERE price_last_refreshed <= now() - INTERVAL '30 days'
                  AND price_last_refreshed >  now() - INTERVAL '180 days'
            ) AS aging,
            COUNT(*) FILTER (
                WHERE price_last_refreshed <= now() - INTERVAL '180 days'
            ) AS stale
        FROM gibson_stock_item
        WHERE store_id = $1 AND status NOT IN ('WITHDRAWN','SOLD')
        """,
        store_id,
    )

    # Unknown-section count
    unk = await fetchrow(
        """
        SELECT COUNT(*) AS cnt
        FROM gibson_stock_item si
        LEFT JOIN gibson_location l ON l.location_id = si.location_id
        WHERE si.store_id = $1
          AND si.status NOT IN ('WITHDRAWN','SOLD')
          AND (l.section = 'UNKNOWN_SECTION' OR si.location_id IS NULL)
        """,
        store_id,
    )

    total = row["total"] or 1
    return {
        "total": row["total"],
        "verified": row["verified"],
        "missing": row["missing"],
        "unverified": row["unverified"],
        "pct_complete": round(row["verified"] / total * 100, 1),
        "tier_breakdown": {
            "tier1": row["tier1"],
            "tier2": row["tier2"],
            "tier3": row["tier3"],
        },
        "price_staleness": {
            "legacy": staleness["legacy"],
            "fresh":  staleness["fresh"],
            "aging":  staleness["aging"],
            "stale":  staleness["stale"],
        },
        "unsectioned": unk["cnt"],
    }


@router.get("/sections")
async def defrag_sections(store_id: str = Depends(get_store_id)):
    """Sections with verification queue counts, sorted by most unverified first."""
    rows = await fetch(
        """
        SELECT
            l.location_id,
            l.section,
            l.section_code,
            COUNT(si.stock_item_id)                                              AS total,
            COUNT(*) FILTER (WHERE si.shelf_verification_status = 'VERIFIED')   AS verified,
            COUNT(*) FILTER (WHERE si.shelf_verification_status = 'UNVERIFIED') AS unverified,
            COUNT(*) FILTER (WHERE si.shelf_verification_status = 'MISSING')    AS missing,
            COUNT(*) FILTER (WHERE si.trust_tier = 2)                           AS tier2,
            COUNT(*) FILTER (WHERE si.trust_tier = 3)                           AS tier3
        FROM gibson_location l
        LEFT JOIN gibson_stock_item si
               ON si.location_id = l.location_id
              AND si.status NOT IN ('WITHDRAWN','SOLD')
        WHERE l.store_id = $1
        GROUP BY l.location_id, l.section, l.section_code
        ORDER BY COUNT(*) FILTER (WHERE si.shelf_verification_status = 'UNVERIFIED') DESC
        """,
        store_id,
    )
    return [dict(r) for r in rows]


@router.get("/queue")
async def defrag_queue(
    section: Optional[str] = Query(None),
    location_id: Optional[str] = Query(None),
    tier: Optional[int] = Query(None),
    limit: int = Query(20, le=100),
    offset: int = Query(0),
    store_id: str = Depends(get_store_id),
):
    """
    Verification queue for a section.
    Priority: Tier 3 (Ka-Zam) first, then Tier 2 (Amazon), then Tier 1.
    Within tier: alphabetical by title.
    """
    filters = ["si.store_id = $1", "si.status NOT IN ('WITHDRAWN','SOLD')",
               "si.shelf_verification_status IN ('UNVERIFIED','NEEDS_VERIFICATION')"]
    args = [store_id]
    idx = 2

    if location_id:
        filters.append(f"si.location_id = ${idx}")
        args.append(location_id)
        idx += 1
    elif section:
        filters.append(f"l.section = ${idx}")
        args.append(section)
        idx += 1

    if tier:
        filters.append(f"si.trust_tier = ${idx}")
        args.append(tier)
        idx += 1

    where = " AND ".join(filters)

    rows = await fetch(
        f"""
        SELECT
            si.stock_item_id,
            si.gibson_sku,
            si.trust_tier,
            si.shelf_verification_status,
            si.asking_price,
            si.condition_grade,
            si.amazon_listing_id,
            si.amazon_asin,
            si.kz_status,
            l.section,
            l.section_code,
            e.isbn_13,
            e.publication_year,
            w.title,
            w.title_sort,
            string_agg(DISTINCT a.name_display, ', ') AS author
        FROM gibson_stock_item si
        LEFT JOIN gibson_location l   ON l.location_id = si.location_id
        LEFT JOIN gibson_edition e    ON e.edition_id  = si.edition_id
        LEFT JOIN gibson_work w       ON w.work_id     = e.work_id
        LEFT JOIN gibson_work_agent wa ON wa.work_id   = w.work_id AND wa.role = 'author'
        LEFT JOIN gibson_agent a       ON a.agent_id   = wa.agent_id
        WHERE {where}
        GROUP BY si.stock_item_id, l.section, l.section_code,
                 e.isbn_13, e.publication_year, w.title, w.title_sort
        ORDER BY si.trust_tier DESC, w.title_sort NULLS LAST
        LIMIT ${idx} OFFSET ${idx+1}
        """,
        *args, limit, offset,
    )

    total_row = await fetchrow(
        f"""
        SELECT COUNT(DISTINCT si.stock_item_id) AS cnt
        FROM gibson_stock_item si
        LEFT JOIN gibson_location l ON l.location_id = si.location_id
        WHERE {where}
        """,
        *args,
    )

    return {
        "items": [dict(r) for r in rows],
        "total": total_row["cnt"],
        "offset": offset,
        "limit": limit,
    }


@router.post("/verify/{stock_item_id}")
async def verify_item(
    stock_item_id: str,
    action: str,          # FOUND | FOUND_UPDATE | NOT_FOUND | SKIP
    session_id: Optional[str] = None,
    asking_price: Optional[float] = None,
    condition_grade: Optional[str] = None,
    section: Optional[str] = None,
    store_id: str = Depends(get_store_id),
    employee_id: Optional[str] = Depends(get_employee_id),
):
    """
    Record a verification action on a stock item.
    FOUND          → mark VERIFIED, stamp verified_at/by
    FOUND_UPDATE   → mark VERIFIED + apply any price/condition/section updates
    NOT_FOUND      → mark MISSING
    SKIP           → mark NEEDS_VERIFICATION (come back later)
    """
    if action not in ("FOUND", "FOUND_UPDATE", "NOT_FOUND", "SKIP"):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

    status_map = {
        "FOUND":        "VERIFIED",
        "FOUND_UPDATE": "VERIFIED",
        "NOT_FOUND":    "MISSING",
        "SKIP":         "NEEDS_VERIFICATION",
    }
    new_status = status_map[action]

    # Verify item belongs to store
    item = await fetchrow(
        "SELECT stock_item_id FROM gibson_stock_item WHERE stock_item_id = $1 AND store_id = $2",
        stock_item_id, store_id,
    )
    if not item:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Item not found")

    await execute(
        """
        UPDATE gibson_stock_item
        SET shelf_verification_status = $1,
            verified_at  = CASE WHEN $1 IN ('VERIFIED','MISSING') THEN now() ELSE verified_at END,
            verified_by  = CASE WHEN $1 IN ('VERIFIED','MISSING') AND $2::text ~ '^[0-9a-f-]{36}$' THEN $2::uuid ELSE verified_by END
        WHERE stock_item_id = $3
        """,
        new_status, employee_id or "", stock_item_id,
    )

    if action == "FOUND_UPDATE":
        if asking_price is not None:
            await execute(
                "UPDATE gibson_stock_item SET asking_price = $1 WHERE stock_item_id = $2",
                asking_price, stock_item_id,
            )
        if condition_grade:
            await execute(
                "UPDATE gibson_stock_item SET condition_grade = $1 WHERE stock_item_id = $2",
                condition_grade, stock_item_id,
            )
        if section:
            loc = await fetchrow(
                "SELECT location_id FROM gibson_location WHERE store_id = $1 AND section = $2",
                store_id, section,
            )
            if loc:
                await execute(
                    "UPDATE gibson_stock_item SET location_id = $1 WHERE stock_item_id = $2",
                    str(loc["location_id"]), stock_item_id,
                )

    # Update session counters if session_id provided
    if session_id:
        col = "verified_count" if new_status == "VERIFIED" else \
              "missing_count"  if new_status == "MISSING"  else "skipped_count"
        await execute(
            f"UPDATE gibson_verification_session SET {col} = {col} + 1 WHERE session_id = $1",
            session_id,
        )

    return {"ok": True, "stock_item_id": stock_item_id, "status": new_status}


@router.post("/session/start")
async def start_session(
    section: Optional[str] = None,
    store_id: str = Depends(get_store_id),
    employee_id: Optional[str] = Depends(get_employee_id),
):
    """Begin a verification session (audit trail)."""
    row = await fetchrow(
        """
        INSERT INTO gibson_verification_session (store_id, user_id, section)
        VALUES ($1, $2, $3)
        RETURNING session_id, started_at
        """,
        store_id, employee_id or "unknown", section,
    )
    return {"session_id": str(row["session_id"]), "started_at": row["started_at"].isoformat()}


@router.post("/session/{session_id}/end")
async def end_session(session_id: str):
    """Close a verification session."""
    await execute(
        "UPDATE gibson_verification_session SET completed_at = now() WHERE session_id = $1",
        session_id,
    )
    row = await fetchrow(
        "SELECT * FROM gibson_verification_session WHERE session_id = $1", session_id
    )
    return dict(row)


@router.get("/missing")
async def missing_queue(
    section: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    store_id: str = Depends(get_store_id),
):
    """Items marked MISSING — resolution queue."""
    filters = ["si.store_id = $1", "si.shelf_verification_status = 'MISSING'"]
    args = [store_id]
    idx = 2

    if section:
        filters.append(f"l.section = ${idx}")
        args.append(section)
        idx += 1

    where = " AND ".join(filters)
    rows = await fetch(
        f"""
        SELECT
            si.stock_item_id,
            si.gibson_sku,
            si.trust_tier,
            si.asking_price,
            si.amazon_listing_id,
            si.amazon_asin,
            si.verified_at,
            l.section,
            e.isbn_13,
            w.title,
            string_agg(DISTINCT a.name_display, ', ') AS author
        FROM gibson_stock_item si
        LEFT JOIN gibson_location l   ON l.location_id  = si.location_id
        LEFT JOIN gibson_edition e    ON e.edition_id   = si.edition_id
        LEFT JOIN gibson_work w       ON w.work_id      = e.work_id
        LEFT JOIN gibson_work_agent wa ON wa.work_id    = w.work_id AND wa.role = 'author'
        LEFT JOIN gibson_agent a       ON a.agent_id    = wa.agent_id
        WHERE {where}
        GROUP BY si.stock_item_id, l.section, e.isbn_13, w.title
        ORDER BY si.verified_at DESC NULLS LAST
        LIMIT ${idx} OFFSET ${idx+1}
        """,
        *args, limit, offset,
    )
    return [dict(r) for r in rows]


@router.patch("/missing/{stock_item_id}")
async def resolve_missing(
    stock_item_id: str,
    resolution: str,   # SOLD_CONFIRMED | RELOCATED | FOUND | WITHDRAWN
    section: Optional[str] = None,
    store_id: str = Depends(get_store_id),
):
    """
    Resolve a missing item.
    SOLD_CONFIRMED → mark status SOLD, shelf_verification_status SOLD_CONFIRMED
    RELOCATED      → update section + mark VERIFIED
    FOUND          → mark VERIFIED
    WITHDRAWN      → soft delete
    """
    valid = ("SOLD_CONFIRMED", "RELOCATED", "FOUND", "WITHDRAWN")
    if resolution not in valid:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Unknown resolution: {resolution}")

    item = await fetchrow(
        "SELECT stock_item_id FROM gibson_stock_item WHERE stock_item_id = $1 AND store_id = $2",
        stock_item_id, store_id,
    )
    if not item:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Item not found")

    if resolution == "SOLD_CONFIRMED":
        await execute(
            "UPDATE gibson_stock_item SET status = 'SOLD', shelf_verification_status = 'SOLD_CONFIRMED' WHERE stock_item_id = $1",
            stock_item_id,
        )
    elif resolution == "WITHDRAWN":
        await execute(
            "UPDATE gibson_stock_item SET status = 'WITHDRAWN' WHERE stock_item_id = $1",
            stock_item_id,
        )
    elif resolution == "FOUND":
        await execute(
            "UPDATE gibson_stock_item SET shelf_verification_status = 'VERIFIED', verified_at = now() WHERE stock_item_id = $1",
            stock_item_id,
        )
    elif resolution == "RELOCATED" and section:
        loc = await fetchrow(
            "SELECT location_id FROM gibson_location WHERE store_id = $1 AND section = $2",
            store_id, section,
        )
        if loc:
            await execute(
                """
                UPDATE gibson_stock_item
                SET location_id = $1,
                    shelf_verification_status = 'VERIFIED',
                    verified_at = now()
                WHERE stock_item_id = $2
                """,
                str(loc["location_id"]), stock_item_id,
            )

    return {"ok": True, "resolution": resolution}


@router.get("/export")
async def export_tsv(
    format: str = Query("amazon", pattern="^(amazon|biblio)$"),
    status: str = Query("all", pattern="^(all|verified|unverified|missing)$"),
    store_id: str = Depends(get_store_id),
):
    """
    Generate TSV export.
    amazon  → SKU, ISBN, Title, Author, Condition, Price, Amazon ASIN
    biblio  → SKU, ISBN, Title, Author, Publisher, Year, Condition, Price, Section
    """
    from fastapi.responses import PlainTextResponse
    import io

    status_filter = ""
    if status == "verified":
        status_filter = "AND si.shelf_verification_status = 'VERIFIED'"
    elif status == "unverified":
        status_filter = "AND si.shelf_verification_status = 'UNVERIFIED'"
    elif status == "missing":
        status_filter = "AND si.shelf_verification_status = 'MISSING'"

    rows = await fetch(
        f"""
        SELECT
            si.gibson_sku,
            si.asking_price,
            si.condition_grade,
            si.amazon_listing_id,
            si.amazon_asin,
            l.section,
            e.isbn_13,
            e.publication_year,
            w.title,
            string_agg(DISTINCT a.name_display, '; ') AS author,
            string_agg(DISTINCT pub.name_display, '; ') AS publisher
        FROM gibson_stock_item si
        LEFT JOIN gibson_location l    ON l.location_id  = si.location_id
        LEFT JOIN gibson_edition e     ON e.edition_id   = si.edition_id
        LEFT JOIN gibson_work w        ON w.work_id      = e.work_id
        LEFT JOIN gibson_work_agent wa ON wa.work_id     = w.work_id AND wa.role = 'author'
        LEFT JOIN gibson_agent a       ON a.agent_id     = wa.agent_id
        LEFT JOIN gibson_work_agent wp ON wp.work_id     = w.work_id AND wp.role = 'publisher'
        LEFT JOIN gibson_agent pub     ON pub.agent_id   = wp.agent_id
        WHERE si.store_id = $1
          AND si.status NOT IN ('WITHDRAWN','SOLD')
          {status_filter}
        GROUP BY si.stock_item_id, l.section,
                 e.isbn_13, e.publication_year, w.title, w.title_sort
        ORDER BY w.title_sort NULLS LAST
        """,
        store_id,
    )

    buf = io.StringIO()
    if format == "amazon":
        buf.write("SKU\tISBN\tTitle\tAuthor\tCondition\tPrice\tASIN\n")
        for r in rows:
            buf.write(
                f"{r['gibson_sku'] or ''}\t{r['isbn_13'] or ''}\t"
                f"{(r['title'] or '').replace(chr(9),' ')}\t"
                f"{(r['author'] or '').replace(chr(9),' ')}\t"
                f"{r['condition_grade'] or ''}\t"
                f"{r['asking_price'] or ''}\t"
                f"{r['amazon_asin'] or ''}\n"
            )
    else:  # biblio
        buf.write("SKU\tISBN\tTitle\tAuthor\tPublisher\tYear\tCondition\tPrice\tSection\n")
        for r in rows:
            buf.write(
                f"{r['gibson_sku'] or ''}\t{r['isbn_13'] or ''}\t"
                f"{(r['title'] or '').replace(chr(9),' ')}\t"
                f"{(r['author'] or '').replace(chr(9),' ')}\t"
                f"{(r['publisher'] or '').replace(chr(9),' ')}\t"
                f"{r['publication_year'] or ''}\t"
                f"{r['condition_grade'] or ''}\t"
                f"{r['asking_price'] or ''}\t"
                f"{r['section'] or ''}\n"
            )

    filename = f"gibson_{format}_export.tsv"
    return PlainTextResponse(
        buf.getvalue(),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        media_type="text/tab-separated-values",
    )


# ═══════════════════════════════════════════════════════════════
# SHELF SCAN — Claude Vision, instant results
# ═══════════════════════════════════════════════════════════════

@router.post("/shelf-scan")
async def shelf_scan(
    image_base64: str = Body(...),
    section: str = Body(...),
    session_id: Optional[str] = Body(None),
    store_id: str = Depends(get_store_id),
    employee_id: Optional[str] = Depends(get_employee_id),
):
    """
    Photograph a shelf → instant results via Claude Vision.
    No batching, no overnight queue. Results in ~10 seconds.

    GREEN  → matched to DB record, location correct → auto-verified
    YELLOW → matched but in wrong section → conflict queue
    RED    → spine readable but not in DB → needs cataloguing
    GREY   → spine unreadable → escalation photo requested
    """
    from api.services.vision import identify_shelf_spines

    # 1. Send to Claude Sonnet — identify all visible spines
    spines = await identify_shelf_spines(image_base64)

    green, yellow, red, grey = [], [], [], []
    auto_verified = 0

    for spine in spines:
        conf = spine.get("overall_confidence", 0)

        if conf < 0.25 or not spine.get("title"):
            grey.append({
                "title": spine.get("title"),
                "notes": spine.get("notes", "Spine unreadable"),
                "confidence": conf,
            })
            continue

        # 2a. Try ISBN match first (exact)
        item = None
        raw_isbn = spine.get("isbn") or ""
        # Normalize ISBN digits only
        isbn_digits = "".join(c for c in raw_isbn if c.isdigit())
        if len(isbn_digits) == 13:
            item = await fetchrow(
                """
                SELECT si.stock_item_id, si.shelf_verification_status,
                       l.section AS db_section, w.title AS db_title, e.isbn_13
                FROM gibson_stock_item si
                LEFT JOIN gibson_edition e  ON e.edition_id  = si.edition_id
                LEFT JOIN gibson_work w     ON w.work_id     = e.work_id
                LEFT JOIN gibson_location l ON l.location_id = si.location_id
                WHERE e.isbn_13 = $1 AND si.store_id = $2
                  AND si.status NOT IN ('WITHDRAWN','SOLD')
                LIMIT 1
                """,
                isbn_digits, store_id,
            )

        # 2b. Fall back to title fuzzy match
        if not item and spine.get("title"):
            title_q = spine["title"][:50].replace("%", "").strip()
            item = await fetchrow(
                """
                SELECT si.stock_item_id, si.shelf_verification_status,
                       l.section AS db_section, w.title AS db_title, e.isbn_13
                FROM gibson_stock_item si
                LEFT JOIN gibson_edition e  ON e.edition_id  = si.edition_id
                LEFT JOIN gibson_work w     ON w.work_id     = e.work_id
                LEFT JOIN gibson_location l ON l.location_id = si.location_id
                WHERE w.title ILIKE $1 AND si.store_id = $2
                  AND si.status NOT IN ('WITHDRAWN','SOLD')
                LIMIT 1
                """,
                f"%{title_q}%", store_id,
            )

        if not item:
            red.append({
                "title":  spine.get("title"),
                "author": spine.get("author"),
                "isbn":   spine.get("isbn"),
                "confidence": conf,
                "notes":  spine.get("notes"),
            })
            continue

        db_section = item["db_section"] or ""
        location_match = (
            db_section.lower() == section.lower()
            or not db_section  # no location on record — treat as match
        )

        spine_data = {
            "title":          spine.get("title"),
            "author":         spine.get("author"),
            "isbn":           spine.get("isbn"),
            "db_title":       item["db_title"],
            "db_isbn":        item["isbn_13"],
            "db_section":     db_section,
            "stock_item_id":  str(item["stock_item_id"]),
            "confidence":     conf,
        }

        if location_match:
            # GREEN — auto-verify
            await execute(
                """
                UPDATE gibson_stock_item
                SET shelf_verification_status = 'VERIFIED', verified_at = now()
                WHERE stock_item_id = $1
                  AND shelf_verification_status != 'VERIFIED'
                """,
                str(item["stock_item_id"]),
            )
            auto_verified += 1
            green.append(spine_data)
        else:
            # YELLOW — location conflict
            yellow.append(spine_data)

    # 3. Update session counters
    if session_id and auto_verified:
        await execute(
            """
            UPDATE gibson_verification_session
            SET verified_count = verified_count + $1
            WHERE session_id = $2
            """,
            auto_verified, session_id,
        )

    # 4. Log the scan
    scan_row = await fetchrow(
        """
        INSERT INTO gibson_shelf_scan
            (store_id, section, scanned_by, spines_detected,
             auto_verified, conflicts, not_found, unclear, raw_results,
             session_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        RETURNING scan_id
        """,
        store_id, section, employee_id or "unknown",
        len(spines), auto_verified, len(yellow), len(red), len(grey),
        json.dumps({"green": green, "yellow": yellow, "red": red, "grey": grey}),
        session_id,
    )

    # 5. Update section defrag_status
    loc = await fetchrow(
        "SELECT location_id FROM gibson_location WHERE store_id = $1 AND section = $2",
        store_id, section,
    )
    if loc:
        await execute(
            """
            UPDATE gibson_location
            SET defrag_status = 'IN_PROGRESS',
                last_scanned_at = now()
            WHERE location_id = $1 AND defrag_status = 'NOT_STARTED'
            """,
            str(loc["location_id"]),
        )

    return {
        "scan_id":       str(scan_row["scan_id"]),
        "section":       section,
        "spines_total":  len(spines),
        "auto_verified": auto_verified,
        "green":  green,
        "yellow": yellow,
        "red":    red,
        "grey":   grey,
        "summary": {
            "green":  len(green),
            "yellow": len(yellow),
            "red":    len(red),
            "grey":   len(grey),
        },
    }


@router.post("/resolve-conflict/{stock_item_id}")
async def resolve_location_conflict(
    stock_item_id: str,
    action: str = Body(...),      # UPDATE_LOCATION | RETURN_TO_SECTION
    new_section: Optional[str] = Body(None),
    store_id: str = Depends(get_store_id),
):
    """
    Resolve a YELLOW (location conflict) from a shelf scan.
    UPDATE_LOCATION  → book has moved; update record to match reality
    RETURN_TO_SECTION → book was mishelved; add to reshelving list (no DB change)
    """
    if action == "UPDATE_LOCATION" and new_section:
        loc = await fetchrow(
            "SELECT location_id FROM gibson_location WHERE store_id = $1 AND section = $2",
            store_id, new_section,
        )
        if loc:
            await execute(
                """
                UPDATE gibson_stock_item
                SET location_id = $1,
                    shelf_verification_status = 'VERIFIED',
                    verified_at = now()
                WHERE stock_item_id = $2 AND store_id = $3
                """,
                str(loc["location_id"]), stock_item_id, store_id,
            )
    elif action == "RETURN_TO_SECTION":
        # Mark as verified (it was found), don't change location
        await execute(
            """
            UPDATE gibson_stock_item
            SET shelf_verification_status = 'VERIFIED', verified_at = now()
            WHERE stock_item_id = $1 AND store_id = $2
            """,
            stock_item_id, store_id,
        )

    return {"ok": True, "action": action}

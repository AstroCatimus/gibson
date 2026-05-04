"""
Gibson Import Router.
Ingest Ka-Zam and Amazon inventory exports into Gibson.

Imports run as background jobs — upload returns a job_id immediately,
app polls /api/import/status/{job_id} for progress.

Batch-optimised: idempotency and ISBN checks are batched per 500 rows,
cutting DB round-trips from ~5/row to ~0.02/row for the lookup phase.

Trust tier: Amazon = 2, Ka-Zam = 3.
"""

import asyncio
import csv
import io
import re
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from api.dependencies import get_store_id
from api.database import fetch, fetchrow, execute

router = APIRouter()

# ── In-memory job store ───────────────────────────────────────────
# Single-process uvicorn — this is fine. Jobs survive for the session.
_jobs: dict[str, dict] = {}

BATCH_SIZE = 500


def _new_job(source: str, store_id: str) -> str:
    job_id = str(uuid4())
    _jobs[job_id] = {
        "job_id":       job_id,
        "source":       source,
        "store_id":     store_id,
        "status":       "running",
        "total":        0,
        "processed":    0,
        "created":      0,
        "updated":      0,
        "skipped":      0,
        "errors":       0,
        "error_details": [],
        "done":         False,
    }
    return job_id


def _update_job(job_id: str, **kwargs):
    if job_id in _jobs:
        _jobs[job_id].update(kwargs)


# ══════════════════════════════════════════════════════════════════
# Shared helpers
# ══════════════════════════════════════════════════════════════════

def _normalize_isbn(raw: str) -> Optional[str]:
    if not raw:
        return None
    digits = re.sub(r"[^0-9X]", "", raw.upper())
    if len(digits) == 13 and digits.startswith(("978", "979")):
        return digits
    if len(digits) == 10:
        base = "978" + digits[:9]
        check = 0
        for i, d in enumerate(base):
            check += int(d) * (1 if i % 2 == 0 else 3)
        return base + str((10 - (check % 10)) % 10)
    return None


def _classify_isbn(raw: str, year: Optional[int]) -> str:
    if not raw or not raw.strip():
        return "PRE_ISBN" if (year and year < 1970) else "MISSING_ISBN"
    digits = re.sub(r"[^0-9X]", "", raw.upper())
    if len(digits) == 13 and digits.startswith(("978", "979")):
        return "NORMAL"
    if len(digits) == 10:
        try:
            total = sum((10 - i) * (10 if digits[i] == 'X' else int(digits[i])) for i in range(10))
            return "NORMAL" if total % 11 == 0 else "INVALID_ISBN"
        except Exception:
            return "INVALID_ISBN"
    return "NON_STANDARD" if len(digits) >= 8 else "INVALID_ISBN"


def _year_from_string(s: str) -> Optional[int]:
    if not s:
        return None
    m = re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", s)
    return int(m.group(1)) if m else None


def _parse_price(s: str) -> Optional[float]:
    if not s:
        return None
    try:
        return float(re.sub(r"[^0-9.]", "", s)) or None
    except ValueError:
        return None


def _map_condition(raw: str) -> str:
    """
    Normalize to Gibson grades: Fine, Very Good+, Very Good, Good+, Good, Fair, Poor
    Handles Amazon numeric codes (11=New, 1=LN, 2=VG, 3=Good, 4=Acceptable)
    and Ka-Zam / free-text grades.
    """
    r = (raw or "").strip()
    rl = r.lower()
    if r == "11":                                           return "Fine"
    if r == "1":                                            return "Fine"
    if r == "2":                                            return "Very Good"
    if r == "3":                                            return "Good"
    if r == "4":                                            return "Fair"
    if rl in ("new", "fine", "mint", "as new"):             return "Fine"
    if rl in ("like new", "ln", "used_like_new"):           return "Fine"
    if "very good+" in rl or rl in ("vg+", "vg +"):        return "Very Good+"
    if rl in ("very good", "vg", "used_very_good"):         return "Very Good"
    if "good+" in rl or rl in ("g+", "g +"):               return "Good+"
    if rl in ("good", "g", "used_good"):                    return "Good"
    if rl in ("acceptable", "fair", "used_acceptable") \
            or "acceptable" in rl:                          return "Fair"
    if "poor" in rl or "reading copy" in rl:               return "Poor"
    return "Good"   # safe default — never crash


def _find_col(headers: list[str], candidates: list[str]) -> Optional[str]:
    lower = {h.lower().strip(): h for h in headers}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    return None


# ── Field maps ────────────────────────────────────────────────────

AMAZON_FIELD_MAP = {
    "isbn":       ["product-id", "isbn", "isbn-13", "isbn_13"],
    "title":      ["item-name", "title", "product-name"],
    "price":      ["price", "your-price", "list-price"],
    "condition":  ["item-condition", "condition"],
    "sku":        ["seller-sku", "sku"],
    "asin":       ["asin1", "asin2", "asin3", "asin"],
    "listing_id": ["listing-id", "listing_id"],
    "status":     ["status", "item-status"],
    "quantity":   ["quantity", "available-quantity"],
}

KAZAM_FIELD_MAP = {
    "isbn":      ["isbn", "isbn13", "isbn-13", "mpn"],
    "title":     ["title", "book title", "book_title"],
    "author":    ["author", "authors", "by"],
    "price":     ["price", "list price", "selling_price", "your price"],
    "condition": ["condition", "item condition", "grade"],
    "sku":       ["id", "sku", "item #", "item#", "kz sku"],
    "location":  ["location", "genre", "shelf", "bin", "section"],
    "publisher": ["publisher", "brand", "pub"],
    "year":      ["year", "pub year", "publication year", "copyright"],
    "status":    ["status"],
}


# ══════════════════════════════════════════════════════════════════
# Edition / work upsert (still per-row but cache-assisted)
# ══════════════════════════════════════════════════════════════════

async def _upsert_edition(
    isbn: Optional[str], title: str, author: Optional[str],
    publisher: Optional[str], year: Optional[int],
    edition_cache: dict,
) -> tuple[str, str]:
    """Return (work_id, edition_id). Uses edition_cache to skip repeat lookups."""
    if isbn and isbn in edition_cache:
        return edition_cache[isbn]

    if isbn:
        row = await fetchrow(
            "SELECT edition_id, work_id FROM gibson_edition WHERE isbn_13 = $1", isbn
        )
        if row:
            result = (str(row["work_id"]), str(row["edition_id"]))
            edition_cache[isbn] = result
            return result

    title = title or "Untitled"
    title_sort = re.sub(r"^(the|a|an)\s+", "", title.lower()).strip()
    work_row = await fetchrow(
        "INSERT INTO gibson_work (title, title_sort, work_type, confidence) "
        "VALUES ($1,$2,'monograph',0.6) RETURNING work_id",
        title, title_sort,
    )
    work_id = str(work_row["work_id"])

    if author:
        author = author.strip()
        agent_row = await fetchrow(
            "SELECT agent_id FROM gibson_agent WHERE name_display = $1", author
        )
        if not agent_row:
            parts = author.rsplit(" ", 1)
            name_sort = f"{parts[-1]}, {parts[0]}" if len(parts) > 1 else author
            agent_row = await fetchrow(
                "INSERT INTO gibson_agent (name_display, name_sort, agent_type) "
                "VALUES ($1,$2,'person') RETURNING agent_id",
                author, name_sort,
            )
        if agent_row:
            await execute(
                "INSERT INTO gibson_work_agent (work_id, agent_id, role, role_order) "
                "VALUES ($1,$2,'author',1) ON CONFLICT DO NOTHING",
                work_id, str(agent_row["agent_id"]),
            )

    edition_row = await fetchrow(
        "INSERT INTO gibson_edition (work_id, isbn_13, publication_year, confidence) "
        "VALUES ($1,$2,$3,0.6) RETURNING edition_id",
        work_id, isbn, year,
    )
    edition_id = str(edition_row["edition_id"])
    if isbn:
        edition_cache[isbn] = (work_id, edition_id)
    return work_id, edition_id


async def _get_or_create_location(store_id: str, section: str, cache: dict) -> Optional[str]:
    if not section:
        return None
    if section in cache:
        return cache[section]
    row = await fetchrow(
        "SELECT location_id FROM gibson_location WHERE store_id = $1 AND section = $2",
        store_id, section,
    )
    if row:
        loc_id = str(row["location_id"])
        cache[section] = loc_id
        return loc_id
    new = await fetchrow(
        "INSERT INTO gibson_location (store_id, section, section_code) "
        "VALUES ($1,$2,$3) RETURNING location_id",
        store_id, section, section[:6].upper().replace(" ", ""),
    )
    loc_id = str(new["location_id"])
    cache[section] = loc_id
    return loc_id


# ══════════════════════════════════════════════════════════════════
# Batch idempotency check — key optimisation
# Checks 500 external_ids in ONE query instead of 500 queries
# ══════════════════════════════════════════════════════════════════

async def _batch_existing_ext_ids(source_type: str, ext_ids: list[str]) -> set[str]:
    if not ext_ids:
        return set()
    rows = await fetch(
        "SELECT external_id FROM gibson_source_record "
        "WHERE source_type = $1 AND external_id = ANY($2::text[])",
        source_type, ext_ids,
    )
    return {r["external_id"] for r in rows}


# ══════════════════════════════════════════════════════════════════
# Background processors
# ══════════════════════════════════════════════════════════════════

async def _process_amazon(text: str, store_id: str, dry_run: bool, job_id: str):
    import json as _json
    try:
        delim = "\t" if "\t" in text.split("\n")[0] else ","
        reader = csv.DictReader(io.StringIO(text), delimiter=delim)
        headers = reader.fieldnames or []
        cols = {k: _find_col(headers, v) for k, v in AMAZON_FIELD_MAP.items()}
        status_col = cols.get("status") or _find_col(headers, ["status", "item-status"])

        all_rows = list(reader)
        _update_job(job_id, total=len(all_rows))

        prefix_row = await fetchrow(
            "SELECT prefix FROM gibson_store WHERE store_id = $1", store_id
        )
        prefix = prefix_row["prefix"] if prefix_row else "GS"

        edition_cache: dict = {}
        created = updated = skipped = errors = 0
        error_details = []

        for batch_start in range(0, len(all_rows), BATCH_SIZE):
            batch = all_rows[batch_start: batch_start + BATCH_SIZE]

            # Gather ext_ids for batch idempotency check
            ext_ids_batch = []
            parsed = []
            for row in batch:
                row_status = row.get(status_col or "", "").strip().lower() if status_col else ""
                if row_status == "incomplete":
                    parsed.append(None)
                    continue

                isbn_raw    = row.get(cols["isbn"] or "", "")
                title_raw   = (row.get(cols["title"] or "", "") or "").strip()
                price_raw   = row.get(cols["price"] or "", "")
                cond_raw    = row.get(cols["condition"] or "", "")
                sku_raw     = row.get(cols["sku"] or "", "")
                asin_raw    = row.get(cols["asin"] or "", "")
                listing_raw = row.get(cols["listing_id"] or "", "")

                if not title_raw:
                    parsed.append(None)
                    continue

                isbn      = _normalize_isbn(isbn_raw) or _normalize_isbn(asin_raw)
                price     = _parse_price(price_raw)
                condition = _map_condition(cond_raw)
                isbn_flag = _classify_isbn(isbn_raw or asin_raw, None)
                ext_id    = listing_raw or sku_raw or asin_raw or None

                parsed.append({
                    "row": row, "isbn": isbn, "title": title_raw,
                    "price": price, "condition": condition, "isbn_flag": isbn_flag,
                    "sku_raw": sku_raw, "asin_raw": asin_raw,
                    "listing_raw": listing_raw, "ext_id": ext_id,
                })
                if ext_id:
                    ext_ids_batch.append(ext_id)

            # One query for the whole batch
            existing_ext = await _batch_existing_ext_ids("amazon", ext_ids_batch) if not dry_run else set()

            for i, p in enumerate(parsed):
                row_num = batch_start + i + 2
                if p is None:
                    skipped += 1
                    continue
                try:
                    if p["ext_id"] and p["ext_id"] in existing_ext:
                        skipped += 1
                        continue

                    if not dry_run:
                        _, edition_id = await _upsert_edition(
                            p["isbn"], p["title"], None, None, None, edition_cache
                        )
                        seq = await fetchrow("SELECT nextval('gibson_sku_seq') as seq")
                        sku = p["sku_raw"] or f"{prefix}-{seq['seq']}"

                        item_row = await fetchrow(
                            """
                            INSERT INTO gibson_stock_item
                                (edition_id, gibson_sku, store_id, condition_grade,
                                 condition_mode, asking_price, trust_tier,
                                 amazon_listing_id, amazon_asin,
                                 shelf_verification_status, isbn_flag)
                            VALUES ($1,$2,$3,$4,'tap',$5,2,$6,$7,'UNVERIFIED',$8)
                            RETURNING stock_item_id
                            """,
                            edition_id, sku, store_id, p["condition"], p["price"],
                            p["listing_raw"] or None, p["asin_raw"] or None, p["isbn_flag"],
                        )
                        if p["ext_id"]:
                            await execute(
                                "INSERT INTO gibson_source_record "
                                "(source_type, external_id, isbn_norm, raw_data, stock_item_id) "
                                "VALUES ('amazon',$1,$2,$3,$4)",
                                p["ext_id"], p["isbn"],
                                _json.dumps(dict(p["row"])),
                                str(item_row["stock_item_id"]),
                            )
                    created += 1
                except Exception as e:
                    errors += 1
                    if len(error_details) < 20:
                        error_details.append({"row": row_num, "error": str(e)})
                    if errors > 500:
                        _update_job(job_id, status="failed",
                                    error_details=error_details, done=True)
                        return

            processed = min(batch_start + BATCH_SIZE, len(all_rows))
            _update_job(job_id, processed=processed, created=created,
                        updated=updated, skipped=skipped, errors=errors)
            # Yield to event loop between batches
            await asyncio.sleep(0)

        _update_job(job_id, status="done", done=True, processed=len(all_rows),
                    created=created, updated=updated, skipped=skipped,
                    errors=errors, error_details=error_details)

    except Exception as e:
        _update_job(job_id, status="failed", done=True,
                    error_details=[{"error": str(e)}])


async def _process_kazam(text: str, store_id: str, dry_run: bool, job_id: str):
    import json as _json
    try:
        delim = "\t" if "\t" in text.split("\n")[0] else ","
        reader = csv.DictReader(io.StringIO(text), delimiter=delim)
        headers = reader.fieldnames or []
        cols = {k: _find_col(headers, v) for k, v in KAZAM_FIELD_MAP.items()}

        all_rows = list(reader)
        _update_job(job_id, total=len(all_rows))

        prefix_row = await fetchrow(
            "SELECT prefix FROM gibson_store WHERE store_id = $1", store_id
        )
        prefix = prefix_row["prefix"] if prefix_row else "GS"

        edition_cache: dict = {}
        location_cache: dict = {}
        created = updated = skipped = errors = 0
        error_details = []

        for batch_start in range(0, len(all_rows), BATCH_SIZE):
            batch = all_rows[batch_start: batch_start + BATCH_SIZE]

            ext_ids_batch = []
            parsed = []
            for row in batch:
                isbn_raw      = row.get(cols["isbn"] or "", "")
                title_raw     = (row.get(cols["title"] or "", "") or "").strip()
                author_raw    = row.get(cols["author"] or "", "")
                publisher_raw = row.get(cols["publisher"] or "", "")
                year_raw      = row.get(cols["year"] or "", "")
                price_raw     = row.get(cols["price"] or "", "")
                cond_raw      = row.get(cols["condition"] or "", "")
                location_raw  = row.get(cols["location"] or "", "")
                sku_raw       = row.get(cols["sku"] or "", "")

                if not title_raw:
                    parsed.append(None)
                    continue

                isbn      = _normalize_isbn(isbn_raw)
                price     = _parse_price(price_raw)
                year      = _year_from_string(year_raw)
                condition = _map_condition(cond_raw)
                isbn_flag = _classify_isbn(isbn_raw, year)
                section   = location_raw.strip() or "UNKNOWN_SECTION"
                ext_id    = sku_raw or None

                parsed.append({
                    "row": row, "isbn": isbn, "title": title_raw,
                    "author": author_raw or None,
                    "publisher": publisher_raw or None,
                    "year": year, "price": price, "condition": condition,
                    "isbn_flag": isbn_flag, "section": section,
                    "sku_raw": sku_raw, "ext_id": ext_id,
                })
                if ext_id:
                    ext_ids_batch.append(ext_id)

            existing_ext = await _batch_existing_ext_ids("kazam", ext_ids_batch) if not dry_run else set()

            for i, p in enumerate(parsed):
                row_num = batch_start + i + 2
                if p is None:
                    skipped += 1
                    continue
                try:
                    if p["ext_id"] and p["ext_id"] in existing_ext:
                        skipped += 1
                        continue

                    if not dry_run:
                        _, edition_id = await _upsert_edition(
                            p["isbn"], p["title"], p["author"],
                            p["publisher"], p["year"], edition_cache,
                        )
                        location_id = await _get_or_create_location(
                            store_id, p["section"], location_cache
                        )
                        seq = await fetchrow("SELECT nextval('gibson_sku_seq') as seq")
                        sku = f"{prefix}-{seq['seq']}"

                        item_row = await fetchrow(
                            """
                            INSERT INTO gibson_stock_item
                                (edition_id, gibson_sku, store_id, condition_grade,
                                 condition_mode, asking_price, location_id,
                                 trust_tier, kz_status,
                                 shelf_verification_status, isbn_flag)
                            VALUES ($1,$2,$3,$4,'tap',$5,$6,3,$7,'UNVERIFIED',$8)
                            RETURNING stock_item_id
                            """,
                            edition_id, sku, store_id, p["condition"], p["price"],
                            location_id, p["sku_raw"] or None, p["isbn_flag"],
                        )
                        if p["ext_id"]:
                            await execute(
                                "INSERT INTO gibson_source_record "
                                "(source_type, external_id, isbn_norm, raw_data, stock_item_id) "
                                "VALUES ('kazam',$1,$2,$3,$4)",
                                p["ext_id"], p["isbn"],
                                _json.dumps(dict(p["row"])),
                                str(item_row["stock_item_id"]),
                            )
                    created += 1
                except Exception as e:
                    errors += 1
                    if len(error_details) < 20:
                        error_details.append({"row": row_num, "error": str(e)})
                    if errors > 500:
                        _update_job(job_id, status="failed",
                                    error_details=error_details, done=True)
                        return

            processed = min(batch_start + BATCH_SIZE, len(all_rows))
            _update_job(job_id, processed=processed, created=created,
                        updated=updated, skipped=skipped, errors=errors)
            await asyncio.sleep(0)

        _update_job(job_id, status="done", done=True, processed=len(all_rows),
                    created=created, updated=updated, skipped=skipped,
                    errors=errors, error_details=error_details)

    except Exception as e:
        _update_job(job_id, status="failed", done=True,
                    error_details=[{"error": str(e)}])


# ══════════════════════════════════════════════════════════════════
# Endpoints
# ══════════════════════════════════════════════════════════════════

@router.post("/amazon")
async def import_amazon(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    dry_run: bool = Form(False),
    store_id: str = Depends(get_store_id),
):
    """
    Start an Amazon import job. Returns job_id immediately.
    Poll /api/import/status/{job_id} for progress.
    """
    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    job_id = _new_job("amazon", store_id)
    background_tasks.add_task(_process_amazon, text, store_id, dry_run, job_id)
    return {"job_id": job_id, "status": "running", "message": "Import started. Poll /api/import/status/{job_id} for progress."}


@router.post("/kazam")
async def import_kazam(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    dry_run: bool = Form(False),
    store_id: str = Depends(get_store_id),
):
    """
    Start a Ka-Zam import job. Returns job_id immediately.
    Poll /api/import/status/{job_id} for progress.
    """
    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    job_id = _new_job("kazam", store_id)
    background_tasks.add_task(_process_kazam, text, store_id, dry_run, job_id)
    return {"job_id": job_id, "status": "running", "message": "Import started. Poll /api/import/status/{job_id} for progress."}


@router.get("/status/{job_id}")
async def import_status(job_id: str):
    """Poll this for live import progress."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found. Jobs are cleared on server restart.")
    pct = round(job["processed"] / job["total"] * 100, 1) if job.get("total") else 0
    return {**job, "pct": pct}


@router.get("/jobs")
async def list_jobs(store_id: str = Depends(get_store_id)):
    """List all import jobs for this store (most recent first)."""
    jobs = [j for j in _jobs.values() if j.get("store_id") == store_id]
    return {"jobs": sorted(jobs, key=lambda j: j["job_id"], reverse=True)}


@router.get("/preview")
async def preview_file(
    file: UploadFile = File(...),
    source: str = Form("amazon"),
):
    """Return first 5 rows + detected column mapping for UI preview."""
    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    delim = "\t" if "\t" in text.split("\n")[0] else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    headers = reader.fieldnames or []
    field_map = AMAZON_FIELD_MAP if source == "amazon" else KAZAM_FIELD_MAP
    detected = {k: _find_col(headers, v) for k, v in field_map.items()}
    rows = []
    for i, row in enumerate(reader):
        if i >= 5:
            break
        rows.append(dict(row))
    return {"headers": headers, "detected_columns": detected, "preview_rows": rows}

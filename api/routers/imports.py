"""
Gibson Import Router — Amazon TSV + Ka-Zam TSV.

Each row becomes: Work → Edition → Stock Item.

Amazon columns (fixed, from Seller Central flat file):
  product-id   = ISBN
  item-name    = title (may include author at end)
  item-note    = description — section tag at end, e.g. "...description. Poetry/G"
  item-condition = 1-4 numeric
  price        = asking price
  listing-id   = external ID for idempotency
  asin1        = ASIN

Ka-Zam columns (fixed, from Ka-Zam export):
  isbn         = ISBN
  title        = title
  author       = author
  price        = price
  condition    = condition text (Very Good, Good, etc.)
  location     = section / shelf location
  id           = external ID for idempotency

Two import modes:
  1. Direct upload  — POST /api/import/{amazon|kazam}
                      Returns job_id immediately; poll /api/import/status/{job_id}.
                      Requires API to be running during the entire upload.

  2. Queue upload   — Mobile uploads TSV to Supabase Storage, inserts a row in
                      gibson_import_queue directly via Supabase client (no API needed).
                      API background worker picks up PENDING rows, downloads from Storage,
                      and processes them. Mobile polls gibson_import_queue directly.
                      GET /api/import/queue/{queue_id} also available for status.
"""

import asyncio
import csv
import io
import json
import logging
import re
from typing import Optional
from uuid import uuid4

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from api.config import settings
from api.dependencies import get_store_id
from api.database import fetch, fetchrow, execute

logger = logging.getLogger("gibson.imports")
router = APIRouter()

# ── In-memory job tracking (direct-upload mode) ──────────────────
_jobs: dict = {}

def _new_job(source: str, store_id: str) -> dict:
    job_id = str(uuid4())
    _jobs[job_id] = {
        "job_id": job_id, "source": source, "store_id": store_id,
        "status": "running", "done": False,
        "total": 0, "processed": 0,
        "created": 0, "skipped": 0, "errors": 0,
        "pct": 0, "error_details": [],
    }
    return _jobs[job_id]

def _tick(job: dict, result: str, row_num: int, err: str = None):
    job["processed"] += 1
    if result == "created":
        job["created"] += 1
    elif result == "skipped":
        job["skipped"] += 1
    else:
        job["errors"] += 1
        if len(job["error_details"]) < 20:
            job["error_details"].append({"row": row_num, "error": err or result})
    if job["total"] > 0:
        job["pct"] = round(job["processed"] / job["total"] * 100)


# ── Condition maps ───────────────────────────────────────────────
# DB valid values: Fine, Very Good+, Very Good, Good+, Good, Fair, Poor

AMAZON_CONDITION = {
    "1": "Fine",        # Like New
    "11": "Fine",
    "2": "Very Good",
    "3": "Good",
    "4": "Fair",        # Acceptable
}

KAZAM_CONDITION = {
    "like new": "Fine",
    "new": "Fine",
    "fine": "Fine",
    "very good+": "Very Good+",
    "vg+": "Very Good+",
    "very good": "Very Good",
    "vg": "Very Good",
    "good+": "Good+",
    "g+": "Good+",
    "good": "Good",
    "g": "Good",
    "fair": "Fair",
    "acceptable": "Fair",
    "poor": "Poor",
    "reading copy": "Poor",
}


# ── Amazon section extraction ────────────────────────────────────
def _extract_amazon_section(note: str) -> Optional[str]:
    """
    Amazon descriptions end with a shelf tag, e.g.:
      '...Clean pages. Poetry/G'      → 'Poetry'
      '...Tight binding. Mil-Civil-M' → 'Mil-Civil'
      '...Softcover. Sports-Basketball/Bry' → 'Sports-Basketball'

    Pattern: last whitespace-delimited token ends with /Initial or -Initial
    where Initial = 1 uppercase + 0-2 lowercase letters (author's name start).
    """
    if not note:
        return None
    last = note.rstrip(". ").split()[-1] if note.strip() else ""
    m = re.match(r"^(.+)[/\-]([A-Z][a-z]{0,2})$", last)
    if m:
        return m.group(1)
    return None


# ── Row parsers ──────────────────────────────────────────────────
def _parse_amazon(row: dict) -> Optional[dict]:
    isbn = (row.get("product-id") or "").strip()
    if not isbn:
        return None
    if (row.get("status") or "").strip() == "Incomplete":
        return None
    cond = AMAZON_CONDITION.get(str(row.get("item-condition") or "").strip(), "Good")
    return {
        "isbn":        isbn,
        "title":       (row.get("item-name") or "").strip(),
        "author":      None,   # Amazon title field often has author appended — skip for now
        "price":       _to_float(row.get("price")),
        "condition":   cond,
        "section":     _extract_amazon_section(row.get("item-note") or ""),
        "external_id": (row.get("listing-id") or row.get("seller-sku") or "").strip(),
        "asin":        (row.get("asin1") or "").strip(),
        "source":      "amazon",
    }

def _parse_kazam(row: dict) -> Optional[dict]:
    isbn = (row.get("isbn") or "").strip()
    if not isbn:
        return None
    cond = KAZAM_CONDITION.get((row.get("condition") or "").strip().lower(), "Good")
    return {
        "isbn":        isbn,
        "title":       (row.get("title") or "").strip(),
        "author":      (row.get("author") or "").strip() or None,
        "price":       _to_float(row.get("price")),
        "condition":   cond,
        "section":     (row.get("location") or "").strip() or None,
        "external_id": (row.get("id") or "").strip(),
        "asin":        None,
        "source":      "kazam",
    }

def _to_float(val) -> Optional[float]:
    try:
        v = float(str(val or "").strip().lstrip("$"))
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


# ── DB upsert ────────────────────────────────────────────────────
async def _upsert(parsed: dict, store_id: str, store_prefix: str,
                  trust_tier: int, edition_cache: dict,
                  cache_lock: asyncio.Lock = None) -> str:
    """
    Write one book to Work → Edition → Stock Item.
    Returns 'created' or 'skipped'.
    """
    from api.services.barcode import normalize_isbn_13

    isbn_13 = normalize_isbn_13(parsed["isbn"])
    if not isbn_13:
        return "skipped"

    ext_id = parsed.get("external_id") or ""

    # Idempotency — skip if already imported
    if ext_id:
        exists = await fetchrow(
            "SELECT source_record_id FROM gibson_source_record WHERE external_id = $1 AND source = $2",
            ext_id, parsed["source"],
        )
        if exists:
            return "skipped"

    # Find or create Edition — lock prevents concurrent rows with the same ISBN
    # from both missing the cache and racing to insert
    async with (cache_lock or asyncio.Lock()):
        if isbn_13 not in edition_cache:
            row = await fetchrow(
                "SELECT edition_id FROM gibson_edition WHERE isbn_13 = $1", isbn_13
            )
            if not row:
                title = parsed.get("title") or "Untitled"
                title_sort = re.sub(r"^(the|a|an)\s+", "", title.lower()).strip()
                work = await fetchrow(
                    """
                    INSERT INTO gibson_work (title, title_sort, work_type)
                    VALUES ($1, $2, 'monograph') RETURNING work_id
                    """,
                    title, title_sort,
                )
                row = await fetchrow(
                    """
                    INSERT INTO gibson_edition (work_id, isbn_13)
                    VALUES ($1, $2) RETURNING edition_id
                    """,
                    str(work["work_id"]), isbn_13,
                )
                # Attach author if we have one (Ka-Zam provides this)
                if parsed.get("author"):
                    author = parsed["author"]
                    parts = author.rsplit(" ", 1)
                    name_sort = f"{parts[-1]}, {parts[0]}" if len(parts) > 1 else author
                    agent = await fetchrow(
                        "SELECT agent_id FROM gibson_agent WHERE name_display = $1", author
                    )
                    if not agent:
                        agent = await fetchrow(
                            """
                            INSERT INTO gibson_agent (name_display, name_sort, agent_type)
                            VALUES ($1, $2, 'person') RETURNING agent_id
                            """,
                            author, name_sort,
                        )
                    await execute(
                        """
                        INSERT INTO gibson_work_agent (work_id, agent_id, role, role_order)
                        VALUES ($1, $2, 'author', 1) ON CONFLICT DO NOTHING
                        """,
                        str(work["work_id"]), str(agent["agent_id"]),
                    )
            edition_cache[isbn_13] = str(row["edition_id"])

    edition_id = edition_cache[isbn_13]

    # Find or create location
    location_id = None
    if parsed.get("section"):
        loc = await fetchrow(
            "SELECT location_id FROM gibson_location WHERE store_id = $1 AND section = $2",
            store_id, parsed["section"],
        )
        if not loc:
            loc = await fetchrow(
                """
                INSERT INTO gibson_location (store_id, section, section_code)
                VALUES ($1, $2, $3) RETURNING location_id
                """,
                store_id, parsed["section"],
                parsed["section"][:6].upper().replace(" ", ""),
            )
        location_id = str(loc["location_id"])

    # SKU — bulk imports use "IMP" pseudo-initials per standing decision
    # (canonical format is initials-seq; store prefix is only the tap-in fallback)
    seq = await fetchrow("SELECT nextval('gibson_sku_seq') AS seq")
    sku = f"IMP-{seq['seq']}"

    # Create stock item
    item = await fetchrow(
        """
        INSERT INTO gibson_stock_item (
            edition_id, gibson_sku, store_id,
            condition_grade, condition_mode,
            asking_price, location_id,
            trust_tier, shelf_verification_status,
            amazon_listing_id, amazon_asin
        ) VALUES ($1,$2,$3,$4,'tap',$5,$6,$7,'UNVERIFIED',$8,$9)
        RETURNING stock_item_id
        """,
        edition_id, sku, store_id,
        parsed["condition"], parsed.get("price"),
        location_id, trust_tier,
        ext_id if parsed["source"] == "amazon" else None,
        parsed.get("asin") or None,
    )

    # Record source for idempotency + audit
    await execute(
        """
        INSERT INTO gibson_source_record
            (source, external_id, isbn_norm, raw_data, stock_item_id)
        VALUES ($1, $2, $3, $4::jsonb, $5)
        """,
        parsed["source"],
        ext_id or None,
        isbn_13,
        json.dumps({"title": parsed.get("title"), "source": parsed["source"]}),
        str(item["stock_item_id"]),
    )

    return "created"


# ── Background processors ────────────────────────────────────────
BATCH_SIZE = 25  # concurrent rows per batch — safe for Supabase connection limits

async def _process(job: dict, content: bytes, parser, trust_tier: int):
    store_id = job["store_id"]
    try:
        text = content.decode("utf-8", errors="replace")
        reader = list(csv.DictReader(io.StringIO(text), delimiter="\t"))
        job["total"] = len(reader)

        prefix_row = await fetchrow(
            "SELECT prefix FROM gibson_store WHERE store_id = $1", store_id
        )
        store_prefix = prefix_row["prefix"] if prefix_row else "GS"

        edition_cache: dict = {}
        cache_lock = asyncio.Lock()

        # Process in batches of BATCH_SIZE rows concurrently
        for batch_start in range(0, len(reader), BATCH_SIZE):
            batch = reader[batch_start:batch_start + BATCH_SIZE]

            async def _handle_row(i, row):
                try:
                    parsed = parser(row)
                    if parsed is None:
                        _tick(job, "skipped", i + 1)
                        return
                    result = await _upsert(parsed, store_id, store_prefix, trust_tier, edition_cache, cache_lock)
                    _tick(job, result, i + 1)
                except Exception as e:
                    _tick(job, "error", i + 1, str(e)[:120])

            await asyncio.gather(*[
                _handle_row(batch_start + i, row)
                for i, row in enumerate(batch)
            ])

        job["status"] = "done"
        job["done"] = True
        job["pct"] = 100

    except Exception as e:
        job["status"] = "failed"
        job["done"] = True
        job["error_details"].append({"row": 0, "error": str(e)})


# ── Endpoints ────────────────────────────────────────────────────
@router.post("/amazon")
async def import_amazon(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    store_id: str = Depends(get_store_id),
):
    """Upload Amazon Seller Central flat-file TSV."""
    content = await file.read()
    job = _new_job("amazon", store_id)
    background_tasks.add_task(_process, job, content, _parse_amazon, 2)
    return {"job_id": job["job_id"], "status": "running"}


@router.post("/kazam")
async def import_kazam(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    store_id: str = Depends(get_store_id),
):
    """Upload Ka-Zam inventory export TSV/CSV."""
    content = await file.read()
    job = _new_job("kazam", store_id)
    background_tasks.add_task(_process, job, content, _parse_kazam, 3)
    return {"job_id": job["job_id"], "status": "running"}


@router.get("/status/{job_id}")
async def import_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs")
async def list_jobs():
    return list(_jobs.values())


# ── Queue-based import (Supabase Storage) ────────────────────────
# Mobile uploads the file directly to Supabase Storage, then inserts
# a row in gibson_import_queue. The worker below picks it up.

STORAGE_BUCKET = "gibson-imports"
QUEUE_POLL_INTERVAL = 30  # seconds between worker sweeps


async def _download_from_storage(storage_path: str) -> bytes:
    """Download a file from Supabase Storage using the service role key."""
    url = f"{settings.supabase_url}/storage/v1/object/{STORAGE_BUCKET}/{storage_path}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {settings.supabase_service_role_key}"},
        )
        resp.raise_for_status()
        return resp.content


async def _process_queue_item(queue_id: str) -> None:
    """Download + process one queue row. Updates the row with progress/results."""

    # Claim the row (PENDING → PROCESSING)
    row = await fetchrow(
        """
        UPDATE gibson_import_queue
           SET status = 'PROCESSING', updated_at = now()
         WHERE queue_id = $1 AND status = 'PENDING'
        RETURNING queue_id, store_id, source, storage_path, filename
        """,
        queue_id,
    )
    if not row:
        return  # already claimed by another worker instance

    logger.info("Processing import queue item %s (%s / %s)", queue_id, row["source"], row["filename"])

    parser = _parse_amazon if row["source"] == "amazon" else _parse_kazam
    trust_tier = 2 if row["source"] == "amazon" else 3

    # Build a synthetic job dict so we can reuse _process() unchanged
    job = {
        "job_id": queue_id, "source": row["source"], "store_id": str(row["store_id"]),
        "status": "running", "done": False,
        "total": 0, "processed": 0,
        "created": 0, "skipped": 0, "errors": 0,
        "pct": 0, "error_details": [],
    }

    async def _flush_progress():
        """Write current job counters to the DB row every ~2 s during processing."""
        await execute(
            """
            UPDATE gibson_import_queue
               SET total = $2, processed = $3, created = $4,
                   skipped = $5, errors = $6, pct = $7,
                   error_details = $8::jsonb, updated_at = now()
             WHERE queue_id = $1
            """,
            queue_id,
            job["total"], job["processed"], job["created"],
            job["skipped"], job["errors"], job["pct"],
            json.dumps(job["error_details"]),
        )

    try:
        content = await _download_from_storage(row["storage_path"])

        # Run the existing batch processor — it mutates `job` in place
        await _process(job, content, parser, trust_tier)

        final_status = "DONE" if job["status"] == "done" else "FAILED"
        await execute(
            """
            UPDATE gibson_import_queue
               SET status = $2, total = $3, processed = $4, created = $5,
                   skipped = $6, errors = $7, pct = $8,
                   error_details = $9::jsonb, updated_at = now()
             WHERE queue_id = $1
            """,
            queue_id, final_status,
            job["total"], job["processed"], job["created"],
            job["skipped"], job["errors"], job["pct"],
            json.dumps(job["error_details"]),
        )
        logger.info(
            "Queue item %s %s — created=%d skipped=%d errors=%d",
            queue_id, final_status, job["created"], job["skipped"], job["errors"],
        )

    except Exception as exc:
        logger.exception("Queue item %s failed: %s", queue_id, exc)
        await execute(
            """
            UPDATE gibson_import_queue
               SET status = 'FAILED',
                   error_details = $2::jsonb,
                   updated_at = now()
             WHERE queue_id = $1
            """,
            queue_id,
            json.dumps([{"row": 0, "error": str(exc)[:200]}]),
        )


async def queue_worker() -> None:
    """
    Background task. Runs for the lifetime of the API process.
    Polls gibson_import_queue every QUEUE_POLL_INTERVAL seconds for PENDING rows
    and processes them one by one (safe for a single API process; extend with
    row-level locking if multiple workers are ever needed).
    """
    logger.info("Import queue worker started (interval=%ds)", QUEUE_POLL_INTERVAL)
    while True:
        try:
            pending = await fetch(
                """
                SELECT queue_id FROM gibson_import_queue
                 WHERE status = 'PENDING'
                 ORDER BY created_at
                 LIMIT 5
                """,
            )
            for row in pending:
                await _process_queue_item(str(row["queue_id"]))
        except Exception as exc:
            logger.warning("Queue worker sweep error: %s", exc)

        await asyncio.sleep(QUEUE_POLL_INTERVAL)


# ── Queue status endpoint ─────────────────────────────────────────

@router.get("/queue/{queue_id}")
async def queue_status(queue_id: str):
    """Status of a Supabase-Storage-based import queue item."""
    row = await fetchrow(
        """
        SELECT queue_id, store_id, source, filename, status,
               total, processed, created, skipped, errors, pct,
               error_details, created_at, updated_at
          FROM gibson_import_queue
         WHERE queue_id = $1
        """,
        queue_id,
    )
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Queue item not found")
    return dict(row)

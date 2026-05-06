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

Upload returns a job_id immediately. Poll /api/import/status/{job_id} for progress.
"""

import csv
import io
import json
import re
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from api.dependencies import get_store_id
from api.database import fetch, fetchrow, execute

router = APIRouter()

# ── In-memory job tracking ───────────────────────────────────────
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
                  trust_tier: int, edition_cache: dict) -> str:
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

    # Find or create Edition (cached by ISBN to avoid repeat lookups)
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

        for i, row in enumerate(reader):
            try:
                parsed = parser(row)
                if parsed is None:
                    _tick(job, "skipped", i + 1)
                    continue
                result = await _upsert(parsed, store_id, store_prefix, trust_tier, edition_cache)
                _tick(job, result, i + 1)
            except Exception as e:
                _tick(job, "error", i + 1, str(e)[:120])

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

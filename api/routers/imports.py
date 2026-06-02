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


# ── Amazon section + note extraction ────────────────────────────
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


def _amazon_condition_note(note: str) -> Optional[str]:
    """
    Return the Amazon item-note with the trailing shelf tag stripped.
      'Light wear. Clean pages. Poetry/G' → 'Light wear. Clean pages.'
    If no tag is found, return the note as-is.
    """
    if not note or not note.strip():
        return None
    stripped = note.rstrip(". ")
    parts = stripped.rsplit(" ", 1)
    if len(parts) == 2 and re.match(r"^(.+)[/\-]([A-Z][a-z]{0,2})$", parts[1]):
        return parts[0].strip() or None
    return note.strip() or None


# ── Row parsers ──────────────────────────────────────────────────
def _parse_amazon(row: dict) -> Optional[dict]:
    isbn = (row.get("product-id") or "").strip()
    if not isbn:
        return None
    if (row.get("status") or "").strip() == "Incomplete":
        return None
    cond = AMAZON_CONDITION.get(str(row.get("item-condition") or "").strip(), "Good")
    note = (row.get("item-note") or "").strip()
    return {
        "isbn":            isbn,
        "title":           (row.get("item-name") or "").strip(),
        "author":          None,   # Amazon title field often has author appended — skip for now
        "publisher":       (row.get("publisher") or "").strip() or None,
        "condition_notes": _amazon_condition_note(note),
        "price":           _to_float(row.get("price")),
        "condition":       cond,
        "section":         _extract_amazon_section(note),
        "external_id":     (row.get("listing-id") or row.get("seller-sku") or "").strip(),
        "asin":            (row.get("asin1") or "").strip(),
        "source":          "amazon",
    }

def _parse_kazam(row: dict) -> Optional[dict]:
    isbn = (row.get("isbn") or "").strip()
    if not isbn:
        return None
    cond = KAZAM_CONDITION.get((row.get("condition") or "").strip().lower(), "Good")
    return {
        "isbn":            isbn,
        "title":           (row.get("title") or "").strip(),
        "author":          (row.get("author") or "").strip() or None,
        "publisher":       (row.get("publisher") or "").strip() or None,
        "condition_notes": (row.get("description") or "").strip() or None,
        "price":           _to_float(row.get("price")),
        "condition":       cond,
        "section":         (row.get("location") or "").strip() or None,
        "external_id":     (row.get("id") or "").strip(),
        "asin":            None,
        "source":          "kazam",
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


# ── Bulk import pipeline ─────────────────────────────────────────
# ~9 DB round trips regardless of file size.
# Old row-by-row approach was 6 × N round trips (600k for 100k rows).

async def _process(job: dict, content: bytes, parser, trust_tier: int):
    import uuid as _uuid
    from api.services.barcode import normalize_isbn_13

    store_id = job["store_id"]
    source   = job["source"]

    try:
        # ── 1. Parse all rows in memory ──────────────────────────────
        # Normalize line endings and strip null bytes.
        # Amazon files often have \r\n (Windows) or bare \r, and occasionally
        # contain 0x00 bytes that PostgreSQL rejects as invalid UTF-8.
        text = (content.decode("utf-8", errors="replace")
                .replace('\x00', '')
                .replace('\r\n', '\n')
                .replace('\r', '\n'))
        parsed_all = [
            p for p in (parser(row) for row in csv.DictReader(io.StringIO(text), delimiter="\t"))
            if p is not None
        ]
        for p in parsed_all:
            p["isbn_13"] = normalize_isbn_13(p["isbn"])
        parsed_all = [p for p in parsed_all if p["isbn_13"]]

        job["total"] = len(parsed_all)
        if not parsed_all:
            job.update(status="done", done=True, pct=100)
            return

        # ── 2. Idempotency — one query for all external_ids ──────────
        ext_ids = [p["external_id"] for p in parsed_all if p.get("external_id")]
        already_done: set = set()
        if ext_ids:
            found = await fetch(
                "SELECT external_id FROM gibson_source_record "
                "WHERE external_id = ANY($1) AND source = $2",
                ext_ids, source,
            )
            already_done = {r["external_id"] for r in found}

        parsed = [
            p for p in parsed_all
            if not p.get("external_id") or p["external_id"] not in already_done
        ]
        job["skipped"] = len(parsed_all) - len(parsed)
        job["pct"] = 10

        # ── 2b. Backfill condition_notes on already-imported stock items ──
        # For rows we're skipping (already in DB), update condition_notes
        # where it's currently NULL so a re-upload fills it in.
        already_with_notes = [
            p for p in parsed_all
            if p.get("external_id") in already_done and p.get("condition_notes")
        ]
        if already_with_notes:
            bf_ext_ids = [p["external_id"] for p in already_with_notes]
            bf_notes   = [p["condition_notes"] for p in already_with_notes]
            await execute(
                """
                UPDATE gibson_stock_item si
                SET condition_notes = matched.note
                FROM (
                    SELECT sr.stock_item_id, v.note
                    FROM unnest($1::text[], $2::text[]) AS v(external_id, note)
                    JOIN gibson_source_record sr
                      ON sr.external_id = v.external_id AND sr.source = $3
                ) matched
                WHERE si.stock_item_id = matched.stock_item_id
                  AND si.condition_notes IS NULL
                """,
                bf_ext_ids, bf_notes, source,
            )

        if not parsed:
            job.update(status="done", done=True, pct=100, processed=job["total"])
            return

        # ── 3. Find existing editions — one query for all ISBNs ──────
        all_isbns = list({p["isbn_13"] for p in parsed})
        ed_rows = await fetch(
            "SELECT isbn_13, edition_id FROM gibson_edition WHERE isbn_13 = ANY($1)",
            all_isbns,
        )
        edition_map: dict = {r["isbn_13"]: str(r["edition_id"]) for r in ed_rows}
        job["pct"] = 20

        # ── 4. Bulk-create missing works + editions ───────────────────
        # One representative row per new ISBN (first occurrence wins for title/author)
        new_isbn_rep: dict = {}
        for p in parsed:
            if p["isbn_13"] not in edition_map and p["isbn_13"] not in new_isbn_rep:
                new_isbn_rep[p["isbn_13"]] = p

        if new_isbn_rep:
            isbn_list    = list(new_isbn_rep.keys())
            # Pre-assign work UUIDs so we can link editions without relying on
            # RETURNING row order — join on isbn_13 instead.
            pre_wids     = [str(_uuid.uuid4()) for _ in isbn_list]
            titles       = [new_isbn_rep[i].get("title") or "Untitled" for i in isbn_list]
            title_sorts  = [
                re.sub(r"^(the|a|an)\s+", "",
                       (new_isbn_rep[i].get("title") or "untitled").lower()).strip()
                for i in isbn_list
            ]

            await execute(
                "INSERT INTO gibson_work (work_id, title, title_sort, work_type) "
                "SELECT * FROM unnest($1::uuid[], $2::text[], $3::text[], $4::text[])",
                pre_wids, titles, title_sorts, ["monograph"] * len(isbn_list),
            )
            new_eds = await fetch(
                "INSERT INTO gibson_edition (work_id, isbn_13) "
                "SELECT * FROM unnest($1::uuid[], $2::text[]) "
                "RETURNING isbn_13, edition_id",
                pre_wids, isbn_list,
            )
            for r in new_eds:
                edition_map[r["isbn_13"]] = str(r["edition_id"])

            # Bulk authors — Ka-Zam provides these; Amazon doesn't
            author_pairs = [
                (pre_wids[i], new_isbn_rep[isbn]["author"])
                for i, isbn in enumerate(isbn_list)
                if new_isbn_rep[isbn].get("author")
            ]
            if author_pairs:
                unique_authors = list({a for _, a in author_pairs})
                ex_agents = await fetch(
                    "SELECT agent_id, name_display FROM gibson_agent "
                    "WHERE name_display = ANY($1)",
                    unique_authors,
                )
                agent_map: dict = {r["name_display"]: str(r["agent_id"]) for r in ex_agents}

                new_authors = [a for a in unique_authors if a not in agent_map]
                if new_authors:
                    name_sorts = [
                        (lambda p: f"{p[-1]}, {p[0]}" if len(p) > 1 else p[0])(a.rsplit(" ", 1))
                        for a in new_authors
                    ]
                    ag_rows = await fetch(
                        "INSERT INTO gibson_agent (name_display, name_sort, agent_type) "
                        "SELECT * FROM unnest($1::text[], $2::text[], $3::text[]) "
                        "RETURNING agent_id, name_display",
                        new_authors, name_sorts, ["person"] * len(new_authors),
                    )
                    for r in ag_rows:
                        agent_map[r["name_display"]] = str(r["agent_id"])

                wa_wids = [wid for wid, a in author_pairs if a in agent_map]
                wa_aids = [agent_map[a] for _, a in author_pairs if a in agent_map]
                if wa_wids:
                    await execute(
                        "INSERT INTO gibson_work_agent (work_id, agent_id, role, role_order) "
                        "SELECT * FROM unnest($1::uuid[], $2::uuid[], $3::text[], $4::int[]) "
                        "ON CONFLICT DO NOTHING",
                        wa_wids, wa_aids, ["author"] * len(wa_wids), [1] * len(wa_wids),
                    )

        job["pct"] = 40

        # ── 4b. Upsert publishers ─────────────────────────────────────
        # Runs on parsed_all (includes already-imported rows) so re-uploading
        # the same file backfills publisher on existing editions.
        # ON CONFLICT DO NOTHING makes every run idempotent.
        pub_by_isbn: dict = {}   # isbn_13 → publisher name (first non-null wins)
        for p in parsed_all:
            if p.get("publisher") and p.get("isbn_13") and p["isbn_13"] not in pub_by_isbn:
                pub_by_isbn[p["isbn_13"]] = p["publisher"]

        if pub_by_isbn:
            # Re-fetch edition_ids for all ISBNs (includes pre-existing editions)
            pub_ed_rows = await fetch(
                "SELECT isbn_13, edition_id FROM gibson_edition WHERE isbn_13 = ANY($1)",
                list(pub_by_isbn.keys()),
            )
            pub_edition_map = {r["isbn_13"]: str(r["edition_id"]) for r in pub_ed_rows}

            unique_pub_names = list({v for v in pub_by_isbn.values()})

            # Find existing publisher records by name
            ex_pubs = await fetch(
                "SELECT publisher_id, name_display FROM gibson_publisher WHERE name_display = ANY($1)",
                unique_pub_names,
            )
            pub_map = {r["name_display"]: str(r["publisher_id"]) for r in ex_pubs}

            # Create any publishers not yet in the DB
            new_pub_names = [n for n in unique_pub_names if n not in pub_map]
            if new_pub_names:
                new_pubs = await fetch(
                    "INSERT INTO gibson_publisher (name_display, name_sort, publisher_type) "
                    "SELECT * FROM unnest($1::text[], $2::text[], $3::text[]) "
                    "RETURNING publisher_id, name_display",
                    new_pub_names,
                    [n.lower() for n in new_pub_names],
                    ["commercial"] * len(new_pub_names),
                )
                for r in new_pubs:
                    pub_map[r["name_display"]] = str(r["publisher_id"])

            # Link editions → publishers (ON CONFLICT DO NOTHING = safe to re-run)
            ep_eids = []
            ep_pids = []
            for isbn, pub_name in pub_by_isbn.items():
                eid = pub_edition_map.get(isbn)
                pid = pub_map.get(pub_name)
                if eid and pid:
                    ep_eids.append(eid)
                    ep_pids.append(pid)

            if ep_eids:
                await execute(
                    "INSERT INTO gibson_edition_publisher (edition_id, publisher_id, role) "
                    "SELECT * FROM unnest($1::uuid[], $2::uuid[], $3::text[]) "
                    "ON CONFLICT DO NOTHING",
                    ep_eids, ep_pids, ["publisher"] * len(ep_eids),
                )

        # ── 5. Locations — 2 queries ──────────────────────────────────
        unique_sections = list({p["section"] for p in parsed if p.get("section")})
        location_map: dict = {}
        if unique_sections:
            ex_locs = await fetch(
                "SELECT location_id, section FROM gibson_location "
                "WHERE store_id = $1 AND section = ANY($2)",
                store_id, unique_sections,
            )
            location_map = {r["section"]: str(r["location_id"]) for r in ex_locs}

            new_secs = [s for s in unique_sections if s not in location_map]
            if new_secs:
                new_locs = await fetch(
                    "INSERT INTO gibson_location (store_id, section, section_code) "
                    "SELECT * FROM unnest($1::uuid[], $2::text[], $3::text[]) "
                    "RETURNING location_id, section",
                    [store_id] * len(new_secs),
                    new_secs,
                    [s[:6].upper().replace(" ", "") for s in new_secs],
                )
                for r in new_locs:
                    location_map[r["section"]] = str(r["location_id"])

        job["pct"] = 50

        # ── 6. Allocate all SKUs in one query ─────────────────────────
        n = len(parsed)
        seq_rows = await fetch(
            "SELECT nextval('gibson_sku_seq') AS seq FROM generate_series(1, $1)", n
        )
        skus = [f"IMP-{r['seq']}" for r in seq_rows]
        job["pct"] = 60

        # ── 7. Bulk insert stock items — one query ────────────────────
        ed_ids, sku_l, sid_l, cond_l, mode_l = [], [], [], [], []
        price_l, loc_l, tier_l, vstat_l      = [], [], [], []
        azid_l, asin_l, cnotes_l             = [], [], []
        valid: list = []

        for p, sku in zip(parsed, skus):
            eid = edition_map.get(p["isbn_13"])
            if not eid:
                job["errors"] += 1
                continue
            ed_ids.append(eid);       sku_l.append(sku)
            sid_l.append(store_id);   cond_l.append(p["condition"])
            mode_l.append("tap");     price_l.append(p.get("price"))
            loc_l.append(location_map.get(p.get("section") or ""))
            tier_l.append(trust_tier); vstat_l.append("UNVERIFIED")
            azid_l.append(p.get("external_id") if p["source"] == "amazon" else None)
            asin_l.append(p.get("asin") or None)
            cnotes_l.append(p.get("condition_notes") or None)
            valid.append(p)

        # ── 7+8. Chunked stock items + source records ─────────────────
        # Insert in chunks of 5k to stay well within asyncpg/Postgres message
        # size limits (large files with long titles can exceed them in one shot).
        CHUNK = 5_000
        item_rows = []

        for start in range(0, len(ed_ids), CHUNK):
            sl = slice(start, start + CHUNK)
            chunk_items = await fetch(
                """
                INSERT INTO gibson_stock_item (
                    edition_id, gibson_sku, store_id,
                    condition_grade, condition_mode,
                    asking_price, location_id,
                    trust_tier, shelf_verification_status,
                    amazon_listing_id, amazon_asin,
                    condition_notes
                )
                SELECT * FROM unnest(
                    $1::uuid[],  $2::text[],  $3::uuid[],
                    $4::text[],  $5::text[],
                    $6::float8[], $7::uuid[],
                    $8::int[],   $9::text[],
                    $10::text[], $11::text[],
                    $12::text[]
                )
                RETURNING stock_item_id
                """,
                ed_ids[sl], sku_l[sl], sid_l[sl],
                cond_l[sl], mode_l[sl],
                price_l[sl], loc_l[sl],
                tier_l[sl], vstat_l[sl],
                azid_l[sl], asin_l[sl],
                cnotes_l[sl],
            )
            item_rows.extend(chunk_items)
            job["pct"] = 60 + round(20 * (start + len(chunk_items)) / max(len(ed_ids), 1))

            valid_sl  = valid[sl]
            await execute(
                "INSERT INTO gibson_source_record "
                "    (source, external_id, isbn_norm, raw_data, stock_item_id) "
                "SELECT * FROM unnest($1::text[], $2::text[], $3::text[], $4::jsonb[], $5::uuid[])",
                [p["source"] for p in valid_sl],
                [p.get("external_id") or None for p in valid_sl],
                [p["isbn_13"] for p in valid_sl],
                [json.dumps({"title": p.get("title"), "source": p["source"]}) for p in valid_sl],
                [str(r["stock_item_id"]) for r in chunk_items],
            )

        job["created"]   = len(item_rows)
        job["processed"] = job["total"]
        job["pct"]       = 100
        job["status"]    = "done"
        job["done"]      = True

    except Exception as e:
        job["status"] = "failed"
        job["done"]   = True
        job["error_details"].append({"row": 0, "error": repr(e)[:400]})


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

    parser     = _parse_amazon if row["source"] == "amazon" else _parse_kazam
    trust_tier = 2 if row["source"] == "amazon" else 3

    job = {
        "job_id": queue_id, "source": row["source"], "store_id": str(row["store_id"]),
        "status": "running", "done": False,
        "total": 0, "processed": 0,
        "created": 0, "skipped": 0, "errors": 0,
        "pct": 0, "error_details": [],
    }

    async def _flush():
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

    # Flush progress every 3s while _process runs — mobile sees live updates
    async def _periodic_flush():
        try:
            while not job["done"]:
                await asyncio.sleep(3)
                await _flush()
        except asyncio.CancelledError:
            pass

    flush_task = asyncio.create_task(_periodic_flush())

    try:
        content = await _download_from_storage(row["storage_path"])
        await _process(job, content, parser, trust_tier)

        flush_task.cancel()
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
        flush_task.cancel()
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

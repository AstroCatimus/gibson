# CLAUDE.md — Gibson Rebuild Specification

**Alexandria Book Co-op  ·  Gibson v2  ·  May 2026**

> This document is the source of truth for rebuilding Gibson on the architecture decided in the May 2026 strategy conversations. It supersedes `CLAUDE.md` (v1), `Nova_Gibson_Build_Brief_v2.docx`, and `Gibson_Cloud_First_Build.docx` where they conflict. Where they agree, this document is the durable expression of the decision.
>
> Audience: Nova (CTO, primary builder), Eddy (operational review), future bookseller-members and developers who join the project.
>
> Read all the way through before touching code. The architectural decisions are interlocking; partial implementation produces incoherent behavior.

---

## Table of Contents

1. [The Job and the Year 1 Strategy](#1-the-job-and-the-year-1-strategy)
2. [Standing Decisions — Do Not Re-Litigate](#2-standing-decisions--do-not-re-litigate)
3. [Tech Stack](#3-tech-stack)
4. [The Two Stores](#4-the-two-stores)
5. [Data Model](#5-data-model)
6. [The Identification Pipeline](#6-the-identification-pipeline)
7. [The Pricing Layer](#7-the-pricing-layer)
8. [The Condition System](#8-the-condition-system)
9. [The Application — Phone Layout](#9-the-application--phone-layout)
10. [The Application — Desktop Layout](#10-the-application--desktop-layout)
11. [Cooperative Data Governance](#11-cooperative-data-governance)
12. [Data Acquisition and Bibliographic Foundation](#12-data-acquisition-and-bibliographic-foundation)
13. [Migration Path to Local Hardware](#13-migration-path-to-local-hardware)
14. [Build Sequence — What Gets Built When](#14-build-sequence--what-gets-built-when)
15. [Environment Variables](#15-environment-variables)
16. [Acceptance Criteria](#16-acceptance-criteria)

---

## 1. The Job and the Year 1 Strategy

### 1.1 The Job

Build Gibson well enough that a bookseller can pick up a book, photograph it, identify it, price it, and list it — faster and more accurately than any existing tool — from a system the cooperative actually owns.

The test is not lines of code or features on a list. The test is whether Eddy picks it up in the warehouse and it makes his day easier. Whether Kim can use it at the counter without thinking about it. Whether the apprentices can be trained on it in a week.

### 1.2 The Year 1 Strategy: Cloud-First on Anthropic

Year 1 (May 2026 – April 2027) runs entirely on cloud infrastructure with Anthropic's Claude as the reasoning layer. The local server arrives in late summer and migration completes by year-end, but Year 1 is fully operational on cloud from Day 1.

This is a deliberate strategy, not a compromise. The reasoning:

- **Speed of execution.** Cloud lets the apprentices learn cataloguing on real inventory in Month 1, not Month 7.
- **Training data accumulation.** Every cataloguing call generates structured training data that migrates intact to the local server. By migration day there are ~219,000 books worth of corrections, conversations, and confidence signals waiting for the first QLoRA run.
- **Cost is manageable.** Year 1 cloud budget is $9,000–$13,500 all-in across both stores at full production pace. This is roughly 1–3% of the inventory throughput value the system processes.
- **Architecture is migration-ready.** Every external service endpoint is configurable. Migration day is config changes, not a rewrite.

The local-first values commitment is unchanged. Year 1 cloud-first is the bridge that makes local-first achievable. See `Gibson_Year_One_Budget.docx` for the full cost analysis.

### 1.3 What Year 1 Produces

- Working cataloguing tool deployed at Driftless Books and Metaphysical Graffiti
- ~219,000 books catalogued across both stores at full pace
- Canonical bibliographic dataset built from LOC + Open Library + HathiTrust deduplication
- The 100-bibliography corpus read, structured, and stored as RAG fuel + training pairs
- Six months minimum of accumulated training data ready for local Llama
- A cooperative data governance model proven against real member-data privacy requirements
- Migration to local hardware completes by April 2027

---

## 2. Standing Decisions — Do Not Re-Litigate

These have been settled across multiple revisions. Building against them is required. Changing them requires explicit Eddy override.

| Decision | Source |
|---|---|
| Local-first is a values commitment, not just a technical preference | Founding board principle |
| 24 GB VRAM is the non-negotiable floor for local hardware | `nova_hardware_spec.docx` |
| Schema is Work → Edition → Stock Item (FRBR-aligned), originated by Mitch | `Gibson_Pipeline_Complete_v2.docx` |
| Source records are immutable, preserved as JSONB blobs | `Gibson_Data_Acquisition_Operating_Instructions.docx` |
| Vialibri is the pricing gate | `nova_pricing_and_agent.docx` |
| Pricing is Day 1, not Month 7 | Standing |
| Cost basis never leaves the owning store | Cooperative governance |
| Cooperative data governance enforced at the database query level | Standing |
| Ghost Book is a first-class pipeline path, not an edge case | `Gibson_Pre_Launch_Development_Outline.docx` |
| Dust jacket is bibliographic for pre-1970 hardcovers | Recent decision, `BUILD_PLAN.md` Item 21 |
| Every cataloguing action is simultaneously a listing action | Standing |
| AI output never writes directly to the catalog without human review | Standing |
| Honest uncertainty over false confidence in every output | Standing |
| Cover-first protocol — one photo resolves 75–80% of non-barcode books | Recent refinement |
| Field-tool pricing and research pricing share no code paths | Architectural invariant |
| eBay Finding API dependency forbidden — decommissioned without notice | Risk-driven |
| AbeBooks structural dependency forbidden — Amazon-owned | Values |

---

## 3. Tech Stack

### 3.1 Backend
- **Language:** Python 3.11+
- **Framework:** FastAPI with `asyncpg` for database access
- **No ORM.** Direct SQL via asyncpg. ORMs hide query plans and degrade at the volume Gibson operates at.
- **Job orchestration:** Apache Airflow (after Month 4) for bibliographic ingest DAGs and the slow-path research queue. Cron is acceptable for Month 1–3 prototyping.

### 3.2 Frontend
- **Type:** Progressive Web App (PWA), vanilla JavaScript, no framework
- **Why no framework:** The PWA is mobile-first and the rendering surface is small. React/Vue add weight, complexity, and dependency footprint without earning their keep at this scale.
- **Camera access:** Browser MediaDevices API. No app-store install. Works on iOS and Android.
- **Layouts:** Three responsive breakpoints — phone (< 640px), tablet (640–1024px), desktop (> 1024px). See sections 9 and 10.

### 3.3 Database
- **Engine:** PostgreSQL 15+
- **Hosting (Year 1):** Supabase Pro — managed PostgreSQL, $25/month base, $0.125/GB/month overage
- **Hosting (post-migration):** Local PostgreSQL on Driftless server
- **Extensions:** pgvector (for embeddings, post-migration), pg_trgm (for fuzzy text matching), uuid-ossp

### 3.4 AI / Reasoning Layer (Year 1)
- **Default vision and reasoning model:** `claude-sonnet-4-6`
  - Full cataloguing path (300 books/day average)
  - Bibliographic field extraction
  - Multi-source synthesis when low-confidence
  - Conversational Q&A on hard cases
- **Triage and classification:** `claude-haiku-4-5-20251001`
  - Fast triage decisions ("$5 fiction, shelve it")
  - Bibliographic dedup adjudication (90% of pairs)
  - Research-agent search reasoning
  - Voice transcription cleanup
- **Escalation for hard cases:** `claude-opus-4-7` — reserved for the genuinely difficult (rare antiquarian, multi-source contradiction, Ghost Book deep research)
- **Prompt caching:** active throughout. Cache the system prompt prefix on every call. Target ~95% cache hit rate in steady state.
- **Batch API:** used for all asynchronous workloads (overnight research, dedup adjudication, 100-bibliography ingest). 50% off both input and output.

### 3.5 AI / Reasoning Layer (Post-Migration)
- **Local model:** Ollama + Llama 3.1 70B (Q4 quantized) on dual RTX 3090, OR Llama 3 8B on single 4090 if dual-3090 not feasible
- **Local fallback:** Claude API still available for genuinely hard cases — the architecture supports hybrid routing
- **Cover matching:** CLIP ViT-L/14 (built post-migration when image corpus exceeds 50K images)
- **OCR ensemble:** PaddleOCR-VL-0.9B as primary (per `Nova_OCR_Memo.docx`), Calamari fraktur19 for German Fraktur, Transkribus API for handwriting

### 3.6 External Services
- **Object storage:** Cloudflare R2 (Year 1) → local `/data/images` (post-migration). $0.015/GB/month, zero egress fees.
- **Application hosting:** Railway (Year 1) → systemd service on Driftless server (post-migration). $10–20/month.
- **Research VM:** Hetzner CX22 — runs ScrapeGraphAI, smolagents, Playwright for the slow-path agent. CPU-only, $5/month.
- **Pricing APIs:** BooksRun (free), BookScouter Cached + Historic (paid tier), Keepa (optional), Vialibri (status unconfirmed), Heritage Auctions API (Year 2–3).

### 3.7 Code Conventions
- This is not a prototype. Write production code from Day 1.
- Every external service endpoint is a configurable environment variable.
- Every API call wraps with retry logic, timeout, and graceful degradation.
- Every database query that touches Stock Item includes `store_id` filter.
- Every conversation is logged in full (multi-turn schema, see § 5.4).
- Every correction generates a training pair (`is_training_pair = true`).

---

## 4. The Two Stores

| Store | Address | SKU prefix | Inventory state |
|---|---|---|---|
| **Driftless Books & Music** | 518 Walnut St, Viroqua, WI 54665 | DL- (location alias only) | First floor: ~100K uncatalogued, hand-priced. Second floor: ~50K catalogued + ~200K unresearched. |
| **Metaphysical Graffiti** | Viroqua, 1919-era storefront | MG- (location alias only) | Fully uncatalogued, pencil-priced. eBay room: ~700 active listings. Specialty: metaphysics, SF, radical politics. |

Both stores share one database, one API, one PWA. Store context passes on every request. Every Stock Item, Sale, Location, and Employee carries `store_id`.

**Out of scope for this build:** Bad Axe Music (vinyl, co-located at MG), Room for Comics (Al's comic shop, co-located at MG). Year 3+ at earliest.

### 4.1 SKU System

Format: `{employee_initials}-{sequential_number}` — e.g. `JS-1213`, `KK-3412`, `NV-0001`.

- No store prefix in the SKU itself. Store lives in the location record.
- Sequence is global across both stores. Numbers never reissued.
- Pencil on front free endpaper, top right.
- Imported books from Amazon or Ka-Zam carry their original ID in `seller_sku` as alias. Either is searchable.

| Employee | Initials |
|---|---|
| Jill | JS |
| Kim | KK |
| Cameron | CM |
| Nova | NV |
| Eddy | EN |

Add others in seed data as the team grows. Sullivan and apprentices get initials when they start cataloguing.

---

## 5. Data Model

The full schema is too long for this document. The migration files in `db/migrations/` are the source of truth. This section describes the structure and the invariants.

### 5.1 Core Entities

```
Work                          (FRBR-aligned: the abstract intellectual creation)
├── Edition                   (a specific published manifestation)
│   ├── Stock Item            (a physical copy at a specific store)
│   │   ├── Sale Record       (the transaction when sold)
│   │   ├── Location          (Store → Floor → Section → Slot)
│   │   ├── Photographs       (cover, title page, copyright page, supplementary)
│   │   └── Condition Q&A Log (full multi-turn record)
│   └── Source Records        (every external bibliographic record contributing to this Edition)
└── Source Records            (every external Work-level record)
```

### 5.2 The Source Record Table

The most important architectural decision in the build. Every external bibliographic record — Claude Vision response, BookScouter API return, ISFDB API call, LOC MARC record, scraped Vialibri page — is preserved as an immutable JSONB blob in the `source_record` table with full provenance.

```sql
CREATE TABLE source_record (
    source_record_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name         TEXT NOT NULL,         -- 'isfdb', 'open_library', 'claude_vision_sonnet_4_6'
    source_record_type  TEXT NOT NULL,         -- 'work', 'edition', 'pricing', 'condition_assessment'
    source_external_id  TEXT,                  -- the source's own ID for this record
    raw_data            JSONB NOT NULL,        -- exactly as received, untransformed
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confidence_floor    NUMERIC(3,2) NOT NULL, -- inherited from source tier
    field_conflicts     JSONB,                 -- array of {field, this_value, other_source_value}
    contributes_to_work UUID REFERENCES work(work_id),
    contributes_to_edition UUID REFERENCES edition(edition_id),
    is_training_pair    BOOLEAN NOT NULL DEFAULT FALSE,
    correction_of       UUID REFERENCES source_record(source_record_id),  -- if this is a correction
    correction_reason   TEXT,
    correction_by       UUID REFERENCES employee(employee_id)
);
```

Every dedup decision is reversible. Every bad merge can be unmerged. Every training example is recoverable. **Removing or compacting the source_record table is forbidden.** Even when records are merged into canonical Editions, the source records persist forever.

### 5.3 Store Organization Layer

```sql
-- Two-level location: Section + Slot
CREATE TABLE location (
    location_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id       UUID NOT NULL REFERENCES store(store_id),
    floor          TEXT NOT NULL,                  -- 'first', 'second', 'basement', 'eBay_room'
    section_code   TEXT NOT NULL,                  -- 'Fic', 'SF', 'Mil-WWII', 'Glass'
    slot           TEXT,                           -- specific shelf/bay/position
    is_catalogued  BOOLEAN NOT NULL DEFAULT FALSE, -- did this section get the cataloguing pass?
    UNIQUE(store_id, floor, section_code, slot)
);

CREATE TABLE employee (
    employee_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    initials       TEXT NOT NULL UNIQUE,           -- 'JS', 'KK', 'CM'
    full_name      TEXT NOT NULL,
    home_store_id  UUID NOT NULL REFERENCES store(store_id),
    started_at     DATE NOT NULL,
    ended_at       DATE,                           -- preserved historically
    is_active      BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE source (
    source_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id       UUID NOT NULL REFERENCES store(store_id),
    name           TEXT NOT NULL,                  -- 'estate sale Westby Mar 2026', 'Reader's Realm bulk'
    contact_info   JSONB,
    notes          TEXT,
    first_buy_at   DATE
);

CREATE TABLE buy_queue (
    buy_queue_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id       UUID NOT NULL REFERENCES store(store_id),
    source_id      UUID NOT NULL REFERENCES source(source_id),
    opened_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at      TIMESTAMPTZ,
    total_paid     NUMERIC(10,2),
    item_count     INTEGER,
    cost_per_item  NUMERIC(10,2) GENERATED ALWAYS AS
                   (CASE WHEN item_count > 0 THEN total_paid / item_count END) STORED
);
```

### 5.4 Conversation Logger

Multi-turn cataloguing dialogues between bookseller and Gibson are preserved in full from Day 1. **This must be in v1, not retrofitted.** Retrofit costs every conversation that came before it.

```sql
CREATE TABLE cataloguing_conversation (
    conversation_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id        UUID NOT NULL,
    stock_item_id     UUID REFERENCES stock_item(stock_item_id),
    employee_id       UUID NOT NULL REFERENCES employee(employee_id),
    started_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at      TIMESTAMPTZ,
    duration_seconds  INTEGER,
    n_turns           INTEGER,
    outcome           TEXT NOT NULL CHECK (outcome IN
                          ('approved', 'corrected', 'escalated', 'abandoned', 'in_progress')),
    final_confidence  NUMERIC(3,2),
    training_eligible BOOLEAN NOT NULL DEFAULT TRUE,
    approved_for_training BOOLEAN NOT NULL DEFAULT FALSE  -- requires curator review
);

CREATE TABLE conversation_turn (
    turn_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id      UUID NOT NULL REFERENCES cataloguing_conversation(conversation_id),
    turn_number          INTEGER NOT NULL,
    role                 TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content              TEXT NOT NULL,
    timestamp            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    evidence_type        TEXT,            -- 'photo_cover', 'photo_title', 'photo_copyright', 'manual_input'
    confidence_at_turn   NUMERIC(3,2),
    hypothesis_at_turn   JSONB,           -- what Gibson thought the book was at this point
    question_asked       TEXT             -- if assistant turn included a question
);
```

### 5.5 Cooperative Privacy at the Schema Level

```sql
-- pricing_record stores aggregate realized prices stripped of attribution
CREATE TABLE pricing_record (
    pricing_record_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    edition_id         UUID NOT NULL REFERENCES edition(edition_id),
    realized_price     NUMERIC(10,2) NOT NULL,
    condition_grade    TEXT,
    condition_dj       TEXT,
    sold_at            TIMESTAMPTZ NOT NULL,
    channel            TEXT NOT NULL          -- 'gibson_pos', 'biblio', 'amazon', 'whatnot'
    -- INTENTIONALLY NO store_id, no stock_item_id
    -- This is the cooperative pricing commons
);
```

The absence of `store_id` on this table is the cooperative privacy commitment expressed in the schema. Every member sees aggregate pricing data; no member sees another member's specific sales.

---

## 6. The Identification Pipeline

### 6.1 Triage Routing

Every book entering Gibson is routed to one of four paths based on what evidence is available before any identification questions are asked. The routing decision is the most important architectural call in the pipeline.

```
INCOMING BOOK
│
├── Has barcode? ──→ FAST PATH (Section 6.2)
│                    Sub-second, BooksRun + DB lookup
│
├── Hand-priced under $15 sticker? ──→ TRIAGE PATH (Section 6.3)
│                                       ~1.5 sec, Haiku, "shelve it"
│
├── Cover legible? ──→ STANDARD PATH (Section 6.4)
│                      5-6 sec, Sonnet cover-first protocol
│
└── Damaged/Ghost Book/no record? ──→ SLOW PATH (Section 6.5)
                                       Overnight research, placeholder created
```

The triage decision is made by the Standard Path entry point itself. The cover photo goes to a lightweight classifier (during Year 1, this is a single Haiku call with a focused prompt) that determines: *barcode present? hand-priced sticker visible? cover legible? Or none of the above?* The classifier returns a routing verdict, and the book proceeds down the appropriate path.

### 6.2 Fast Path

**Trigger:** Barcode detected and decoded successfully.

**Flow:**
1. Decode ISBN-13 from barcode
2. Local PostgreSQL lookup AND BooksRun API call fire **simultaneously, not sequentially**
3. If DB returns a high-quality match (confidence ≥ 0.90) → populate fields, proceed to condition Q&A
4. If DB returns a sparse match (0.65–0.89) → populate available fields, flag gaps for Q&A
5. If DB returns multiple matches → merge classifier picks winner, conflict surfaced to dealer
6. If DB returns no match → fall through to Standard Path on the cover photo

**Speed target:** Sub-second to display.

**Cost:** $0 in API calls (database lookup + BooksRun free tier).

**Critical invariant:** The Fast Path does not touch Claude. Scan → API call → display. The reasoning model is idle during this step. This matters because Claude calls are expensive and slow relative to a database lookup; pricing lookups must never wait for vision inference.

### 6.3 Triage Path

**Trigger:** Hand-priced sticker under $15 detected on cover, OR explicit "triage mode" toggle in PWA.

**Flow:**
1. Single cover photo to Haiku 4.5
2. Cached system prompt: `triage_system_prompt` (≈4K tokens)
3. Quick bibliographic lookup (1 candidate from database)
4. Quick pricing signal (BooksRun + BookScouter Cached, no Vialibri)
5. Haiku returns: `{verdict: "shelf_it" | "research_it", suggested_section: "Fic", suggested_price: 5}`
6. If `shelf_it`: dealer accepts price, condition is "Tap mode" single-click, book is shelved, listed IN_STORE_ONLY
7. If `research_it`: routes to Standard Path

**Speed target:** ~1.5 seconds total.

**Cost:** ~$0.005 per call with Haiku batch.

**Use case:** The 100,000 first-floor uncatalogued books at Driftless. Fast triage that captures a record without doing full bibliographic research on a $5 mass-market paperback.

### 6.4 Standard Path

**Trigger:** No barcode, no hand-priced sticker (or "research it" verdict from triage).

**Flow — cover-first protocol:**

1. **Cover photo capture.** Single shot. Image quality check: focus, lighting, full coverage. If quality fails, prompt re-shoot.
2. **Cover sent to Claude Sonnet 4.6** with cached system prompt + bibliographic context (top candidates from prior session if relevant).
3. **Claude returns structured JSON:**
   ```json
   {
     "title": "...",
     "subtitle": "...",
     "authors": [{"name": "...", "role": "author"}],
     "publisher": "...",
     "year": 2024,
     "edition_statement": "...",
     "isbn_visible": null,
     "confidence": {"title": 0.95, "author": 0.92, "publisher": 0.78, "year": 0.65},
     "needs": ["copyright_page_for_year_confirmation"],
     "candidate_editions": [{"edition_id": "...", "match_confidence": 0.91}, ...]
   }
   ```
4. **If overall confidence ≥ 0.85 and gap to second candidate ≥ 0.15:** identification accepted automatically, proceed to condition Q&A.
5. **If confidence is between 0.60–0.85:** Gibson asks one specific question. *"Confidence is 0.72 on the year — can I see the copyright page?"* The bookseller takes one targeted shot. Goes to step 3 again with the new evidence.
6. **If confidence stays below 0.60 after follow-up shots:** dealer chooses from top candidates, OR routes to Slow Path.

**Speed target:** 5–6 seconds for the average book that resolves on the first shot. Up to 15 seconds for books that need a follow-up.

**Cost:** ~$0.05 per book with Sonnet, prompt caching active.

**Cover-first principle:** One photograph resolves 75–80% of non-barcode books. Asking for three photographs upfront is bookseller time wasted. Gibson asks for additional shots only when it needs them, and tells the bookseller exactly what it needs and why.

### 6.5 Slow Path

**Trigger:** Standard Path failed (confidence < 0.50 after follow-up), OR no institutional record found in any source, OR damaged title page, OR explicitly Ghost Book material.

**Flow:**
1. **Placeholder Stock Item created immediately** with status `PENDING_RESEARCH`. The dealer is not blocked — they move on to the next book.
2. **The original photographs and any partial OCR** are stored on the Stock Item with a routing reason.
3. **The Stock Item enters an Airflow research queue** for overnight processing.
4. **The autonomous research agent runs nightly at 2 AM** (Hetzner VM during Year 1, local server post-migration):
   - smolagents drives the research loop
   - DuckDuckGo + ScrapeGraphAI + Playwright fetch candidate pages
   - Tier 1 sources first (WorldCat, ISFDB, LOC, Open Library, BNB)
   - Tier 2 sources second (commercial — Vialibri, Biblio, Heritage)
   - Tier 3 sources last (specialist, fan, archival)
5. **Claude Haiku synthesizes** the multi-source evidence (during Year 1 — this becomes local Llama post-migration).
6. **Sonnet reviews** if Haiku synthesis confidence is below 0.75.
7. **The candidate record lands in a human review queue** the next morning.
8. **Eddy or a curator approves, edits, or rejects.** Approval generates a high-quality training example.

**Speed target:** Overnight. Books are not blocked.

**Cost:** ~$0.005 per call average (mostly Haiku, with batch). Average ~30 calls per book = $0.15 per slow-path book.

**Critical invariant:** The autonomous research agent never writes directly to the canonical catalog. It produces candidates with confidence scores and source citations. Human approval is absolute.

---

## 7. The Pricing Layer

### 7.1 The Stack

In display order on the bookseller's screen:

```
┌─────────────────────────────────────────────────────────────┐
│  SOLD (REALIZED)                                            │
│  Gibson POS history          [if available — highest weight]│
│  eBay sold (last 90 days)                                   │
│  Heritage / Swann / regional auction realized prices        │
│                                                             │
│  ASKING (MARKET)                                            │
│  Vialibri current listings                                  │
│  eBay active                                                │
│  BookScouter Cached (30+ vendor aggregate)                  │
│                                                             │
│  TREND                                                      │
│  BookScouter Historic (6-month direction)                   │
│                                                             │
│  GIBSON SUGGESTS:    $XX.XX  (median realized × condition) │
│  YOUR PRICE:         [editable]                             │
└─────────────────────────────────────────────────────────────┘
```

Each line cites its source. Each line shows how many data points contributed. Empty data is shown as empty, not hidden.

### 7.2 Vialibri Gate

**No online listing without a Vialibri lookup.** This is non-negotiable.

```
Vialibri returns comps → proceed to listing
  Gibson: "Vialibri $9–$14, eBay sold $11. Suggest $10."

Vialibri returns empty → Gibson presents two routing options:
  ┌───────────────────────────────────────────┐
  │ Vialibri has no comps for this book.      │
  │                                           │
  │ [ Price $3 — IN-STORE ONLY ]              │
  │ [ Queue for overnight research ]          │
  │ [ List anyway — I know the value ]        │
  └───────────────────────────────────────────┘
```

The third option exists but is logged. Listing without comps is a dealer judgment call; Gibson does not block it but flags it as `priced_without_comps = true` for later review.

**Vialibri access status: unconfirmed.** This is the largest unresolved external dependency. If Sullivan's conversation lands a partnership, free or at workable cost, the architecture above proceeds. If it lands at a prohibitive tier, this section is the first thing to redesign.

### 7.3 Field-Tool vs Research Pipelines

Field-tool pricing and background-research pricing share zero code paths. **This is an architectural invariant.**

| Context | Trigger | How | Speed target |
|---|---|---|---|
| Field cataloguing | Barcode scan or ISBN entry | BooksRun + BookScouter Cached → display | Sub-second |
| Field cataloguing (no barcode) | Cover identification confirmed | Vialibri + eBay + BookScouter → display | 2–3 seconds |
| Background research | Slow Path placeholder OR sparse record flagged | Autonomous agent across full source stack | Batch overnight |

The field tool does not touch the autonomous agent. The agent does not touch the field tool's pricing logic. They share data (the canonical Edition record, the pricing_record table) but no code paths.

### 7.4 The Dealer's Price Is Always Final

Gibson suggests. The dealer decides. The system never overrides. The dealer can edit the suggested price freely. If the dealer's price is significantly below the median (more than 40%), Gibson surfaces a one-tap "Your price is below market — is this intentional?" warning, but does not block.

Every dealer override is logged as a pricing training signal.

### 7.5 Cost-Basis Awareness

Stock Item carries `cost_per_item` calculated from the Buy Queue. The pricing layer reasons about this:

- If suggested listing price is below cost basis: Gibson surfaces the warning.
- If suggested listing price is above 5× cost basis: Gibson surfaces a different warning ("This is a high-margin recommendation — verify rare/collectible status").
- The dealer can override either warning.

Cost basis is never exposed outside the owning store. The cooperative-privacy schema (§ 11) enforces this at the query level.

---

## 8. The Condition System

Two modes. Gibson determines which before asking anything.

### 8.1 Tap Mode

**Trigger:** First floor / commodity / under $15 / triage-routed.

Single tap from a one-row picker:

```
[ Fine ] [ VG+ ] [ VG ] [ Good ] [ Reading Copy ]
```

No questions. One gesture. Time to complete: under 2 seconds.

Plus a jacket tap if the triage engine has flagged `jacket_issued = yes` on the Edition: a single-row picker for jacket presence (Present / Absent expected / Absent unknown).

### 8.2 Q&A Mode

**Trigger:** Upstairs / online listing / $15 and above.

Seven core questions presented one at a time, each with tap-to-answer options. Conditional sub-questions fire based on Q5 (jacket) and other triggers.

| Q# | Question (as shown) | Answer options |
|---|---|---|
| Q1 | Any writing, stamps, or marks inside? | None / Ex-libris only / Light / Heavy |
| Q2 | Binding: how does it feel? | Tight / Slightly loose / Loose / Detached or broken |
| Q3 | Cover and boards: overall wear? | None or near fine / Light shelf wear / Moderate wear / Heavy wear or damage |
| Q4 | Pages: any foxing, tanning, or water damage? | Clean / Light tanning / Foxed / Water damaged |
| Q5 | Dust jacket present? | **Yes, complete** / **No — issued without** / **No — unknown if ever issued** |
| Q6 | Any pages, plates, or maps missing? | No / Yes |
| Q7 | Overall grade (Gibson-suggested, dealer overrides freely) | Fine / VG+ / VG / Good+ / Good / Fair / Poor |

### 8.3 Q5 — Three-State Dust Jacket Logic

**This is non-negotiable.** The dust jacket is a separate bibliographic and physical object. It receives its own condition grade. It is never folded into the book grade. Jacket presence is a three-state field — present, absent-expected, absent-unknown — because these are three meaningfully different things.

**Q5 answers:**
- **Yes, complete** → fires Q5a, Q5b (if pre-1970 or value-flagged), Q5c
- **No — issued without** → stored as `jacket_present = 'absent_expected'`. Listing reads: "No dust jacket, as issued."
- **No — unknown if ever issued** → stored as `jacket_present = 'absent_unknown'`. Listing reads: "No dust jacket; records do not confirm whether this edition was issued with one." Research agent may resolve overnight.

Never present Q5 as "No jacket" with a single undifferentiated negative.

**Q5a (always fires when Q5 = Yes):** Jacket condition — Fine / VG+ / VG / Good+ / Good / Fair / Poor. Independent of book grade.

**Q5b (fires when Q5 = Yes AND publication_year < 1970 OR triage flagged jacket_price as value-determinant):** Price on jacket — Price intact (note printed price) / Clipped / Sticker removed / Panel missing.

**Q5c (always fires when Q5 = Yes):** Jacket in protective cover — None / Mylar or archival sleeve / Tape or non-archival cover / **Facsimile**.

**Facsimile disclosure is non-suppressible.** If `jacket_is_facsimile = true`, the listing description automatically prepends: "Note: jacket is a reproduction facsimile, not original." The dealer cannot suppress this line.

### 8.4 Other Conditional Questions

| Q# | When triggered | Question |
|---|---|---|
| Q8 | Confidence on edition < 0.80 | Is this a first edition? (Check copyright page) |
| Q9 | Multiple printings recorded | What does the number line show? |
| Q10 | Vision flagged possible signature | Is there a signed or inscribed page? Who, dated? |
| Q11 | Limited / fine press / numbered indicator | Is there a limitation statement? (Copy X of Y) |

### 8.5 Listing Format

```
[Book grade] in [Jacket grade] dust jacket.

Examples:
  "Very Good+ in Very Good dust jacket."
  "Very Good+ (no dust jacket, as issued)."
  "Very Good (no dust jacket; unknown if issued)."
  "Fine in Very Good dust jacket. Note: jacket is a reproduction facsimile, not original."
```

**Never use VG+/VG slash format.** Slash format is ambiguous about which grade is the book and which is the jacket. The full sentence form is unambiguous.

---

## 9. The Application — Phone Layout

Mobile is the primary deliverable. Every other layout is derived from mobile-first design.

### 9.1 Design Principles

1. **One thumb operation.** All primary actions must be reachable with the thumb of the hand holding the phone.
2. **Speed > beauty.** Functional minimalism. No animations beyond necessary feedback.
3. **Progressive disclosure.** Primary view shows minimum useful info. Tap to drill deeper.
4. **Honest uncertainty visible.** Confidence scores, source attributions, conflict flags are first-class UI elements, not buried in tooltips.
5. **Continue-friction-free.** The most common action (continue / approve / next) is always the largest, lowest-friction button on the screen.

### 9.2 Screen Map

```
ROOT (post-login)
│
├── CAPTURE                       (default landing, camera-first)
│   ├── CAMERA                    (cover-first photo capture)
│   ├── IDENTIFICATION RESULT     (after Claude returns)
│   │   ├── BIBLIOGRAPHIC DEEP DIVE   (Layer 1 — tap title)
│   │   ├── PRICING DEEP DIVE         (Layer 2 — tap price)
│   │   ├── SCARCITY DEEP DIVE        (Layer 3 — tap scarcity badge)
│   │   ├── LIVE MARKETPLACE          (Layer 4 — tap "see active copies")
│   │   └── DISAMBIGUATION SCREEN     (when confidence is split)
│   ├── CONDITION Q&A             (after identification confirmed)
│   │   ├── TAP MODE              (single-row grade picker)
│   │   └── Q&A MODE              (7 questions, conditional sub-questions)
│   ├── PRICING + LISTING         (Vialibri gate, channel routing)
│   └── CONFIRMED                 (success screen, auto-advance to next book)
│
├── INVENTORY                     (search, filter, manage)
│   ├── SEARCH RESULTS
│   ├── ITEM DETAIL
│   └── EDIT FIELDS
│
├── BUY QUEUE                     (counter intake)
│   ├── OPEN NEW QUEUE
│   ├── PHOTOGRAPH HAUL
│   ├── CUSTOMER + OFFER
│   └── CLOSE / RECEIPT
│
├── COUNTER POS                   (sale capture)
│   ├── SCAN OR PHOTO
│   ├── PRICE CONFIRMATION
│   └── CUSTOMER + COMPLETE
│
├── CORRECTION QUEUE              (Eddy's review surface — admin only)
│   └── (collapses to web link on phone — desktop-first surface)
│
└── SETTINGS
    ├── STORE CONTEXT             (which store am I in)
    ├── EMPLOYEE PROFILE
    └── SECTION QUICK-PICKER
```

### 9.3 Capture Screen — The Heart of the App

The most-used screen. Optimized for cataloguing 300+ books per day. Layout described top-to-bottom on a phone in portrait orientation:

```
┌─────────────────────────────┐
│ STATUS BAR                  │  9:42 · WiFi · battery
├─────────────────────────────┤
│ DRIFTLESS · UPSTAIRS · SF/F │  store + floor + section context
│ Gibson                      │  (section picker auto-fills based on
│             [≡ menu]        │   last 3 books)
├─────────────────────────────┤
│                             │
│      CAMERA VIEWFINDER      │
│      (or last result        │
│       thumbnail with        │
│       summary overlay)      │
│                             │
│                             │
├─────────────────────────────┤
│ [ Re-shoot ] [ Triage mode ]│
└─────────────────────────────┘
       [  ◯ CAPTURE  ]           large, thumb-reachable
```

After capture and identification:

```
┌─────────────────────────────┐
│ ← Back to capture           │
├─────────────────────────────┤
│ GIBSON IDENTIFIED [0.91]    │  confidence pill, color-coded
│                             │  (green ≥ 0.85, amber 0.65–0.85,
│ A Canticle for Leibowitz    │   red < 0.65)
│ Walter M. Miller, Jr.       │
│ J.B. Lippincott, 1960       │
│ First edition, first print  │
├─────────────────────────────┤
│ [LOC ✓] [ISFDB ✓] [OL ✓]    │  source attribution pills,
│ [⚠ 1 conflict]              │  conflicts in amber
├─────────────────────────────┤
│ ┌─ CONFLICT ──────────────┐ │
│ │ ISFDB says gray cloth.  │ │
│ │ OL says black cloth.    │ │
│ │ Gibson asks to see it.  │ │
│ └─────────────────────────┘ │
├─────────────────────────────┤
│ ┌─ GIBSON ASKS ───────────┐ │  inline question, three tap-options
│ │ G  Gray cloth = $200-450│ │
│ │    Black cloth = $40-90 │ │
│ │    Which is it?         │ │
│ │ [Gray] [Black] [Show me]│ │
│ └─────────────────────────┘ │
├─────────────────────────────┤
│ PRICING — gray cloth state  │
│                             │
│ ✓ Sold (realized)           │
│   Heritage 2023 (sgnd) $425 │
│   eBay 90d (3)     $180-340 │
│   Driftless POS         —   │
│                             │
│ 🏷 Asking (market)          │
│   Vialibri (4)     $225-650 │
│   eBay active (7)  $150-500 │
│   BookScouter (30) $95-280  │
│                             │
│ 📈 Trend: stable, ↑12% 6mo  │
├─────────────────────────────┤
│ GIBSON SUGGESTS             │
│         $245                │  large, tappable (opens edit)
├─────────────────────────────┤
│ CONDITION Q&A · 2 of 7      │
│ Q2. Dust jacket present?    │
│                             │
│ [Yes, intact         ]      │
│ [Yes, with sleeve    ]      │
│ [No — absent         ]      │
│ [No — as issued      ]      │  (grayed if unlikely)
├─────────────────────────────┤
│ WILL LIST TO                │
│ [Biblio] →[Amazon] →[AbeB.] │
├─────────────────────────────┤
│ [Save draft] [Continue → Q3]│  large, low-friction continue
└─────────────────────────────┘
```

### 9.4 Layered Information Access

Every primary surface element is tappable. Tapping drills into a deeper layer; the back gesture returns to the primary view. The bookseller never loses their place.

**Layer 1 — Bibliographic Deep Dive (tap title or edition):**
```
- Full Edition record: publisher, city, format, pages, binding
- Work record: all known editions with years
- Source citations: where each field came from (raw source records)
- Confidence breakdown by field
- Variant identification notes (colophon, number line, issue points)
- [Button: This isn't the right book → Disambiguation]
```

**Layer 2 — Pricing Deep Dive (tap price summary):**
```
- Full pricing stack with source labels
- Every active comp with condition, price, seller, date listed
- Realized price history with chart (if 3+ data points)
- Scarcity summary with [→ Scarcity Deep Dive]
```

**Layer 3 — Scarcity Deep Dive (tap scarcity badge):**
```
- Full evidence chain: print run, WorldCat, LT, OL, marketplace snapshots
- Source citations for every data point
- Confidence intervals and data age
- Snapshot history: 8 quarters of marketplace availability
- [Button: Add community note | Flag for research]
```

**Layer 4 — Live Marketplace (tap "See active copies"):**
```
- Live Vialibri results: price, condition, seller, location, date listed
- Live eBay active: same format
- Sort: price low→high, date listed (oldest first = slowest movers)
- Note: real-time fetch, labeled as such
```

### 9.5 Disambiguation Screen

Triggered by: "This isn't the right book" tap, OR identification confidence < 0.70, OR multiple candidates with similar confidence.

```
┌─────────────────────────────┐
│ ← Back                      │
├─────────────────────────────┤
│ POSSIBLE MATCHES            │
│ Gibson is not certain       │
│ which edition this is.      │
├─────────────────────────────┤
│ ○ A Canticle for Leibowitz  │
│   Lippincott 1960 (first)   │
│   Confidence 0.62           │
│   Why: cover matches, but   │
│   binding state ambiguous   │
├─────────────────────────────┤
│ ○ A Canticle for Leibowitz  │
│   Bantam 1976 (mass mkt)    │
│   Confidence 0.31           │
│   Why: title matches,       │
│   layout is paperback-style │
├─────────────────────────────┤
│ ○ None of these — let me    │
│   describe it manually      │
├─────────────────────────────┤
│ [ Show me how to tell ]     │  shows visual dictionary entries
└─────────────────────────────┘
```

### 9.6 Counter POS Screen

When a customer brings a book to the counter:

```
┌─────────────────────────────┐
│ COUNTER · DRIFTLESS         │
├─────────────────────────────┤
│ Today: 23 sales · $487      │
├─────────────────────────────┤
│  [ Scan barcode  ]          │
│  [ Photograph    ]          │
│  [ Look up SKU   ]          │
├─────────────────────────────┤
│ LAST 3 SALES                │
│ • Hemingway short stories $9│
│ • Wisconsin atlas        $15│
│ • Penguin classic        $4 │
├─────────────────────────────┤
│ [ Open buy queue ]          │  fast-access for sellers
└─────────────────────────────┘
```

After scan/photo:

```
┌─────────────────────────────┐
│ ← Counter                   │
├─────────────────────────────┤
│ MATCHED                     │
│ The Catcher in the Rye      │
│ Salinger · Little, Brown    │
│ Cataloged: KK-3412          │
│ Section: Fic, Slot 7B       │
├─────────────────────────────┤
│ PRICE                       │
│ Penciled: $8                │
│ Catalogue: $8 (matches)     │
├─────────────────────────────┤
│ Customer:                   │
│ [+ Anonymous] [+ Add member]│
├─────────────────────────────┤
│ [ COMPLETE SALE — $8 ]      │
└─────────────────────────────┘
```

---

## 10. The Application — Desktop Layout

Desktop is for difficult cases, research at the counter, the correction queue, the dashboard, and the inventory management surface. **The cataloguing flow itself stays on phone.** Desktop is the supplementary surface.

### 10.1 Design Principles

1. **Three-pane layout for rich data.** Sidebar (navigation), main (primary content), inspector (detail).
2. **Dense information by default.** Desktop users can absorb more on a screen; don't waste the real estate.
3. **Keyboard-first where it matters.** Search, navigation, correction shortcuts. Power users skip the mouse.
4. **Multi-record operations.** Bulk approve, bulk re-route, bulk re-tag. Phone is single-record; desktop is multi-record.

### 10.2 Screen Map

```
ROOT (desktop)
│
├── DASHBOARD                         (default landing, Eddy's view)
│   ├── TODAY'S ACTIVITY              (books processed, by person, by store)
│   ├── PIPELINE HEALTH               (path distribution, confidence, queue depth)
│   ├── CORRECTION QUEUE PREVIEW      (HIGH priority items)
│   └── TRAINING DATA HEALTH          (corrections, pairs, dataset readiness)
│
├── INVENTORY                         (full search, filter, bulk operations)
│   ├── SEARCH + FILTERS              (every field queryable)
│   ├── RESULTS GRID                  (sortable, multi-select)
│   └── INSPECTOR (right pane)        (selected item detail + edit)
│
├── CORRECTION QUEUE                  (Eddy's primary work surface)
│   ├── HIGH                          (review first)
│   ├── MEDIUM                        (review when time)
│   └── LOW                           (batch approve)
│
├── BIBLIOGRAPHIC SEARCH              (full database, work-edition-stock browse)
│   └── (research surface for difficult cases at the counter)
│
├── PRICING WORKBENCH                 (deep dive on a single book)
│   ├── ALL COMPS, EVERY SOURCE
│   ├── REALIZED HISTORY CHART
│   └── COOPERATIVE COMPARISONS       (anonymized)
│
├── BUY QUEUE MANAGEMENT              (open queues, source attribution, payouts)
│
├── ADMIN                             (Eddy + Nova only)
│   ├── EMPLOYEES + PERMISSIONS
│   ├── SECTIONS + LOCATIONS
│   ├── SOURCE MANAGEMENT             (bibliographic source ingest status)
│   ├── PIPELINE CONFIGURATION        (model routing, confidence thresholds)
│   └── TRAINING DATA EXPORT          (for QLoRA pipeline)
│
└── CONVERSATIONS                     (architectural conversation archive — RAG corpus)
```

### 10.3 The Dashboard

The desktop landing screen for Eddy and any user with `manager` role. Three-row layout:

```
┌──────────────────────────────────────────────────────────────────┐
│ [Sidebar: Dashboard | Inventory | Corrections | Pricing | Admin] │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│ ┌─ TODAY · MAY 7, 2026 ─────────────────────────────────────┐   │
│ │ DRIFTLESS                  METAPHYSICAL GRAFFITI            │   │
│ │ ─────────                  ─────────────────────            │   │
│ │ 247 books processed        89 books processed               │   │
│ │ 31 listed online           0 listed (in-store only floor)   │   │
│ │ 23 sales · $487            12 sales · $234                  │   │
│ │ 4 corrections pending      1 correction pending             │   │
│ └─────────────────────────────────────────────────────────────┘   │
│                                                                  │
│ ┌─ PIPELINE HEALTH (last 7 days) ────────────────────────────┐  │
│ │ Fast Path:     1,234 books (62%)  · avg conf 0.94           │  │
│ │ Triage Path:     453 books (23%)  · avg conf 0.91           │  │
│ │ Standard Path:   267 books (13%)  · avg conf 0.83           │  │
│ │ Slow Path:        46 books (2%)   · 38 resolved overnight   │  │
│ │                                                             │  │
│ │ Correction rate: 4.2%   (target < 8% — healthy)             │  │
│ │ Anthropic spend (7d): $67  · projected month: $290          │  │
│ └─────────────────────────────────────────────────────────────┘  │
│                                                                  │
│ ┌─ CORRECTION QUEUE — HIGH PRIORITY ─────────────────────────┐  │
│ │ Item                     | Field       | Why            | ↓ │  │
│ │ ─────────────────────────|─────────────|────────────────|── │  │
│ │ Joyce, Ulysses (1922)    | Edition     | Gibson 0.92, KK│ → │  │
│ │ Burroughs, Junky (1953)  | Year        | conflict 53/52 │ → │  │
│ │ Sandburg, Lincoln Vol 4  | Pricing     | 47% > Vialibri │ → │  │
│ │ ...3 more                |             |                |   │  │
│ │ [ Review HIGH queue → ]  [ Batch approve LOW (47) → ]   │  │
│ └─────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 10.4 The Correction Queue

Eddy's primary work surface. Reviews 50–200 corrections per day. Three-pane layout: sidebar (priority filter), main (queue list), inspector (selected item).

```
┌──────────┬───────────────────────────────────┬───────────────────┐
│ SIDEBAR  │ QUEUE                             │ INSPECTOR         │
├──────────┼───────────────────────────────────┼───────────────────┤
│ ● HIGH   │ ⌖ Joyce, Ulysses                  │ Joyce, Ulysses    │
│   (12)   │   Field: edition_statement        │ Cataloged by KK   │
│ ○ MEDIUM │   Original: "First edition"       │ 2026-05-07 09:23  │
│   (38)   │   Corrected: "First American Ed"  │                   │
│ ○ LOW    │   Reason: KK noted Modern Library │ Source records:   │
│   (47)   │   imprint, not Random House       │  ISFDB           ▾│
│          │   ───────────────────────────     │  LOC MARC        ▾│
│ FILTERS  │                                   │  Open Library    ▾│
│ Store    │ ⌖ Burroughs, Junky                │  Claude Vision   ▾│
│ Person   │   Field: publication_year         │                   │
│ Field    │   Original: 1953                  │ Conversation log: │
│ Date     │   Corrected: 1952 (advance copy)  │  4 turns, 0:42    │
│          │   Reason: KK saw advance copy ind │  [view full →]    │
│ [Reset]  │                                   │                   │
│          │ ⌖ Sandburg, Lincoln               │ Photographs:      │
│ TRAINING │   Field: pricing                  │  cover · spine    │
│ Today:   │   Suggested: $145                 │  copyright page   │
│  47 pairs│   Listed: $215                    │                   │
│ Total:   │   ───────────────────────────     │ ┌─ ACTIONS ──┐   │
│  4,127   │                                   │ │ ✓ Approve   │   │
│          │ ...                               │ │ ✗ Reject    │   │
│          │                                   │ │ ✎ Edit      │   │
│          │                                   │ │ ↻ Re-route  │   │
│          │                                   │ └─────────────┘   │
└──────────┴───────────────────────────────────┴───────────────────┘
```

### 10.5 The Inventory Search

When Kim is at the counter and a customer asks "do you have anything by Edward Abbey?", or when Eddy is researching a difficult book at his desk:

```
┌──────────┬────────────────────────────────────────────────────────┐
│ SIDEBAR  │ SEARCH: edward abbey                                   │
│          │ ─────────────────────────────────────────────────      │
│ FACETS   │  Filters: store ▾ · floor ▾ · section ▾ · cond ▾      │
│          │ ─────────────────────────────────────────────────      │
│ Author   │ ┌────────────────────────────────────────────────────┐ │
│ Subject  │ │ Title                | Edition | Loc      | Price  │ │
│ Section  │ ├────────────────────────────────────────────────────┤ │
│ Year     │ │ Desert Solitaire     | 1968 1st| DL/2/Nat | $185   │ │
│ Cond.    │ │ The Monkey Wrench Gang| 1975 1st| DL/2/Fic| $95    │ │
│ Format   │ │ Abbey's Road         | 1979 1st| DL/2/Nat | $35    │ │
│ Channel  │ │ Down the River       | 1982    | MG       | $14    │ │
│          │ │ Beyond the Wall      | 1984    | DL/2/Nat | $25    │ │
│ Avail.   │ │ ...12 more                                          │ │
│ ☑ All    │ ├────────────────────────────────────────────────────┤ │
│ ☐ In stk │ │ [ Pull all to counter ] [ Print list ]              │ │
│ ☐ Listed │ └────────────────────────────────────────────────────┘ │
│          │                                                         │
└──────────┴────────────────────────────────────────────────────────┘
```

Click any row → opens inspector pane with full record, photographs, source citations, pricing history.

### 10.6 Pricing Workbench

For difficult pricing decisions — books where the standard pricing layer doesn't give a clear answer, or where Eddy wants to dig into the comp data:

```
┌────────────────────────────────────────────────────────────────────┐
│ PRICING WORKBENCH · The Hobbit, Allen & Unwin 1937 1st             │
├────────────────────────────────────────────────────────────────────┤
│ ┌─ REALIZED PRICES ────────────────────────────────────────────┐   │
│ │  Date    | Source              | Condition | Price            │   │
│ │  2025-09 | Heritage Auctions   | F in F DJ | $45,000          │   │
│ │  2024-11 | Sotheby's           | VG in G DJ| $18,000          │   │
│ │  2024-03 | Swann Galleries     | F no DJ   | $8,500           │   │
│ │  ...                                                           │   │
│ └────────────────────────────────────────────────────────────────┘   │
│                                                                    │
│ ┌─ ASKING PRICES (LIVE) ──────────────────────────────────────┐   │
│ │  Source   | Condition       | Asking | Listed | Days        │   │
│ │  Vialibri | F in F DJ       | $52K   | UK     | 12          │   │
│ │  Vialibri | VG+ in VG+ DJ   | $34K   | US     | 47          │   │
│ │  ...                                                          │   │
│ └────────────────────────────────────────────────────────────┘   │
│                                                                    │
│ ┌─ TREND CHART (last 24 months) ──────────────────────────────┐   │
│ │  [chart placeholder]                                         │   │
│ └────────────────────────────────────────────────────────────┘   │
│                                                                    │
│ ┌─ COOPERATIVE COMPARISONS (anonymized) ──────────────────────┐   │
│ │ 3 cooperative members have sold this edition in the last    │   │
│ │ 18 months. Range: $8,200 – $42,000. Mean: $19,400.         │   │
│ └─────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────┘
```

### 10.7 The Conversations Archive

The desktop surface for the architectural-conversation corpus. Browse, search, and tag the conversations between Eddy and Claude that get exported throughout Year 1. This is the institutional memory layer that the local Llama RAG-queries against post-migration.

```
┌──────────┬────────────────────────────────────────────────────────┐
│ TOPICS   │ CONVERSATIONS ARCHIVE                                  │
│          │ ─────────────────────────────────────────────────      │
│ Schema   │ Search: dust jacket facsimile                          │
│   (12)   │                                                         │
│ Pricing  │ ┌────────────────────────────────────────────────────┐ │
│   (8)    │ │ 2026-04-15 — Dust jacket as bibliographic object   │ │
│ Dedup    │ │ 47 turns · 3,200 words                              │ │
│   (15)   │ │ Tags: schema, dust_jacket, condition_q&a            │ │
│ Cond.    │ │ Decision: three-state field, facsimile non-suppress │ │
│   (5)    │ │ [open →]                                            │ │
│ Corp.    │ │                                                      │ │
│   (3)    │ │ 2026-03-08 — Facsimile jacket disclosure            │ │
│ ...      │ │ 12 turns · 800 words                                 │ │
│          │ │ Tags: condition, listings, ethics                    │ │
│          │ │ [open →]                                             │ │
│          │ │                                                      │ │
│          │ │ ...                                                  │ │
│          │ └─────────────────────────────────────────────────────┘ │
└──────────┴────────────────────────────────────────────────────────┘
```

### 10.8 Tablet Layout

The middle viewport (640–1024px). Tablet is used by apprentices on cataloguing carts, by Kim at the counter when she needs more screen than the phone gives, and by Eddy when he's reviewing the correction queue away from his desk.

Tablet uses the same three-pane structure as desktop but collapses the inspector pane to an overlay (drawer-style) when a record is selected. The cataloguing flow is the same as phone but with larger touch targets and side-by-side rendering of the photograph and the form fields when the screen is wide enough.

The decision rule for tablet: every desktop screen has a tablet-responsive variant; every phone screen works unchanged on tablet. The cataloguing flow stays mobile-first.

---

## 11. Cooperative Data Governance

### 11.1 What Every Member Sees

- Full bibliographic database (Work, Edition, Agent, Publisher) — cooperative commons
- Realized prices in aggregate, no member attribution
- Collective copy count by title (count only, no member detail, no location)
- Confidence scores and source citations on all records
- The 100-bibliography corpus
- Source records with original provenance preserved

### 11.2 What No Member Sees

- Another member's cost basis — ever
- Another member's asking prices before public listing
- Another member's inventory details (what they have, where, condition)
- Another member's sales volume, revenue, transaction history
- Another member's correction history or identification patterns

### 11.3 Implementation

Enforced at the database query level, not in application logic.

- Every Stock Item query MUST include `store_id` filter — this is not optional, not a feature, but how member data stays private by default.
- The `pricing_record` table strips `store_id` before insert. The schema does not have a `store_id` column on this table; attribution is impossible by structure.
- Cost basis (`stock_item.cost_basis_at_acquisition`) is only queryable from the owning store's dashboard.
- Member A's stock simply does not appear in Member B's queries. This is not a permission system. It is a data architecture decision.

### 11.4 Audit Trail

Every read of cross-member data (the realized-price aggregate, the cooperative bibliographic commons) is logged. The cooperative reviews the audit log quarterly. This is an accountability mechanism, not a surveillance system — the log records "member X queried the realized-price aggregate at 2026-05-07 14:32," not "member X looked up Member Y's data" because the latter is not possible.

---

## 12. Data Acquisition and Bibliographic Foundation

### 12.1 The Foundation Ingest

The bibliographic database that Gibson reasons against is built from a sequence of source ingests in a deliberate order. Each source is a separate Airflow DAG with its own normalization layer.

| Source | Month | Volume | Access |
|---|---|---|---|
| ISFDB | 2 | 2.38M records | CC license, bulk DB dump |
| Open Library (post-1950 EN subset) | 3 | 4M filtered editions | Free bulk export from archive.org |
| LOC Authority Files | 3 | ~18M name + subject authorities | Free download from id.loc.gov |
| LOC MARC (full bibliographic) | 4–5 | ~18M | Free API + bulk via partnership |
| BNB | 4–5 | UK comprehensive | Partnership (Sullivan) |
| HathiTrust | 5 | ~17M digitized | Free API |
| Project Gutenberg | 6 | ~70K pre-1928 | Free RDF/XML |
| Wikidata Q-numbers | 6 | growing crosswalk spine | Free SPARQL |
| Crossref | 6 | 130M+ scholarly | Free API |
| Galactic Central | Year 2 | SF magazine bibliography | Partnership (Phil) |
| ISBNdb | Optional | 109M+ commercial | Annual bulk export, partnership |

### 12.2 The Five-Stage Deduplication Pipeline

| Stage | Name | What happens | When |
|---|---|---|---|
| 1 | Ingest & Normalize | Each source parsed into intermediate format. Author inversion, publisher canonicalization, ISBN validation. One import script per source. | Months 2–3 |
| 2 | Blocking | Reduce comparison space. LSH on title/author. | Month 3 |
| 3 | Candidate Scoring | Similarity scores across fields. Weighted by reliability. BibDedupe evaluated here first. | Months 3–4 |
| 4 | Classification & Clustering | Auto-merge above threshold. Uncertain middle → human review queue (assisted by Claude — Haiku for bulk, Sonnet for hard cases). | Months 4–5 |
| 5 | Continuous Validation | Member corrections feed back. Periodic re-runs as new sources added. | Ongoing |

### 12.3 The 100 Bibliographies — Read by Claude in Year 1

In the local-server architecture this is a fine-tuning corpus. In the Year 1 cloud architecture, Claude reads it and produces structured output stored as RAG fuel + training pairs:

1. **Ingest pass:** 75M tokens of bibliographic source material (McKerrow, Gaskell, Bowers, Bleiler, ABPC, etc.) sent through Claude Sonnet in batches with structured extraction prompts. Output: structured JSON per chunk with reasoning patterns, bibliographic claims, and discriminative points surfaced.
2. **Synthesis pass:** Per-major-work multi-page summaries that capture methodology and reasoning.
3. **Cross-reference pass:** Conflicts and overlaps surfaced (where Gaskell and Bowers disagree, etc.).
4. **Training pair extraction:** ~10,000 structured Q&A pairs (*given this title page, what is the edition? Why?*) ready for the eventual QLoRA run.

Total cost: $500–$1,000 one-time. See `Gibson_Year_One_Budget.docx` § 2.2.

### 12.4 Source Hierarchy and Access Patterns

Per `Gibson_Data_Acquisition_Operating_Instructions.docx`, every source is classified into an acquisition mode:

- **Bulk download** (preferred): the source provides a complete data dump. Run a DAG monthly or quarterly.
- **API query** (acceptable): structured API with rate limits. Run a DAG with appropriate throttling.
- **HTML scrape** (last resort, ToS-permitting): ScrapeGraphAI or Playwright. Always reads robots.txt.
- **Partnership before scraping** (relationship-required): Galactic Central, ISFDB extensions, dealer-network pricing data.

Every source has its own normalization function. Author names resolved via VIAF + GND + LOC Name Authority Files (≥ 0.85 confidence required). Conflicts logged, never auto-resolved.

---

## 13. Migration Path to Local Hardware

The migration is a redeployment, not a rewrite. The codebase has environment variables for every external service endpoint. Changing from cloud to local is changing config values.

### 13.1 The Day-Of Procedure

| Step | Command | Time |
|---|---|---|
| 1. Export database | `pg_dump gibson_prod > gibson.sql` | 30–60 min |
| 2. Import to local | `psql gibson_local < gibson.sql` | 30–60 min |
| 3. Sync image storage | `rclone sync r2:gibson-images /data/images/` | 4–8 hours |
| 4. Sync conversation archive | `rsync /home/eddy/conversations/ server:/data/conversations/` | minutes |
| 5. Deploy FastAPI backend | `git clone + pip install + systemd service` | 1 hour |
| 6. Install Ollama + Llama | `ollama pull llama3.1:70b-q4` | 30–60 min |
| 7. Update config — research agent | Point `OLLAMA_BASE_URL` at `localhost:11434` | 5 min |
| 8. Install CLIP | `pip install + download ViT-L/14 weights` | 30 min |
| 9. Build CLIP index | Run indexing job against image corpus | 2–4 hours |
| 10. Install Airflow | `pip install apache-airflow + import DAGs` | 1 hour |
| 11. Update DNS / PWA config | Point `gibson.alexandriabookcoop.com` at local IP | 5 min |
| 12. Run first QLoRA fine-tuning | Load 6+ months of training data, run overnight | 8–12 hours |
| 13. Parallel run | Cloud and local in parallel for 2 weeks | 2 weeks |
| 14. Decommission cloud | After confidence is established | When ready |

### 13.2 What Migrates

- **Bibliographic database:** entire PostgreSQL via pg_dump
- **Stock Item records:** every book catalogued during Year 1, with all photos and condition Q&A logs
- **Source records:** every immutable JSONB blob from every external source query
- **Photographs:** entire R2 bucket → local disk (rclone, free egress)
- **Conversation logs:** every multi-turn cataloguing dialogue, structured for fine-tuning
- **Architectural conversations:** the markdown corpus from `/data/conversations/`
- **Decision log:** the standing-decision document
- **Correction examples:** every paired training example with provenance

### 13.3 What Doesn't Migrate

- **Claude itself.** The reasoning capability of Sonnet 4.6 cannot be downloaded. What migrates is everything Claude *did* during Year 1 — every identification, every confidence score, every synthesis — but not Claude's underlying intelligence.
- **What closes the gap:** the local Llama 70B running with the full RAG corpus, plus the first QLoRA run on the Year 1 training data. After three or four fine-tuning rounds (Months 3–6 post-migration), Llama on Gibson-specific tasks closes most of the gap. Where it doesn't, hybrid routing keeps Claude available as paid escalation.

### 13.4 The Disciplines That Make Migration Work

These three must be enforced from Day 1 of v1:

1. **The conversation logger ships with v1.** Schema in § 5.4. Not Phase 2. Not retrofit. Day 1.
2. **Every architectural conversation is exported.** Eddy's discipline: export Claude conversations to markdown, drop in `/home/eddy/conversations/`, tag by topic. Twenty per month, sixty per quarter, hundreds per year. Without this, the local LLM has no RAG corpus of cooperative reasoning.
3. **Every external endpoint is configurable.** No hardcoded URLs. Every one of `ANTHROPIC_API_BASE`, `OLLAMA_BASE_URL`, `BOOKSRUN_API`, `BOOKSCOUTER_API`, `R2_ENDPOINT`, etc. is an environment variable. Migration day = config change, not code change.

---

## 14. Build Sequence — What Gets Built When

This is the realistic build order for Year 1, assuming Nova's part-time bandwidth (he is in high school) and Eddy's full-time involvement.

### 14.1 Month 1 — Schema, Database, Fast Path

- Week 1: Schema deployed to Supabase. First API endpoint: `ping → pong`.
- Week 2: ISFDB bulk dump downloaded, parsed, loaded.
- Week 3: LOC Authority Files loaded. First `title + author → results` query.
- Week 4: BooksRun API wired. **Fast Path live.** Eddy can scan a barcode and see a result.

**Conversation logger is in v1 from Day 1.** Schema deployed in Week 1 alongside the core tables.

### 14.2 Month 2 — Standard Path, Open Library, PWA

- Open Library post-1950 English subset loaded. Dedup against ISFDB begins. BibDedupe evaluated.
- Claude Sonnet integration built. **Cover-first protocol live.** Three breakpoint responsive PWA (phone, tablet, desktop scaffolding).
- BookScouter API activated. Pricing display shows BooksRun + BookScouter.
- VIAF authority resolution wired into normalization.

### 14.3 Month 3 — Triage Path, Condition Q&A, Both Stores

- **Triage Path live.** Haiku-driven $5-fiction-shelve-it routing.
- Condition Q&A flow implemented end to end. Tap mode and Q&A mode. Dust jacket three-state. Listing description generator.
- LOC MARC catalog ingested (initial subset). Merge classifier running across ISFDB + OL + LOC.
- **Metaphysical Graffiti comes online.** Same PWA, same backend, store selector in header.
- **Cataloguing begins at scale.** Apprentices start using Gibson on real inventory.

### 14.4 Month 4 — Research Agent, Wikidata, Training Audit

- Lightweight research agent deployed on Hetzner. Single-source WorldCat lookups on Slow Path queue. Results to review queue.
- Wikidata Q-numbers ingested as crosswalking spine.
- HathiTrust + Crossref added to research agent's tier list.
- **Training data audit.** How many corrections have accumulated? Distribution by field, era, genre. Is the correction interface capturing enough signal? Adjust UI if rates are low.

### 14.5 Month 5 — Multi-Source Agent, Ghost Book Prototype, Desktop UI

- Research agent expanded: ISFDB + Printed Matter + WorldCat sweep. Llama synthesis replaced by Haiku multi-fragment synthesis. Confidence scores per field.
- **Ghost Book prototype on Xexoxial records.** Five items run through the agent. Document what it finds and what it can't. The cooperative-narrative demo.
- Desktop UI shipped: dashboard, correction queue, inventory search.

### 14.6 Month 6 — Stabilize, Document, Assess

- No new features. Clean up everything.
- Documentation for every component (CLAUDE.md kept current).
- Accuracy report with real numbers from real use at both stores.
- Training data inventory and gap analysis.
- Honest assessment of what the local server needs to unlock (Shelfie, CLIP, fine-tuning, Llama).

### 14.7 Months 7–9 — 100 Bibliographies, Foreign Language, Hardware Buy

- **100 Bibliographies ingest.** Claude reads the corpus, structures it, stores RAG + training pairs.
- **Foreign-language acceleration.** PaddleOCR-VL + DNB/BnF/BNE pre-ingest per `Nova_OCR_Memo.docx`.
- **Local server hardware purchased and assembled** (target August–September per `Summer_2026_Plan.docx`).

### 14.8 Months 10–12 — Migration, First QLoRA, Year 1 Wrap

- **Local server migration weekend.** Per § 13.
- **First QLoRA run** on accumulated Year 1 training data.
- Hybrid routing in production: local Llama default, Claude as escalation.
- **Year 1 retrospective.** What worked, what didn't, what Year 2 priorities are.

---

## 15. Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/gibson
DATABASE_POOL_SIZE=10

# Anthropic
ANTHROPIC_API_KEY=
ANTHROPIC_API_BASE=https://api.anthropic.com
ANTHROPIC_VISION_MODEL=claude-sonnet-4-6
ANTHROPIC_TRIAGE_MODEL=claude-haiku-4-5-20251001
ANTHROPIC_SYNTHESIS_MODEL=claude-haiku-4-5-20251001
ANTHROPIC_ESCALATION_MODEL=claude-opus-4-7
ANTHROPIC_ENABLE_BATCH=true
ANTHROPIC_PROMPT_CACHE=true

# Local LLM (post-migration)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:70b-q4
USE_LOCAL_LLM=false                # flip to true at migration

# Pricing APIs
BOOKSRUN_API_KEY=
BOOKSCOUTER_API_KEY=
VIALIBRI_API_KEY=                  # if/when access lands
KEEPA_API_KEY=                     # optional
EBAY_APP_ID=
EBAY_CERT_ID=
EBAY_DEV_ID=

# Channel APIs
BIBLIO_API_KEY=
WHATNOT_API_KEY=                   # if obtained, otherwise batch export

# Image Storage
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=gibson-images
LOCAL_IMAGE_PATH=/data/images
USE_LOCAL_IMAGE_STORE=false        # flip to true at migration

# Notifications
TWILIO_ACCOUNT_SID=                # for fetch alerts and want list SMS
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=

# Store Config
STORE_DL_ID=
STORE_MG_ID=

# Confidence Thresholds (tunable)
FAST_PATH_AUTO_ACCEPT=0.90
STANDARD_PATH_AUTO_ACCEPT=0.85
STANDARD_PATH_FOLLOWUP_THRESHOLD=0.60
SLOW_PATH_FALLBACK_THRESHOLD=0.50

# Pricing
PRICING_BELOW_COST_WARN=true
PRICING_BELOW_MARKET_THRESHOLD=0.40
VIALIBRI_GATE_ENFORCE=true

# Feature Flags
USE_LOCAL_CLIP=false
SHELFIE_ENABLED=false
AGENT_ENABLED=false
WHATNOT_LIVE_CAMERA=false          # Phase 10 only
TRIAGE_PATH_ENABLED=true           # Month 3+
CONVERSATION_LOGGER=true           # MUST be true from Day 1
```

---

## 16. Acceptance Criteria

The build is acceptable when, and only when, all of these are true:

### 16.1 Pipeline

- [ ] Eddy can scan a barcode at the Driftless counter and see a complete record in under 2 seconds.
- [ ] Kim can photograph an upstairs book without a barcode and see Gibson's identification with confidence score in under 6 seconds.
- [ ] Apprentices can triage a $5 first-floor paperback in under 2 seconds.
- [ ] An unknown Ghost Book gets a placeholder Stock Item, the dealer is not blocked, and the agent's overnight result lands in the review queue.

### 16.2 Pricing

- [ ] Vialibri gate is enforced. No online listing without a Vialibri lookup.
- [ ] The full pricing stack displays SOLD / ASKING / TREND with sources cited on every book.
- [ ] Field-tool pricing and research pricing share zero code paths.
- [ ] Dealer can edit suggested price freely. Below-cost and below-market warnings surface.

### 16.3 Condition

- [ ] Tap mode for under-$15 books completes in under 2 seconds.
- [ ] Q&A mode handles all 7 questions plus dust-jacket sub-questions in under 30 seconds.
- [ ] Dust jacket is three-state. Facsimile disclosure is non-suppressible.
- [ ] Listing descriptions never use VG+/VG slash format.

### 16.4 Cooperative Privacy

- [ ] Every Stock Item query enforces `store_id` filter.
- [ ] `pricing_record` table has no `store_id` column.
- [ ] Cost basis cannot be queried from another store's session.
- [ ] Audit log records cross-member queries with structural content only.

### 16.5 Migration Readiness

- [ ] Conversation logger is live from Day 1.
- [ ] Every external endpoint is a configurable environment variable.
- [ ] Eddy is exporting architectural conversations to `/home/eddy/conversations/` with topic tags.
- [ ] Source records are immutable. No code path deletes or compacts them.
- [ ] By migration day, six+ months of training data are structured and ready for QLoRA.

### 16.6 The Real Test

> Eddy picks up a book in the warehouse. Does Gibson make his day easier?

If yes, the build is right. If no, fix what's wrong, then ask again.

---

*This is a living document. When evidence changes the picture, the evidence goes in and the conclusion gets updated. Revisions are tracked at the section level. Every architectural decision herein has been made deliberately; changing one without thinking through the interlocks compromises the system.*

— Eddy Nix, Driftless Books & Music · May 2026

# CLAUDE.md — Gibson Build Instructions
# Alexandria Book Co-op
# Last updated: April 2026 (v2 — incorporates 20-question design review)

This file is the authoritative instruction set for building Gibson.
Read it completely before writing a single line of code.
When in doubt, re-read this file before asking a question.

---

## What Gibson Is

Gibson is the bibliographic intelligence system of the Alexandria Book Co-op. Its job,
in order of priority: identify a book from a photograph, price it against real market
data, catalogue it into a cooperative database, and list it for sale.

Gibson is a field tool first. Everything else — the cooperative marketplace, the
community authentication layer, the Ghost Book pipeline, the Shelfie inventory system —
is built on top of a working field tool. Build the field tool first.

Gibson always has an opinion. It reads what it can see, makes the most informed
recommendation it can, shows its reasoning, and asks the dealer to confirm or override
with one tap. It is a knowledgeable colleague, not a form waiting to be filled out.
This interaction model applies uniformly: identification routing, pricing decisions,
condition grading, section placement, listing decisions. Gibson prompts the logical
choice. The dealer is always final.

---

## What This Codebase Is

- **Backend:** Python / FastAPI
- **Frontend:** Progressive Web App (vanilla JS, no framework)
- **Database:** PostgreSQL (raw SQL migrations only — no ORM)
- **Vision / AI:** Anthropic API (Sonnet for identification, Haiku for synthesis)
- **Local LLM (post-migration):** Ollama + Llama 3 8B
- **Deployment:** Cloud-first (Supabase + Railway + Cloudflare R2) for Month 1,
  then migrates to local server at Driftless Books & Music, Viroqua, Wisconsin

This is not a prototype. Write production code from Day 1.
Every shortcut is technical debt against a cooperative with no engineering staff to pay it down.

---

## The Two Stores

**Driftless Books & Music**
518 Walnut Street, Viroqua, Wisconsin 54665
Former tobacco warehouse. Two operational floors.
- First floor: ~100,000 hand-priced uncatalogued books, customer browsing
- Second floor: ~50,000 catalogued + ~200,000 unresearched, restricted access
SKU prefix: DL-

**Metaphysical Graffiti**
1919-era storefront, Viroqua. Smaller than Driftless.
Fully uncatalogued stock, all pencil-priced. Single floor.
Specialty: metaphysics, radical politics, homesteading, conspiracy, SF paperbacks.
eBay room in back: physical location of the 700 separate eBay listings.
Connected internally to Bad Axe Music (Scott, vinyl, local only — not Gibson's concern)
and Room for Comics (Al — out of scope for this build, Year 3+).
SKU prefix: MG-

Both stores share one database, one API. Store context via JWT claim on every request.
Every Stock Item, Location, and Sale Record carries store_id.
SKU prefix is the human-readable store indicator.

---

## Standing Decisions — Do Not Relitigate

These are resolved. If a future instruction appears to contradict them,
flag the conflict rather than complying silently.

- **Local-first is the destination.** Cloud is the starting point. Every cloud service
  must have a documented local replacement. No lock-in that cannot be unwound in a weekend.

- **Work → Edition → Stock Item** is the schema. FRBR-aligned. Non-negotiable.
  Do not flatten this for convenience.

- **Publisher and Agent are entity tables** with authority record support. Not string fields.

- **Confidence scores are always visible.** Every identification, price estimate, and
  bibliographic claim carries a confidence score and source citation.

- **The correction interface is the most critical software after the photo pipeline.**
  The training loop depends entirely on it. Build it well.

- **The research agent never writes directly to the catalog.**
  Every candidate record goes to human review. No exceptions.

- **Vialibri is the pricing gate.** No Vialibri comps = no online listing without an
  explicit dealer decision (IN_STORE_ONLY or PRICING_RESEARCH queue).

- **BooksRun is low-weight.** Fire on all ISBNs, weight near zero pre-1990 and specialist.

- **Gibson always prompts the logical choice.** One tap. Never a blank form.

- **Ghost Book is a first-class pipeline path.** Not a plugin, not an edge case.

- **No cooperative governance scaffolding.** Attribution logging only — who did what,
  timestamped. Credits, dividends, member classes come later.

- **Raw SQL migrations only.** Alembic for tracking. No ORM hiding the SQL.

- **BibDedupe before custom dedup.** Evaluate it. Measure it. Only write custom
  code if it fails.

- **Pricing is Day 1.** Vialibri and eBay fire with every identification. Not Month 7.

- **Comics and vinyl are out of scope** for this build. Year 3+ at earliest.

- **Member data privacy is enforced at the database query level**, not application logic.
  store_id filters are mandatory on all Stock Item queries. See cooperative data
  governance section below.

---

## What Claude Code Should Never Do

- Introduce a cloud service without documenting its local replacement in .env.example
- Flatten Work / Edition / Stock Item for convenience
- Write AI output directly to catalog without human review
- Hide confidence scores from any user-facing output
- Present AI price estimates as market data
- List a book online when Vialibri returns empty without explicit dealer decision
- Build governance, credit, or dividend features before the field tool works
- Treat Ghost Book as an edge case
- Use an ORM that hides the SQL
- Write deduplication code before evaluating BibDedupe
- Allow one member's Stock Item data to be visible to another member
- Expose cost basis to anyone other than the owning store

---

## Repository Layout

```
gibson/
├── CLAUDE.md
├── README.md
├── .env.example                    # every environment variable documented
├── docker-compose.yml              # local dev: postgres + api
├── docker-compose.prod.yml         # cloud deployment
│
├── api/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── routers/
│   │   ├── identification.py
│   │   ├── pricing.py
│   │   ├── catalogue.py
│   │   ├── inventory.py
│   │   ├── pos.py
│   │   ├── research.py
│   │   ├── ghostbook.py
│   │   ├── shelfie.py
│   │   ├── whatnot.py              # show mode: playlist + live_camera
│   │   └── customer.py
│   ├── services/
│   │   ├── vision.py
│   │   ├── ocr.py
│   │   ├── barcode.py
│   │   ├── triage.py
│   │   ├── pricing/
│   │   │   ├── vialibri.py
│   │   │   ├── ebay.py
│   │   │   ├── booksrun.py
│   │   │   ├── bookscouter.py
│   │   │   └── aggregator.py
│   │   ├── channels/
│   │   │   ├── amazon.py           # selective: ISBN-present post-1970 only
│   │   │   ├── biblio.py           # full catalogued inventory
│   │   │   ├── ebay_listings.py    # existing 700 + new selective
│   │   │   ├── website.py          # Gibson is the backend
│   │   │   └── whatnot_export.py   # batch export for shows
│   │   ├── deduplication.py
│   │   ├── correction.py
│   │   └── research_agent.py
│   ├── models/
│   └── tests/
│
├── pwa/
│   ├── index.html
│   ├── manifest.json
│   ├── service-worker.js
│   └── src/
│       ├── views/
│       │   ├── camera.js
│       │   ├── identify.js
│       │   ├── pricing.js
│       │   ├── condition.js
│       │   ├── catalogue.js
│       │   ├── inventory.js
│       │   ├── pos.js
│       │   ├── shelfie.js
│       │   ├── research.js
│       │   ├── whatnot_show.js     # playlist mode + live camera mode
│       │   └── customer/
│       │       ├── browse.js
│       │       ├── search.js
│       │       ├── wantlist.js
│       │       └── visit.js        # "I'm coming Saturday" scheduling
│       ├── components/
│       └── lib/
│
├── db/
│   ├── migrations/
│   │   ├── 001_schema_core.sql
│   │   ├── 002_schema_store.sql
│   │   ├── 003_schema_training.sql
│   │   ├── 004_schema_ghostbook.sql
│   │   └── 005_indexes.sql
│   └── seeds/
│       ├── stores.sql              # DL and MG store records
│       ├── sections_dl.sql         # Driftless section list (from master list photo)
│       └── sections_mg.sql         # MG section list (TBD)
│
├── agent/
│   ├── runner.py
│   ├── sources/
│   │   ├── worldcat.py
│   │   ├── isfdb.py
│   │   ├── printed_matter.py
│   │   ├── zinecat.py              # scrape inbound; contribution waits for Sullivan
│   │   └── dealer_sites.py
│   ├── synthesis.py
│   └── ghostbook_agent.py
│
├── scripts/
│   ├── ingest/
│   │   ├── isfdb_import.py
│   │   ├── openlibrary_import.py
│   │   ├── loc_marc_import.py
│   │   ├── loc_authorities_import.py
│   │   ├── kazam_import.py         # 37,967 records, tab-delimited
│   │   └── amazon_import.py        # flat file, trust tier 2
│   └── maintenance/
│       ├── dedup_run.py
│       ├── channel_sync.py         # 15-minute sync cycle
│       └── training_export.py
│
└── training/
    ├── datasets/
    │   ├── bibliographic/
    │   ├── condition/
    │   └── pricing/
    ├── qlora/
    └── eval/
```

---

## Database Schema

### 001_schema_core.sql

```sql
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE agent (
    agent_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name_display     TEXT NOT NULL,
    name_sort        TEXT NOT NULL,
    name_variants    TEXT[] DEFAULT '{}',
    agent_type       TEXT NOT NULL CHECK (agent_type IN (
                         'person','corporate','collective','unknown')),
    authority_source TEXT,
    authority_id     TEXT,
    notes            TEXT,
    created_at       TIMESTAMPTZ DEFAULT now(),
    updated_at       TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE publisher (
    publisher_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name_display        TEXT NOT NULL,
    name_sort           TEXT NOT NULL,
    name_variants       TEXT[] DEFAULT '{}',
    parent_publisher_id UUID REFERENCES publisher(publisher_id),
    publisher_type      TEXT NOT NULL CHECK (publisher_type IN (
                            'commercial','university_press','small_press',
                            'self_published','collective','unknown')),
    founded_year        INT,
    dissolved_year      INT,
    country             TEXT,
    authority_source    TEXT,
    authority_id        TEXT,
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE work (
    work_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title          TEXT NOT NULL,
    title_sort     TEXT NOT NULL,
    subtitle       TEXT,
    language       TEXT DEFAULT 'en',
    work_type      TEXT NOT NULL CHECK (work_type IN (
                       'monograph','anthology','periodical','zine',
                       'ephemera','manuscript','recording','mixed_media')),
    subject_terms  TEXT[] DEFAULT '{}',
    genre_terms    TEXT[] DEFAULT '{}',
    notes          TEXT,
    confidence     NUMERIC(3,2) DEFAULT 1.0,
    created_at     TIMESTAMPTZ DEFAULT now(),
    updated_at     TIMESTAMPTZ DEFAULT now(),
    created_by     UUID
);

CREATE TABLE work_agent (
    work_id                UUID REFERENCES work(work_id),
    agent_id               UUID REFERENCES agent(agent_id),
    role                   TEXT NOT NULL CHECK (role IN (
                               'author','editor','compiler',
                               'illustrator','photographer','contributor')),
    role_order             INT DEFAULT 1,
    attribution_confidence NUMERIC(3,2) DEFAULT 1.0,
    attribution_source     TEXT,
    PRIMARY KEY (work_id, agent_id, role)
);

CREATE TABLE edition (
    edition_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    work_id                  UUID NOT NULL REFERENCES work(work_id),
    isbn_13                  TEXT UNIQUE,
    isbn_10                  TEXT,
    title_on_piece           TEXT,
    edition_statement        TEXT,
    publication_year         INT,
    publication_year_uncertainty TEXT,
    printing_number          INT,
    number_line              TEXT,
    format                   TEXT CHECK (format IN (
                                 'hardcover','paperback','mass_market_paperback',
                                 'trade_paperback','spiral','stapled','loose_leaf',
                                 'broadside','chapbook','zine','other')),
    page_count               INT,
    dimensions_cm            TEXT,
    series_name              TEXT,
    series_number            TEXT,
    print_run                INT,
    is_limited_edition       BOOLEAN DEFAULT false,
    limitation_note          TEXT,
    cover_image_url          TEXT,
    source_record_ids        UUID[] DEFAULT '{}',
    confidence               NUMERIC(3,2) DEFAULT 1.0,
    notes                    TEXT,
    created_at               TIMESTAMPTZ DEFAULT now(),
    updated_at               TIMESTAMPTZ DEFAULT now(),
    created_by               UUID
);

CREATE TABLE edition_agent (
    edition_id  UUID REFERENCES edition(edition_id),
    agent_id    UUID REFERENCES agent(agent_id),
    role        TEXT NOT NULL CHECK (role IN (
                    'translator','illustrator','introducer',
                    'editor','designer','photographer')),
    role_order  INT DEFAULT 1,
    PRIMARY KEY (edition_id, agent_id, role)
);

CREATE TABLE edition_publisher (
    edition_id   UUID REFERENCES edition(edition_id),
    publisher_id UUID REFERENCES publisher(publisher_id),
    role         TEXT NOT NULL CHECK (role IN (
                     'publisher','distributor','printer','imprint')),
    role_order   INT DEFAULT 1,
    PRIMARY KEY (edition_id, publisher_id, role)
);

CREATE TABLE source_record (
    source_record_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name        TEXT NOT NULL,
    source_id          TEXT,
    raw_data           JSONB NOT NULL,
    normalized_data    JSONB,
    matched_work_id    UUID REFERENCES work(work_id),
    matched_edition_id UUID REFERENCES edition(edition_id),
    match_confidence   NUMERIC(3,2),
    ingested_at        TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE stock_item (
    stock_item_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    edition_id          UUID NOT NULL REFERENCES edition(edition_id),
    gibson_sku          TEXT UNIQUE,        -- JS-1213, KK-3412 (employee initials + seq)
    seller_sku          TEXT,               -- Amazon ASIN or Kazam ID alias
    store_id            UUID NOT NULL,      -- NEVER query without this filter
    location_id         UUID,
    condition_grade     TEXT CHECK (condition_grade IN (
                            'Fine','Very Good+','Very Good','Good+',
                            'Good','Fair','Poor')),
    condition_dj        TEXT,
    condition_notes     TEXT,
    condition_qa_log    JSONB,              -- full Q&A preserved (upstairs/online only)
    condition_mode      TEXT DEFAULT 'tap' CHECK (condition_mode IN ('tap','qa')),
    status              TEXT NOT NULL DEFAULT 'AVAILABLE' CHECK (status IN (
                            'AVAILABLE','LISTED','SOLD','HOLD',
                            'IN_STORE_ONLY','PRICING_RESEARCH',
                            'PENDING_IDENTIFICATION','PENDING_REVIEW',
                            'GHOST_BOOK_QUEUE','WITHDRAWN')),
    listing_channels    TEXT[] DEFAULT '{}', -- 'amazon','biblio','website','ebay','whatnot'
    asking_price        NUMERIC(10,2),
    cost_basis          NUMERIC(10,2),      -- NEVER exposed outside owning store
    images              TEXT[] DEFAULT '{}',
    is_signed           BOOLEAN DEFAULT false,
    is_inscribed        BOOLEAN DEFAULT false,
    inscription_note    TEXT,
    is_association_copy BOOLEAN DEFAULT false,
    provenance_notes    TEXT,
    whatnot_showed      BOOLEAN DEFAULT false,  -- was shown on Whatnot show
    whatnot_showed_at   TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now(),
    created_by          UUID
);
```

### 002_schema_store.sql

```sql
CREATE TABLE store (
    store_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name       TEXT NOT NULL,
    prefix     TEXT NOT NULL,   -- 'DL', 'MG'
    address    TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE location (
    location_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id     UUID NOT NULL REFERENCES store(store_id),
    floor        TEXT,           -- 'First Floor', 'Second Floor'
    section      TEXT,           -- 'Fiction', 'Science Fiction', 'MG-Metaphysics'
    section_code TEXT,           -- pencil system code
    subsection   TEXT,           -- alpha shelf: 'A-F', 'G'
    shelf_unit   TEXT,
    slot         TEXT,
    notes        TEXT
);

CREATE TABLE employee (
    employee_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id     UUID REFERENCES store(store_id),
    name         TEXT NOT NULL,
    initials     TEXT NOT NULL,  -- 'JS', 'KK' — used in SKU generation
    role         TEXT,
    pin          TEXT,           -- hashed
    created_at   TIMESTAMPTZ DEFAULT now()
);

-- SKU sequence per employee
CREATE SEQUENCE sku_seq_global START 1000;
-- SKU format: employee.initials || '-' || nextval('sku_seq_global')
-- JS-1213, KK-3412. No store prefix. Store lives in section field.

CREATE TABLE sale_record (
    sale_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id       UUID NOT NULL REFERENCES store(store_id),
    employee_id    UUID REFERENCES employee(employee_id),
    sale_timestamp TIMESTAMPTZ DEFAULT now(),
    total_amount   NUMERIC(10,2),
    tax_amount     NUMERIC(10,2),
    payment_method TEXT,
    customer_id    UUID,
    notes          TEXT
);

CREATE TABLE sale_item (
    sale_item_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sale_id        UUID NOT NULL REFERENCES sale_record(sale_id),
    stock_item_id  UUID NOT NULL REFERENCES stock_item(stock_item_id),
    asking_price   NUMERIC(10,2),
    realized_price NUMERIC(10,2) NOT NULL,
    discount_reason TEXT
);

CREATE TABLE buy_queue (
    buy_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id      UUID REFERENCES store(store_id),
    employee_id   UUID REFERENCES employee(employee_id),
    customer_id   UUID REFERENCES customer(customer_id),
    status        TEXT DEFAULT 'PENDING' CHECK (status IN (
                      'PENDING','OFFERED','ACCEPTED','DECLINED','COMPLETE')),
    haul_images   TEXT[] DEFAULT '{}',  -- photos of boxes/bags at intake
    cash_offer    NUMERIC(10,2),
    credit_offer  NUMERIC(10,2),
    offer_accepted_at TIMESTAMPTZ,
    notes         TEXT,
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ DEFAULT now()
);

-- Buy queue closes at counter with cash/credit offer.
-- Books enter processing queue after acceptance.
-- Per-book identification happens later through normal pipeline.

CREATE TABLE customer (
    customer_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT,
    email       TEXT UNIQUE,
    phone       TEXT,
    auth_token  TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE want_list (
    want_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID REFERENCES customer(customer_id),
    query_text  TEXT NOT NULL,
    work_id     UUID REFERENCES work(work_id),
    agent_id    UUID REFERENCES agent(agent_id),
    status      TEXT DEFAULT 'ACTIVE',
    notified_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Want list fires on CONFIRMED CATALOGUED match only.
-- Also surfaces as dealer alert on dashboard:
-- "3 customers want Edward Abbey — you have uncatalogued stock upstairs"

CREATE TABLE visit_schedule (
    visit_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id  UUID REFERENCES customer(customer_id),
    store_id     UUID REFERENCES store(store_id),
    visit_date   DATE NOT NULL,
    arrival_time TEXT,
    wants_note   TEXT,           -- "looking for Abbey, Berry, anything Wisconsin"
    prep_note    TEXT,           -- employee prep notes
    status       TEXT DEFAULT 'SCHEDULED' CHECK (status IN (
                     'SCHEDULED','PREPPED','VISITED','CANCELLED')),
    created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE pricing_record (
    pricing_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    edition_id      UUID REFERENCES edition(edition_id),
    source          TEXT NOT NULL,
    price_type      TEXT NOT NULL CHECK (price_type IN ('asking','realized','trend')),
    amount          NUMERIC(10,2),
    currency        TEXT DEFAULT 'USD',
    condition_grade TEXT,
    url             TEXT,
    retrieved_at    TIMESTAMPTZ DEFAULT now(),
    listing_date    DATE
    -- NO store_id or member attribution on pricing records
    -- Realized prices are cooperative commons, stripped of member identity
);
```

### 003_schema_training.sql

```sql
CREATE TABLE correction (
    correction_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stock_item_id    UUID REFERENCES stock_item(stock_item_id),
    edition_id       UUID REFERENCES edition(edition_id),
    field_name       TEXT NOT NULL,
    original_value   TEXT,
    corrected_value  TEXT,
    corrected_by     UUID REFERENCES employee(employee_id),
    correction_reason TEXT,
    gibson_original_confidence NUMERIC(3,2),  -- was Gibson confident when it got it wrong?
    concern_level    TEXT DEFAULT 'MEDIUM' CHECK (concern_level IN ('HIGH','MEDIUM','LOW')),
    is_training_pair BOOLEAN DEFAULT false,
    reviewed_by      UUID REFERENCES employee(employee_id),
    created_at       TIMESTAMPTZ DEFAULT now()
);

-- Concern level rules (set automatically by the correction service):
-- HIGH: bibliographic field on book >$25, conflicts with source record,
--       Gibson confidence was >85%, or same field corrected by multiple people
-- MEDIUM: condition override on online-listed book, price >40% from Vialibri comps,
--         any Ghost Book correction
-- LOW: first-floor commodity condition tap, section change, Gibson confidence <50%

CREATE TABLE training_example (
    example_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    example_type  TEXT NOT NULL CHECK (example_type IN (
                      'bibliographic_extraction','condition_grade',
                      'pricing_decision','routing_decision',
                      'ghost_book_identification')),
    input_data    JSONB NOT NULL,
    output_data   JSONB NOT NULL,
    source        TEXT,
    quality_score NUMERIC(3,2),
    reviewed      BOOLEAN DEFAULT false,
    created_at    TIMESTAMPTZ DEFAULT now()
);
```

### 004_schema_ghostbook.sql

```sql
CREATE TABLE ghost_book_record (
    ghost_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stock_item_id        UUID REFERENCES stock_item(stock_item_id),
    collection_name      TEXT,
    physical_description TEXT,
    date_range           TEXT,
    attribution_notes    TEXT,
    research_status      TEXT DEFAULT 'UNRESEARCHED' CHECK (research_status IN (
                             'UNRESEARCHED','IN_QUEUE','AGENT_COMPLETE',
                             'HUMAN_REVIEW','CONFIRMED','CONTRIBUTED_BACK')),
    agent_candidate      JSONB,
    confidence_map       JSONB,
    sources_searched     TEXT[] DEFAULT '{}',
    contributed_to_zuc   BOOLEAN DEFAULT false,
    contributed_at       TIMESTAMPTZ,
    created_at           TIMESTAMPTZ DEFAULT now(),
    updated_at           TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE ghost_book_source_hit (
    hit_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ghost_id        UUID REFERENCES ghost_book_record(ghost_id),
    source_name     TEXT NOT NULL,
    source_url      TEXT,
    raw_content     TEXT,
    relevance_score NUMERIC(3,2),
    retrieved_at    TIMESTAMPTZ DEFAULT now()
);
```

### 005_indexes.sql

```sql
CREATE INDEX idx_edition_isbn13 ON edition(isbn_13);
CREATE INDEX idx_edition_work ON edition(work_id);
CREATE INDEX idx_stock_item_edition ON stock_item(edition_id);
CREATE INDEX idx_stock_item_gibson_sku ON stock_item(gibson_sku);
CREATE INDEX idx_stock_item_seller_sku ON stock_item(seller_sku);
CREATE INDEX idx_stock_item_status ON stock_item(status);
CREATE INDEX idx_stock_item_store ON stock_item(store_id);
CREATE INDEX idx_stock_item_store_status ON stock_item(store_id, status);
CREATE INDEX idx_work_title_sort ON work(title_sort);
CREATE INDEX idx_agent_name_sort ON agent(name_sort);
CREATE INDEX idx_publisher_name_sort ON publisher(name_sort);
CREATE INDEX idx_pricing_record_edition ON pricing_record(edition_id);
CREATE INDEX idx_pricing_record_source ON pricing_record(source);
CREATE INDEX idx_correction_concern ON correction(concern_level, reviewed_by);
CREATE INDEX idx_ghost_book_status ON ghost_book_record(research_status);
CREATE INDEX idx_visit_schedule_date ON visit_schedule(store_id, visit_date);
CREATE INDEX idx_work_title_fts ON work USING gin(to_tsvector('english', title));
CREATE INDEX idx_agent_name_fts ON agent USING gin(to_tsvector('english', name_display));
```

---

## SKU System

Format: employee initials + sequential number. JS-1213, KK-3412.
No store prefix. Store lives in the section/location field.
Pencil on front free endpaper, top right corner. Small and consistent.

Current employees and initials:
- Jill: JS
- Kim: KK
- Add others in the employee seed data

Sequence is global, not per-employee. Numbers never reissued.
Imported books carry their Amazon ASIN or Kazam ID in `seller_sku` as alias.
Either can be searched. Gibson SKU is what gets written in pencil.

---

## Identification Pipeline

### Camera Interface

PWA single-page view. Camera opens immediately. ZXing-js barcode detection
runs continuously on live viewfinder. Barcode detected = fires immediately,
no photo needed.

For non-barcode books: one cover photo. Gibson processes, asks for more only
if needed, says exactly what it needs and why.

```
CAPTURE FLOW

1. Camera opens, ZXing-js on live feed
2a. Barcode detected → Fast Path fires. Green flash.

2b. No barcode after 3 seconds → "Take cover photo"
    → Image quality check
    → Quality fail: specific instruction ("Too dark — try again")
    → Quality pass → Standard Path fires

3. Confidence ≥ 85% → one-tap confirm
4. Confidence < 85% → Gibson requests exactly one more photo, says why
5. Still < 85% → Gibson prompts:
   "Queue for overnight research, or mark in-store only?"
```

### Fast Path — Barcode

```
Decode → ISBN-13 normalize → check digit validate
→ Local DB lookup ←─── parallel ───→ Vialibri
                  ←─── parallel ───→ eBay sold
                  ←─── parallel ───→ BooksRun (low weight)

Gibson presents: title, author, edition, price range, suggested section.
Example: "Very Good. Vialibri $8–$14, eBay sold $11 avg. Suggest $10. Biography?"
Target: under 5 seconds.
```

### Standard Path — Cover Photo

```
Cover image → EasyOCR + PaddleOCR ensemble
→ Claude Vision (claude-sonnet-4-6): image + OCR text always
  (hybrid always — never image alone — architectural invariant)
→ Structured JSON, ~5-6 seconds, per-field confidence scores
→ ≥ 85%: present result
→ < 85%: request one targeted photo with plain-language explanation
→ Pricing fires when identification clears 70%
```

### Gibson Asks — Targeted Follow-Up

```
Gibson asks for exactly one thing. Never "I need more information."

"Copyright page — I can see this is Ballantine but need the year."
"Title page — spine is ambiguous between two editions."
"Is there a number line on the copyright page?" (yes/no, no photo)
"Does it say 'First Edition' on the copyright page?" (yes/no)
```

### Slow Path

```
Triggers: confidence below threshold after two images, OCR failure,
vision API timeout, Ghost Book material, dealer routes there manually.

→ Placeholder Stock Item (PENDING_IDENTIFICATION)
→ All images attached, partial OCR preserved
→ Optional dealer note
→ Gibson prompts: "Queue for overnight research, or in-store only?"
→ Overnight agent at 2 AM → candidate record → human review queue
→ Nothing reaches catalog without human approval
→ Dealer notified when ready
```

### Shelf Scan Mode

```
Wide angle, shelf orientation. 10–30 spines.
YOLOv8n spine detection → EasyOCR per spine → database match

Results overlaid:
  GREEN  = matched, location confirmed
  YELLOW = matched, location conflicts with record
  RED    = not in database (potential underpriced book)
  GREY   = OCR failed

RED items where Gibson has pricing data:
→ "This $5 book has $40 Vialibri comps. Pull for upstairs?"

Runs overnight batch or on-demand with progress bar.
```

---

## Condition System

Two modes. Gibson determines which before asking anything.

**Tap mode (first floor / commodity / under $15):**
Single tap — Fine / VG+ / VG / Good / Reading Copy. No questions.

**Q&A mode (upstairs / online listing / $15 and above):**
Seven questions. Generated condition description. DJ grade if applicable.
Dealer can override suggested grade at any point.

Condition grade mapping and language generation per existing pipeline spec.
Every Q&A session preserved in `condition_qa_log` on Stock Item.
Every dealer override of Gibson's suggested grade is a training signal.

---

## Pricing Layer

### The Rule

Vialibri is the gate. No comps = no online listing without explicit dealer decision.
eBay sold is the realized price layer. Dealer price is always final.

### Stack — All Parallel

```
SOURCE          TYPE        WEIGHT    NOTES
────────────────────────────────────────────────────────────
Gibson POS      Realized    Highest   Our own sales. Compounds.
eBay sold       Realized    High      Labeled: SOLD
Vialibri        Asking      High      Gate. Labeled: ASKING
eBay active     Asking      Medium    Labeled: ASKING
BooksRun        Asking      Low       Post-1990 only. ~zero pre-1990.
BookScouter     Trend       Supp.     Labeled: TREND
Claude Haiku    Estimate    Last      Only when all sources empty.
                                      Labeled: AI ESTIMATE — NO MARKET DATA
────────────────────────────────────────────────────────────
```

### Vialibri Gate

```
Vialibri returns comps → proceed to listing
  Gibson: "Vialibri $9–$14, eBay sold $11. Suggest $10. Biography?"

Vialibri returns empty → Gibson prompts logical choice:
  "Nothing on Vialibri. Price $3 and keep in-store, or queue for research?"

  IN_STORE_ONLY: hand price, no online listing, visible in customer app
                 as browsable but not orderable

  PRICING_RESEARCH: overnight agent runs expanded search:
    - eBay completed (title/author, not just ISBN)
    - BookFinder / AddAll
    - Heritage Auctions realized prices
    - Dealer site scraping
    Agent returns comps with sources cited.
    Human reviews. Gibson presents result. Dealer decides.
```

### Price Display

```
SOLD (realized)
  Gibson POS:    $12.00   (1 sale, 2024)
  eBay:          $8–$18   (6 sales, last 90 days)

ASKING (market)
  Vialibri:      $9–$14   (3 copies)
  eBay active:   $7–$22   (8 listings)

TREND
  BookScouter:   ↓ slight  (6 month)

─────────────────────────────
YOUR PRICE:    [ $10.00 ]    ← always editable
SECTION:       Biography     ← Gibson suggestion, tappable
```

---

## Channel Routing

One database, every marketplace. Single source of truth.
Book sold on any channel → status SOLD → all channels synced within 15 minutes.

```
CHANNEL         INVENTORY           NOTES
────────────────────────────────────────────────────────────────
Biblio          Full catalogued     Full sync. Primary trade channel.
Website         Full catalogued     Gibson is the backend. Day 1.
Amazon          Selective           ISBN-present, post-1970 only.
                                    No lots. No Ghost Book.
eBay            Selective           Existing 700 listings at MG managed
                                    separately. New listings selective.
Whatnot         Show-by-show        Batch export + show mode. See below.
In-store        All stock           First floor always IN_STORE_ONLY.
                                    Upstairs available for fetch alerts.
────────────────────────────────────────────────────────────────
```

### Whatnot Show Mode

Two sub-modes in `whatnot.py` and `whatnot_show.js`:

**Batch prep (before show):**
- Dealer photographs pile or individual books
- Gibson identifies, pulls bibliographic data
- Generates Whatnot-voice description (punchy, collector-facing, not catalogue-dry)
- For lots: "lot of X books including..." — flags what it couldn't identify
- User amends description, sets starting bid
- Gibson suggests show sequence: accessible books early, strong items mid-show,
  anchor items near end
- Export batch file for upload OR direct API if Whatnot access obtained
- Starting prices suggested from Vialibri + eBay sold

**Live show mode (during show):**

Sub-mode A — Playlist:
- Pre-sequenced show order loaded into Gibson
- Anchor or second person taps to advance each book
- Gibson surfaces full record + talking points on display screen
- Real-time comp display: what similar copies sold for recently
- Want list matching: notifies registered customers via SMS when their wanted
  book comes up in the show

Sub-mode B — Live Camera (Phase 10):
- Phone or laptop camera pointed at book anchor is holding
- Gibson watches feed, identifies book from cover in real time
- Same Standard Path pipeline running continuously on video feed
- 5–6 second latency from hold-up to record surface
- Anchor glances at display, picks up the detail, mentions on camera

**After show:**
- Every sold item marked SOLD immediately, removed from all channels
- Realized prices feed directly into pricing corpus
- Unsold items returned to AVAILABLE with `whatnot_showed = true` flag
  (signal: price may be wrong or audience wasn't right for this book)

---

## Buy Queue

Closes at the counter. Not a research workflow.

```
INTAKE FLOW

1. Open new buy queue entry
2. Photograph the haul (boxes, bags — whatever came in)
3. Attach or create customer record (name, phone, email)
4. Record offer: cash / store credit / combination
5. Mark paid — transaction closes, receipt generated
6. Books enter IN_QUEUE status, awaiting processing
7. Each book processed normally when bookseller gets to it:
   photograph → identify → price → SKU → location
```

Customer record carries purchase history. Repeat sellers recognized instantly.
Offer history visible on customer record.

---

## POS & Counter Flow

```
COUNTER FLOW

1. Tap "Sale"
2. Camera opens — auto-capture on cover
3. Catalogued book: type SKU (JS-1213) → full record, price auto-fills
   Uncatalogued: type section code + price ("K 5" = Fiction, $5.00)
4. Section code carries forward across multi-book sale
5. Next book — repeat
6. Close sale: tax, total, payment method
7. Confirm — receipt (print or SMS via Twilio)

Every book sold:
  → Photograph captured
  → Realized price → pricing_record immediately (no store attribution)
  → Timestamp + employee attribution
  → Stock Item → SOLD
  → All listing channels synced within 15 minutes
  → Background identification for uncatalogued books
```

### Kim's Two Interfaces

**Phone (employee.pwa — mobile view):**
Fast, single-task screens. Visit schedule, want list prep notes,
fetch alerts, counter POS, condition tap, SKU lookup.
What she needs while moving through the store.

**Desktop (employee.pwa — wide view):**
Full inventory search, pricing lookup for difficult cases,
customer record management. Same PWA, responsive layout.
Not the overnight research queue (that's Eddy's).

### Fetch Alert

Customer in store taps "Get this for me" on a catalogued upstairs book.
Every employee PWA receives SMS (Twilio) with title, price, exact location.
Employee claims it. Customer's screen shows "Kim is getting your book."
SMS not PWA push — works on every device regardless of OS.
Low priority, Phase 7.

---

## Customer App

Same PWA, customer-facing route. QR code at the door. No download, no login to browse.

```
PUBLIC (no login):
  Search by title, author, subject, section
  Browse by section
  View catalogued books: title, condition, price, location
  New arrivals feed

ACCOUNT (magic link email auth):
  Want list — SMS notification on confirmed catalogued match only
  Purchase history
  Visit scheduling:
    "I'm coming Saturday, looking for Abbey, Berry, anything Wisconsin"
    → surfaces on employee dashboard as upcoming visit with prep notes
    → Kim pulls what she can before customer arrives
  Fetch alert

DEALER DASHBOARD (want list intelligence):
  "14 customers want Edward Abbey — you have uncatalogued stock upstairs"
  "37 searches for graphic novels found nothing"
  Upcoming visits with prep notes
  Slow movers: high want-list + no sale = overpriced signal
```

---

## Correction Engine & Training Loop

### Correction Queue

Everything goes to Eddy. Gibson sorts by concern level.
One-tap approve / reject. Batch approve all LOW with one button.
Rejection kicks back to corrector with optional note field.

```
HIGH — review first:
  Bibliographic field on book >$25
  Conflicts with a source record
  Gibson confidence was >85% and it got corrected
  Same field corrected by multiple people

MEDIUM — review when you have time:
  Condition override on online-listed book
  Price >40% from Vialibri comps
  Any Ghost Book record correction

LOW — batch approve or spot-check:
  First-floor commodity condition tap
  Section placement change
  Gibson confidence was <50% (wasn't sure anyway)
```

### Three Learning Loops

```
FAST (real-time): evidence layer updates on every interaction
MEDIUM (overnight): agent fills gaps, pricing records accumulate
SLOW (quarterly, local GPU): QLoRA fine-tuning on accumulated data
  Datasets:
    bibliographic_extraction  target: 500+ verified before first run
    condition_grade           target: 1,000+ Q&A records
    pricing_decision          target: 500+ dealer decisions with comps
```

Training infrastructure built Day 1. Data collected now, training runs when
server arrives. No cold start.

---

## Research Agent

### Month 1–3: Haiku Synthesis Only

Claude Haiku receives everything Gibson knows about unidentified book.
Returns candidate record with per-field confidence scores.
Labeled as drawing on model training knowledge, not current data.

### Month 4+: Full Agent Stack

Hetzner CX22 VM. Cron at 2 AM.
smolagents + ScrapeGraphAI + Playwright + DuckDuckGo + Claude Haiku

Standard source routing:
→ WorldCat → ISFDB (genre signals) → DuckDuckGo + ScrapeGraphAI → dealer sites

Ghost Book source routing:
→ ZineCat (scrape inbound — contribution pipeline waits for Sullivan relationship)
→ Printed Matter → Internet Archive → mail art archives → HathiTrust
→ DuckDuckGo + ScrapeGraphAI on dealer descriptions

Heritage Auctions: Playwright (JS-rendered), realized prices for rare material.

**ZineCat note:** CollectiveAccess REST API may be exposed at zinecat.org/index.php/api
— Nova checks in one afternoon. If open, scrape is straightforward. If not,
Playwright scrape of web interface. ~31,000 records, one-time import + periodic refresh.
Contribution back requires Sullivan to establish relationship and get contributor account.
Nova then builds xZINECOREx format export. Until then, inbound only.

---

## Cooperative Data Governance

### What Every Member Sees
- Full bibliographic database (Work, Edition, Agent, Publisher) — cooperative commons
- Realized prices in aggregate, no member attribution
- Collective copy count by title (count only, no member detail, no location)
- Confidence scores and source citations on all records

### What No Member Sees
- Another member's cost basis — ever
- Another member's asking prices before public listing
- Another member's inventory details (what they have, where, condition)
- Another member's sales volume, revenue, transaction history
- Another member's correction history or identification patterns

### Implementation
Enforced at database query level, not application logic.
Every Stock Item query MUST include store_id filter.
Pricing corpus strips member attribution before storage (no store_id on pricing_record).
Cost basis never exposed outside owning store's dashboard.
This is not a permission system. It is a data architecture decision.
Member A's stock simply does not appear in Member B's queries.

---

## Infrastructure & Deployment

### Cloud-First Stack (Month 1)

```
SERVICE          PROVIDER          COST/MO    LOCAL REPLACEMENT
──────────────────────────────────────────────────────────────
PostgreSQL       Supabase Pro      $25        Local PostgreSQL
FastAPI          Railway           $10        systemd service
Image storage    Cloudflare R2     $2         /data/images local disk
Research VM      Hetzner CX22      $5         Same server as API
Vision API       Anthropic Sonnet  ~$15       Llama 3 + CLIP
Synthesis API    Anthropic Haiku   ~$5        Llama 3 local
──────────────────────────────────────────────────────────────
~$62/mo + BooksRun $0 + BookScouter $20–50
```

Week 2 Stacks deliverable: "Gibson running and usable at Driftless"
= cloud deployment fully operational and accessible from the store.
Local server hardware not yet purchased. Do not block on it.

### Local Server — Target Spec

```
GPU:         RTX 4090 24GB used, eBay — $1,400–$1,600
             Buy from gamer upgrading to RTX 5090, not a miner
             Stress-test 24hr VRAM burn before accepting
CPU:         AMD Ryzen 9 7950X or Intel i9-13900K — $350–$450 used
RAM:         64GB DDR5 — $120–$160
Storage:     1TB NVMe (OS + code + DB) + 4TB HDD (images) — $160–$250
Motherboard: PCIe 4.0 x16 compatible — $180–$250
PSU:         1000W 80+ Gold minimum — $100–$140
Case:        Full tower (4090 is three slots wide) — $80–$120
Network:     Gigabit ethernet to store router — not WiFi
─────────────────────────────────────────────────────────
TOTAL:       $2,400–$2,900
Timing:      August–September 2026 — RTX 5080 supply may
             soften used 4090 prices to $1,200–$1,400
```

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/gibson
DATABASE_POOL_SIZE=10

# Anthropic
ANTHROPIC_API_KEY=
ANTHROPIC_VISION_MODEL=claude-sonnet-4-6
ANTHROPIC_SYNTHESIS_MODEL=claude-haiku-4-5-20251001

# Local LLM (after migration)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3:8b

# Pricing
BOOKSRUN_API_KEY=
BOOKSCOUTER_API_KEY=
VIALIBRI_BASE_URL=https://www.vialibri.net
EBAY_APP_ID=
EBAY_CERT_ID=
EBAY_DEV_ID=

# Channels
BIBLIO_API_KEY=
WHATNOT_API_KEY=          # if obtained; otherwise batch export only

# Image Storage
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=gibson-images
LOCAL_IMAGE_PATH=/data/images

# Notifications
TWILIO_ACCOUNT_SID=       # SMS for fetch alerts and want list notifications
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=

# Store Config
STORE_DL_ID=
STORE_MG_ID=

# Feature Flags
USE_LOCAL_LLM=false
USE_LOCAL_CLIP=false
SHELFIE_ENABLED=false
AGENT_ENABLED=false
WHATNOT_LIVE_CAMERA=false  # Phase 10 only
```

### Migration to Local Server

Code does not change. Config changes.

```
1.  pg_dump gibson_prod > gibson_$(date +%Y%m%d).sql
2.  pg_restore to local PostgreSQL
3.  rclone sync r2:gibson-images /data/images/
4.  git clone + pip install + systemd service
5.  ollama pull llama3:8b → set USE_LOCAL_LLM=true
6.  pip install clip + download ViT-L/14 → build index (2–4 hrs)
7.  set USE_LOCAL_CLIP=true, SHELFIE_ENABLED=true
8.  install Airflow, import DAGs
9.  update DNS
10. run first QLoRA fine-tuning overnight
11. parallel run 2 weeks, decommission cloud when confident
```

---

## Source Cascade — Bibliographic Identification & Pricing

### The Principle

The three photographs are the input. Everything else is lookup. Claude Vision extracts
the bibliographic signal from the photographs. The cascade finds that signal in the
world's bibliographic infrastructure. The cascade stops when confidence clears the
threshold or all sources are exhausted.

Sources are configured as YAML — not hardcoded. Adding a new source is two lines of
config and one new scraper file. No pipeline code changes.

### The USBN — Pre-ISBN Identifier

A critical recent development: USBN (openusbn.org, v1.0, April 2026). An open,
decentralized identifier for pre-ISBN books computed from the book itself — hash of
title + author + year as printed on the title page, normalized, producing a
13-character string identical in length to ISBN-13.

The same book examined by two strangers on opposite sides of the world yields the same
USBN. No network, no registration, no prior cataloguing required.

Gibson computes a USBN for every pre-ISBN book it processes. This becomes the stable
lookup key for pre-1970 material across the cooperative database. When two members
process the same 1923 volume, their records merge under the same USBN automatically.

Implementation: pip install usbn (or implement the BLAKE2s hash directly from the
spec at openusbn.org — it is 40 lines of Python). Compute USBN immediately after
Claude Vision extracts title/author/year. Store alongside gibson_sku and seller_sku
in the stock_item table.

### The ABSA — The Most Important New Pricing Source

Biblio's Auction and Book Sales Archive (biblio.com/auction-and-book-sales-archive)
launched in 2024. It combines nearly 50 years of American Book Prices Current records
with Biblio's own historical sales data. Millions of curated rare book and manuscript
auction records with hammer prices, provenance, and bibliographical references.

This is the gold-standard authority on rare book auction values. ABPC has been
the definitive source for a century. Now it lives in a database Sullivan can
negotiate access to as part of the Alexandria cooperative relationship with Biblio.

ABAA members get free access (included in annual dues). Sullivan pursues ABAA
affiliate status — it may unlock ABSA access for the cooperative.

If API access is negotiated: query by author + title + year. Returns hammer prices,
condition descriptions, sale dates, auction house. This is realized price data from
the most authoritative source in the trade.

If no API: Playwright scrape, respectful rate limiting, query overnight only.

### Calamari — Fraktur OCR

Calamari (github.com/Calamari-OCR) with pretrained Fraktur weights achieves 0.18%
character error rate on 19th-century German Fraktur — near human-level accuracy,
outperforming Tesseract and commercial engines on this task.

Pretrained models available immediately:
- fraktur_historical (GT4HistOCR corpus, 15th–19th century)
- fraktur19 (DTA19 subset, 19th century German novels — best for 1800-1900)
- htr models for medieval German manuscripts (Gothic, Bastarda)

Fires as a fallback in the OCR pipeline when:
- Language signal is German AND
- Standard EasyOCR + PaddleOCR ensemble returns low confidence

Not a replacement for the main OCR ensemble — it is a fallback for the specific case
of pre-WWII German Fraktur typefaces. Claude Vision handles the rough extraction;
Calamari fires when higher precision is needed on the title page or copyright page.

Install: pip install calamari-ocr
Models: github.com/Calamari-OCR/calamari_models (download fraktur19 weights)

### Harvard LibraryCloud — Major Bibliographic Source Not In Prior Spec

Harvard Library's LibraryCloud API (library.harvard.edu/services-tools) provides
open access to 12.7 million bibliographic records from Harvard's catalog plus 4M
image records and 2M archival finding aids. Returns normalized MODS or Dublin Core.
Free, no registration required for the public API.

For American publications, scholarly works, and anything that passed through a major
research library — this is a high-quality free source that supplements LOC and WorldCat.
Particularly strong on pre-ISBN academic, theological, and scientific works.

Endpoint: librarycloudapi.harvard.edu/v2/items — search by title, author, ISBN,
LCCN, OCLC number.

### Rare Book Hub — The Trade's Own Database

Rare Book Hub (rarebookhub.com) contains approximately 15.9 million auction records
for rare books, prints, maps, photographs, autographs, and ephemera. The trade
standard for professional appraisers. Available by subscription.

For the overnight research agent on high-value items: Playwright scrape against the
free search interface, or negotiate a data partnership as the cooperative grows.
This is the most comprehensive auction record database in the trade, broader than
ABSA for some categories (especially prints, maps, ephemera).

### LiveAuctioneers — 21 Million Auction Records, Free

LiveAuctioneers (liveauctioneers.com) archives realized prices for 21+ million objects
from auction houses worldwide since 1999. Free to access with account registration.
Includes book auction results from hundreds of regional houses not covered by Heritage,
Swann, or PBA.

For the overnight pricing agent: Playwright with registered account. High value for
regional and specialist auction results that the major houses don't cover.

### source_cascade.yaml

```yaml
# agent/source_cascade.yaml
# Edit this file to add sources. No pipeline code changes needed.

# ─── PHASE 1: LOCAL DATABASE ──────────────────────────────────────────────
phase_1:
  - local_db                    # ISBN-13 exact, ISBN-10 normalized, title+author fuzzy

# ─── PHASE 2: FREE BULK SOURCES (already ingested locally) ────────────────
phase_2:
  - isfdb_local                 # 2.38M records, genre fiction
  - open_library_local          # 4M filtered editions
  - loc_authorities_local       # 10M+ name/title authorities
  - project_gutenberg_local     # 70K public domain records

# ─── PHASE 3: FREE API SOURCES (external, parallel) ──────────────────────
phase_3_default:
  - open_library_api            # broader than local subset
  - loc_sru                     # authoritative for American publications
  - hathitrust                  # strong academic press, multilingual
  - worldcat                    # 586M+ records, multilingual
  - harvard_librarycloud        # 12.7M records, strong pre-ISBN scholarly
  - google_books_metadata       # metadata only, fallback

# ─── PHASE 4: PRICING (parallel, fires when identification clears 70%) ────
phase_4_pricing_default:
  - vialibri                    # GATE. Aggregates 170+ sites. Always first.
  - ebay_sold                   # realized prices. Labeled: SOLD
  - ebay_active                 # asking prices. Labeled: ASKING
  - booksrun                    # post-1990 commodity only. Low weight.
  - bookscouter_historic        # trend data. Labeled: TREND

# ─── PHASE 5: OVERNIGHT DEEP RESEARCH (agent only) ───────────────────────
phase_5_default:
  - absa_biblio                 # 50 years ABPC auction records. Best for rare.
  - rare_book_hub               # 15.9M auction records. Trade standard.
  - liveauctioneers             # 21M records, regional houses. Free.
  - heritage_auctions           # Playwright. Realized prices.
  - swann_galleries             # Playwright. Fine books specialist.
  - pba_galleries               # Playwright. West Coast specialist.
  - bookfinder_addall           # asking price aggregation
  - internet_archive            # bibliographic metadata
  - duckduckgo_research         # title + author + publisher + year search
  - dealer_site_scraping        # specialist dealers by subject signal

# ─── SIGNAL OVERRIDES ─────────────────────────────────────────────────────
signals:

  language_german:
    ocr_fallback: calamari_fraktur19    # fires when EasyOCR+PaddleOCR < 70%
    identifier: usbn                     # compute USBN from title/author/year
    phase_3_prepend:
      - dnb                    # Deutsche Nationalbibliothek — authoritative post-1913
      - kvk                    # Karlsruher Virtueller Katalog — German/Austrian/Swiss
      - osterreich_nb          # Österreichische Nationalbibliothek
    phase_4_pricing_prepend:
      - zvab_direct            # German antiquarian market
      - ebay_de_sold           # German eBay realized prices
    phase_5_prepend:
      - jahrbuch_auktionspreise  # German auction results

  language_french:
    phase_3_prepend:
      - bnf                    # Bibliothèque nationale de France — data.bnf.fr

  language_latin:
    phase_3_prepend:
      - estc                   # English Short Title Catalogue (pre-1801)
      - istc                   # Incunabula Short Title Catalogue (pre-1501)

  pre_1501:
    identifier: usbn
    phase_3_replace:           # replace default, not prepend
      - istc
      - estc
      - kvk

  pre_1700:
    identifier: usbn
    phase_3_prepend:
      - estc
      - vd16                   # Verzeichnis der Drucke des 16. Jahrhunderts
      - vd17                   # Verzeichnis der Drucke des 17. Jahrhunderts

  pre_1800:
    identifier: usbn
    phase_3_prepend:
      - estc
      - evans_american         # Early American Imprints (1639-1800)

  pre_isbn:                    # any book where ISBN is absent
    identifier: usbn            # always compute USBN

  genre_sf_fantasy:
    phase_2_prepend:
      - isfdb_local            # already there but move to front
    phase_3_prepend:
      - isfdb_api              # live API, deeper than local dump
      - galactic_central       # when Sullivan relationship is active
      - fictiondb

  genre_mystery_crime:
    phase_3_prepend:
      - stop_youre_killing_me
      - thrilling_detective

  genre_poetry_literary:
    phase_3_prepend:
      - poetry_foundation
      - columbia_grangers

  genre_childrens:
    phase_3_prepend:
      - degrummond_finding_aids

  format_zine:
    ghost_book: true
    phase_3_replace:
      - zinecat
      - printed_matter
      - qzap
      - internet_archive
      - factsheet_five

  format_academic_scholarly:
    phase_3_prepend:
      - hathitrust
      - harvard_librarycloud

  format_government_document:
    phase_3_prepend:
      - gpo_catalog
      - eric

  subject_music:
    phase_3_append:
      - rilm_abstracts

  auction_value_signal:        # triggers when: age>1900 OR price signal>$50
    phase_5_prepend:
      - absa_biblio
      - rare_book_hub
      - liveauctioneers
      - heritage_auctions
      - swann_galleries

  illustrated_plates:          # colored plate books — high value, condition-sensitive
    phase_5_prepend:
      - rare_book_hub
      - liveauctioneers

  signed_inscribed:
    phase_5_prepend:
      - absa_biblio            # ABPC has extensive autograph/manuscript records
      - rare_book_hub

# ─── SOURCE DEFINITIONS ───────────────────────────────────────────────────
# Each source maps to a file in agent/sources/
# access: free | scrape | subscription | relationship
# rate_limit: requests per minute

sources:
  local_db:           {file: local_db.py,         access: free,         rate: unlimited}
  isfdb_local:        {file: isfdb_local.py,       access: free,         rate: unlimited}
  open_library_local: {file: ol_local.py,          access: free,         rate: unlimited}
  loc_authorities_local: {file: loc_auth_local.py, access: free,         rate: unlimited}
  open_library_api:   {file: open_library_api.py,  access: free,         rate: 100}
  loc_sru:            {file: loc_sru.py,           access: free,         rate: 30}
  hathitrust:         {file: hathitrust.py,        access: free,         rate: 60}
  worldcat:           {file: worldcat.py,          access: free_limited, rate: 20}
  harvard_librarycloud: {file: harvard_cloud.py,   access: free,         rate: 100}
  google_books_metadata: {file: google_books.py,   access: free_limited, rate: 20}
  dnb:                {file: dnb.py,               access: free,         rate: 60}
  kvk:                {file: kvk.py,               access: free_scrape,  rate: 10}
  osterreich_nb:      {file: onb.py,               access: free_scrape,  rate: 10}
  bnf:                {file: bnf.py,               access: free,         rate: 30}
  estc:               {file: estc.py,              access: free_scrape,  rate: 10}
  istc:               {file: istc.py,              access: free_scrape,  rate: 10}
  vd16:               {file: vd16.py,              access: free_scrape,  rate: 10}
  vd17:               {file: vd17.py,              access: free_scrape,  rate: 10}
  evans_american:     {file: evans.py,             access: free_scrape,  rate: 10}
  isfdb_api:          {file: isfdb_api.py,         access: free,         rate: 30}
  galactic_central:   {file: galactic_central.py,  access: relationship, rate: 5}
  fictiondb:          {file: fictiondb.py,         access: free_scrape,  rate: 10}
  stop_youre_killing_me: {file: sykm.py,           access: free_scrape,  rate: 10}
  thrilling_detective: {file: thrilling_det.py,    access: free_scrape,  rate: 10}
  poetry_foundation:  {file: poetry_foundation.py, access: free_scrape,  rate: 10}
  columbia_grangers:  {file: grangers.py,          access: free_scrape,  rate: 10}
  degrummond_finding_aids: {file: degrummond.py,   access: free_scrape,  rate: 5}
  zinecat:            {file: zinecat.py,           access: free_scrape,  rate: 10}
  printed_matter:     {file: printed_matter.py,    access: free_scrape,  rate: 10}
  qzap:               {file: qzap.py,              access: free_scrape,  rate: 10}
  factsheet_five:     {file: factsheet_five.py,    access: free_scrape,  rate: 5}
  vialibri:           {file: vialibri.py,          access: free_scrape,  rate: 30}
  ebay_sold:          {file: ebay_sold.py,         access: api,          rate: 60}
  ebay_active:        {file: ebay_active.py,       access: api,          rate: 60}
  zvab_direct:        {file: zvab.py,              access: free_scrape,  rate: 10}
  ebay_de_sold:       {file: ebay_de.py,           access: scrape,       rate: 10}
  booksrun:           {file: booksrun.py,          access: affiliate,    rate: 60}
  bookscouter_historic: {file: bookscouter.py,     access: paid,         rate: 30}
  absa_biblio:        {file: absa.py,              access: subscription, rate: 10}
  rare_book_hub:      {file: rare_book_hub.py,     access: subscription, rate: 5}
  liveauctioneers:    {file: liveauctioneers.py,   access: free_account, rate: 10}
  heritage_auctions:  {file: heritage.py,          access: playwright,   rate: 5}
  swann_galleries:    {file: swann.py,             access: playwright,   rate: 5}
  pba_galleries:      {file: pba.py,               access: playwright,   rate: 5}
  bookfinder_addall:  {file: bookfinder.py,        access: free_scrape,  rate: 15}
  internet_archive:   {file: internet_archive.py,  access: free,         rate: 30}
  duckduckgo_research: {file: ddg_research.py,     access: free,         rate: 20}
  dealer_site_scraping: {file: dealer_sites.py,    access: scrape,       rate: 5}
  gpo_catalog:        {file: gpo.py,               access: free,         rate: 20}
  rilm_abstracts:     {file: rilm.py,              access: free_scrape,  rate: 10}
  calamari_fraktur19: {file: calamari_ocr.py,      access: local,        rate: unlimited}
  jahrbuch_auktionspreise: {file: jahrbuch.py,     access: scrape,       rate: 5}
```

### OCR Pipeline with Calamari Fallback

```python
# services/ocr.py

def run_ocr_pipeline(image, language_signal=None):
    """
    Primary: EasyOCR + PaddleOCR ensemble
    Fallback: Calamari fraktur19 for German Fraktur when confidence < 0.70
    Claude Vision handles final extraction regardless — OCR feeds it context
    """
    # Primary ensemble
    easy_result = run_easyocr(image)
    paddle_result = run_paddleocr(image)
    ensemble = merge_ensemble(easy_result, paddle_result)

    # Calamari fallback for German Fraktur
    if (language_signal == 'german' or
        detect_fraktur_typeface(image)) and ensemble.confidence < 0.70:
        calamari_result = run_calamari(image, model='fraktur19')
        ensemble = merge_with_calamari(ensemble, calamari_result)

    return ensemble

def run_calamari(image, model='fraktur19'):
    """
    Calamari with 5-model voting ensemble.
    Models: github.com/Calamari-OCR/calamari_models
    Install: pip install calamari-ocr
    Download: calamari-predict --download fraktur19
    """
    # Preprocess: convert to grayscale, resize to 48px height
    preprocessed = preprocess_for_calamari(image)
    result = calamari_predict(preprocessed, model=model)
    return result
```

### The German Box — Resolved Pipeline

```
Box of 1900 German books photographed in batch session:

1. Cover photo → detect Fraktur typeface (visual classifier)
   → set language_signal = 'german'
   → load source_cascade.yaml with german signal overrides

2. OCR: EasyOCR + PaddleOCR ensemble runs first
   If confidence < 0.70: Calamari fraktur19 fires as fallback
   Result: title, author, publisher city, year extracted

3. USBN computed from title + author + year as printed
   → stable identifier even without ISBN

4. Phase 1: local DB lookup by USBN → probably misses

5. Phase 3 (german override — parallel):
   DNB API → KVK → Österreichische NB → Harvard LibraryCloud
   → WorldCat → HathiTrust
   Expected match rate: 85-90% at Work level, 70% at Edition level

6. Phase 4 pricing (fires when identification > 70%):
   Vialibri (hits ZVAB) → eBay sold → ZVAB direct → eBay.de sold
   For anything that looks auction-worthy: 
   → heritage, swann, pba (Playwright, overnight only)

7. Phase 5 (overnight, unresolved books):
   ABSA Biblio → Rare Book Hub → LiveAuctioneers
   → DuckDuckGo on extracted German terms
   → dealer site scraping for specialist German dealers

8. Morning review:
   Identified with comps: price suggested, ready to list
   Identified without comps: IN_STORE_ONLY suggestion, dealer decides
   Unidentified: Ghost Book queue — human expert review

Expected resolution: 95%+ of post-1800 German books identified
to Work level. 80%+ to Edition level.
Remaining 5%: genuinely obscure regional imprints — Ghost Book queue.
```

### Priority Build Order for Sources

Nova builds sources in this order — high value, free sources first:

```
IMMEDIATE (Month 1-2, free, high value):
  local_db, isfdb_local, open_library_local, loc_authorities_local
  open_library_api, loc_sru, hathitrust, harvard_librarycloud
  vialibri, ebay_sold, ebay_active, booksrun
  usbn (compute identifier — 40 lines of Python)

MONTH 3 (free, adds language coverage):
  dnb, kvk, bnf
  calamari_fraktur19 (add as OCR fallback)
  liveauctioneers (free account, 21M records)
  internet_archive, duckduckgo_research

MONTH 4-6 (agent infrastructure, some relationship-dependent):
  zinecat, printed_matter, qzap (Ghost Book sources)
  isfdb_api, galactic_central (when Sullivan relationship active)
  heritage_auctions, swann_galleries (Playwright, overnight)
  bookfinder_addall

RELATIONSHIP-DEPENDENT (Sullivan unlocks):
  absa_biblio — negotiate with Biblio as cooperative partner
  rare_book_hub — subscription or data partnership
  galactic_central — Eddy introduces, Sullivan builds

SPECIALTY (add when needed):
  estc, istc, vd16, vd17 (early printed books)
  evans_american (early American)
  stop_youre_killing_me, thrilling_detective (mystery)
  fictiondb, poetry_foundation (genre)
  gpo_catalog (government docs)
```


---

## Data Ingestion

### Legacy Inventory Import (Priority — before bibliographic sources)

```
SOURCE          RECORDS    FORMAT          TRUST TIER
────────────────────────────────────────────────────────
Amazon export   ~active    Tab-delimited   Tier 2
Kazam file      37,967     Tab-delimited   Tier 3
eBay (700)      700        Manual/API      Tier 2
```

Kazam: `location` field = section code. Import, preserve raw as JSONB,
match by ISBN, flag conflicts, route unmatched to NEEDS_IDENTIFICATION.
Amazon: `item-note` field has section appended after dash ("Bio/G").
Lower tiers never overwrite higher. Conflicts flagged, never auto-resolved.

### Bibliographic Sources

```
SOURCE               RECORDS    FORMAT       MONTH
──────────────────────────────────────────────────
ISFDB dump           2.38M      MySQL dump   1
LOC Authority Files  10M+       MARC21       1
Open Library         4M filt.   JSON         2
LOC MARC catalog     varies     MARC21       3–4
ZineCat              ~31K       CollectiveAccess API or scrape  4
Project Gutenberg    70K        RDF/XML      4
Wikidata (books)     varies     JSON         5
HathiTrust           varies     JSON         5–6
```

BibDedupe before any custom deduplication code. Non-negotiable.

---

## Build Sequence

```
PHASE 0 — Environment (Week 1)
  ✓ Supabase + Railway + GitHub
  ✓ GET /health → {status: ok, store: DL}
  ✓ .env.example complete
  ✓ docker-compose.yml local dev
  ✗ No vision, pricing, book data

PHASE 1 — Schema (Week 1–2)
  ✓ All migrations run cleanly
  ✓ Seed: two stores, employees with initials, one test book
  ✓ Section seed from master list photo (pending from Eddy)
  ✗ No real bibliographic data

PHASE 2 — Fast Path + Pricing (Week 2–3)
  ✓ ZXing-js barcode in PWA
  ✓ ISBN normalize + validate
  ✓ Local DB lookup
  ✓ Vialibri + eBay sold + BooksRun parallel
  ✓ Price display: SOLD / ASKING / TREND
  ✓ Vialibri gate logic
  ✓ Stock Item creation on confirm
  ✓ Biblio channel integration
  ✓ Website channel (Gibson as backend)
  ← First thing Eddy uses in the store

PHASE 3 — Standard Path (Week 3–4)
  ✓ PWA camera interface
  ✓ EasyOCR + PaddleOCR
  ✓ Claude Vision hybrid integration
  ✓ Per-field confidence scoring
  ✓ Gibson asks for follow-up
  ✓ Triage router complete

PHASE 4 — Correction Interface (Week 4)
  ✓ Field-level correction UI
  ✓ Concern level auto-assignment
  ✓ Review queue for Eddy
  ✓ Training example logging
  ← Do not skip or defer

PHASE 5 — POS + Whatnot Batch (Week 4–5)
  ✓ Counter view: SKU lookup + section code entry
  ✓ Multi-book sale flow
  ✓ Sale record + realized price
  ✓ Channel sync on sale (15 min)
  ✓ Whatnot batch export: identify pile, generate descriptions,
    suggest sequence, export for upload

PHASE 6 — Slow Path + Research Agent + Buy Queue (Week 5–6)
  ✓ Placeholder Stock Item
  ✓ Slow path queue
  ✓ Haiku synthesis
  ✓ Human review queue
  ✓ Ghost Book record creation
  ✓ Buy queue: intake flow, customer record, offer, mark paid

PHASE 7 — Customer App + Visit Scheduling (Week 6–7)
  ✓ Browse, search, section view
  ✓ Want list (SMS notification on confirmed match)
  ✓ Visit scheduling ("I'm coming Saturday")
  ✓ Employee dashboard: upcoming visits + prep notes
  ✓ Dealer want list intelligence alerts
  ✓ SMS fetch alert via Twilio (not PWA push)

PHASE 8 — Data Ingestion (Week 6–8, parallel)
  ✓ Kazam import (37,967 records)
  ✓ Amazon import
  ✓ ISFDB dump
  ✓ LOC Authority Files
  ✓ Open Library filtered
  ✓ BibDedupe evaluated and decision documented

PHASE 9 — Shelf Scan (Week 8–10)
  ✓ YOLOv8n spine detection
  ✓ Spine OCR + inventory comparison
  ✓ Color overlay: GREEN/YELLOW/RED/GREY
  ✓ Promotion queue for underpriced books
  ✓ Location correction queue

PHASE 10 — Full Agent + Whatnot Live Camera (Month 4)
  ✓ Hetzner VM
  ✓ smolagents + ScrapeGraphAI + Playwright
  ✓ Standard + Ghost Book source routing
  ✓ ZineCat inbound scrape
  ✓ Whatnot live camera mode (Standard Path on video feed)
```

---

## Writing Standards

- Write for a developer who has never met you and is reading this in 2028.
- Every function has a docstring explaining what and why.
- Every environment variable documented in .env.example before use in code.
- Every failure mode has a specific error message. Never a generic 500.
- Confidence scores in every API response involving identification or pricing.
- Original value preserved before every correction. Not optional.
- Every disagreement between Gibson's suggestion and dealer's decision is logged.
- Every Stock Item query includes store_id filter. No exceptions.
- Cost basis never appears in any response outside the owning store's session.

---

*Alexandria Book Co-op — Driftless Books & Music, 518 Walnut Street, Viroqua, Wisconsin*
*Metaphysical Graffiti — Viroqua, Wisconsin*
*Gibson is built to outlast its founders. Write it accordingly.*

---

## Store Mapping & Physical Intelligence System

### What This Is

A continuous spatial intelligence layer over the physical store. Gibson builds a complete model of every room in both stores — every shelf unit, every shelf, every box, every table, every pile, every corner — and overlays known inventory on that model. It reads uncatalogued surfaces overnight and generates morning pull recommendations.

This is not a one-time cataloguing project. It is an ongoing model that knows where everything is, understands what it does not know, and works overnight to surface what is worth attention.

### The Container Model

Everything in the store is a container. Shelves, boxes, tables, carts, piles — all treated identically at the data model level. Every container has a location, a photograph, a rough inventory, and a status.

```
Container types:
  shelf_unit     Standard book shelving. Photographed shelf by shelf.
  box            Open or sealed. Rough manifest from top layer.
  table          Flat surface. Wide shot + close shots of visible spines.
  cart           Book cart. Photo showing contents and location.
  pile           Stacked books. Photo from above.
  other          Anything else. Photo + description.
```

When the photographer encounters any container, Gibson asks:
1. What type is this?
2. What section is it, or what do you think is in it?

The photographer writes the confirmed name on a sticky note and tapes it to the container. Gibson reads the sticky note in the shelf photo and registers it as the confirmed identifier. This is the most important interface decision in this feature — it means the photographer never has to type while standing on a ladder.

### New Schema Tables

```sql
CREATE TABLE room (
    room_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id        UUID REFERENCES store(store_id),
    name            TEXT NOT NULL,   -- 'First Floor Fiction Room'
    floor           TEXT,
    video_url       TEXT,            -- room walkthrough video
    floor_plan_json JSONB,           -- spatial model (post-migration only)
    mapped_at       TIMESTAMPTZ,
    last_updated    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE container (
    container_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    room_id          UUID REFERENCES room(room_id),
    container_type   TEXT NOT NULL CHECK (container_type IN (
                         'shelf_unit','box','table','cart','pile','other')),
    name             TEXT NOT NULL,
    name_source      TEXT CHECK (name_source IN (
                         'sticky_note','user_input','gibson_proposed')),
    sticky_note_text TEXT,
    position_in_room JSONB,          -- {x, y, orientation} relative to room
    photo_url        TEXT,
    video_url        TEXT,
    shelf_count      INT,
    status           TEXT DEFAULT 'MAPPED' CHECK (status IN (
                         'MAPPED','PARTIALLY_INVENTORIED',
                         'FULLY_INVENTORIED','NEEDS_RESHOOT','SEALED')),
    notes            TEXT,
    created_at       TIMESTAMPTZ DEFAULT now(),
    updated_at       TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE shelf (
    shelf_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    container_id        UUID REFERENCES container(container_id),
    shelf_number        INT NOT NULL,    -- 1 = top, counts down
    photo_url           TEXT,
    book_count_est      INT,
    spine_manifest      JSONB,           -- [{text, confidence, position}]
    last_photographed   TIMESTAMPTZ,
    last_scanned        TIMESTAMPTZ,
    status              TEXT DEFAULT 'UNCATALOGUED' CHECK (status IN (
                            'UNCATALOGUED','PARTIALLY_CATALOGUED',
                            'FULLY_CATALOGUED','NEEDS_RESHOOT'))
);

CREATE TABLE container_item (
    item_id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shelf_id                  UUID REFERENCES shelf(shelf_id),
    container_id              UUID REFERENCES container(container_id),
    stock_item_id             UUID REFERENCES stock_item(stock_item_id),
    spine_text_raw            TEXT,
    identified_work_id        UUID REFERENCES work(work_id),
    identification_confidence NUMERIC(3,2),
    position_on_shelf         INT,      -- left to right, 1-indexed
    photo_region              JSONB,    -- bounding box in shelf photo
    pull_recommended          BOOLEAN DEFAULT false,
    pull_reason               TEXT,
    pull_priority             INT,      -- 1 = highest
    resolved_at               TIMESTAMPTZ,
    created_at                TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX idx_container_room ON container(room_id);
CREATE INDEX idx_shelf_container ON shelf(container_id);
CREATE INDEX idx_container_item_shelf ON container_item(shelf_id);
CREATE INDEX idx_container_item_pull ON container_item(pull_recommended, pull_priority);
CREATE INDEX idx_container_item_stock ON container_item(stock_item_id);
```

### Photography Workflow

**Phase 1 — Room video (3–8 minutes per room)**
Walk the room slowly from the entrance, phone at chest height. State the room name aloud. Point at each unit and name its section if known. Point at boxes and containers, describe contents. End back at the entrance. Gibson processes overnight — builds spatial model, identifies containers, reads sticky notes.

**Phase 2 — Shelf unit photos**
For each unit: confirm name via sticky note (write it, tape it, Gibson reads it). Photograph the full unit from 6–8 feet. Photograph each shelf individually, held level, 2–3 feet back, full width visible.

**Phase 3 — Container photos**
Open boxes: video around box, photo of open top showing spines, photo of any label.
Sealed boxes: photo of exterior and any labels. Status: SEALED. Added to pull queue as "open and photograph."
Tables and flat surfaces: wide shot from above, close shots of any legible spine text.

### Overnight Pipeline

Runs at 2 AM, same Hetzner VM as research agent.

```
2:00–3:00  Spine reading
           YOLOv8n detects book regions in shelf photos
           EasyOCR + PaddleOCR ensemble extracts spine text
           Calamari fires as fallback when ensemble confidence < 0.70
           Results stored in container_item.spine_manifest

3:00–4:00  Identification attempt
           Author + title fuzzy match against local bibliographic database
           Full match → link to work_id
           Partial match → flag PARTIAL_ID
           No match → flag UNIDENTIFIED
           Pre-ISBN + no match → flag GHOST_BOOK_CANDIDATE

4:00–4:30  Pricing cross-reference
           Query Vialibri cache, pricing_record, eBay sold cache
           Build price estimate: low / median / high
           Store in container_item alongside identification

4:30–5:00  Want list matching
           Cross-reference identified spines against active want_list
           Flag matches: pull_recommended = true
           Never expose customer name in pull list — 'customer want list match'

5:00–5:30  Pull recommendation engine
           Generate prioritized pull list for morning report
```

### Pull Recommendation Rules

```python
# services/pull_recommendations.py

PULL_CRITERIA = [
    # Priority 1 — act today
    ("vialibri_comps_above_15", "3+ Vialibri comps above $15"),
    ("want_list_match", "Active customer want list match"),
    ("search_zero_result_match", "Recent customer search — zero results"),
    ("first_edition_signals", "Edition signals visible on spine"),
    ("signed_copy_visible", "Handwriting visible — possible inscription"),

    # Priority 2 — worth the pull
    ("partial_id_needs_title_page", "Gibson can almost identify — one photo resolves"),
    ("ghost_book_candidate", "Pre-ISBN, no institutional record — Ghost Book queue"),

    # Priority 3 — batch when working the section
    ("vialibri_comps_8_to_15", "Vialibri comps $8–15, commodity signal"),
    ("high_demand_author", "Author matches high-demand section pattern"),
]

# Gibson never recommends pulling everything on a shelf.
# That is cataloguing, not intelligence.
# The pull engine surfaces books where there is a specific reason to act today.
```

### Morning Report

Two forms, same data:

**Dashboard:** Summary count, drill into each recommendation. Shelf photo with book position highlighted. One-tap: Pull / Skip / Already have it / Can't find it.

**Printable pull list:** Clean sheet for carrying on the floor. Columns: Priority, Location (room + unit + shelf + position), Title/Author as read, Why Gibson recommends it, Price estimate, Action. Apprentices carry the printed sheet. Each pull becomes a normal Gibson cataloguing session.

### Sold Book View

When a book sells, Gibson retrieves:
- The shelf photo where the book was located
- The book's recorded position (container_item.position_on_shelf)
- The bounding box (container_item.photo_region)

Draws a red highlight at that position in the shelf photo. Kim sees this on the fetch alert. Employee goes directly to the right shelf, right position. No hunting.

Gap intelligence: when a shelf has sold more than 20% of its books since last photo, Gibson adds it to the re-photograph queue. The spatial model stays current automatically.

### Build Sequence

Build after Phase 9 (Shelfie working on 3+ sections). The Shelfie spine reading pipeline is the foundation.

```
Map-1: Room video ingest. Container/shelf/room schema deployed.
Map-2: Sticky note OCR + name registration. Shelf photo → spine manifest.
       Reuses Shelfie pipeline. Position numbers assigned to every book.
Map-3: Overnight identification + pricing + want list matching.
Map-4: Pull recommendation engine. Morning dashboard. Printable pull list.
Map-5: Sold book view. Shelf photo with highlight. Gap intelligence.
Map-6: Floor plan generation from room video (post-migration, local GPU).
       Customer-facing store map.
```

### What Must Not Happen

- Do not try to identify every book on every shelf. The overnight pass is an intelligence pass, not a cataloguing run.
- Do not skip position tracking. Every book on every shelf needs a left-to-right position number at photograph time. The sold book view depends entirely on this.
- Do not generate floor plans in the cloud phase. That requires photogrammetry on a local GPU. Build the data model without it. The floor plan is added post-migration.
- Do not expose customer names in pull recommendations. Say "customer want list match" only.

---

## Conversational Intelligence System

### What This Is

Gibson's conversational interface. Not a chatbot. Not a query form. The interface through which everything else becomes accessible to a non-technical operator. A microphone button on every screen and a full conversation window for deep sessions. Currently restricted to Eddy only.

Two modes, one interface:

**Ambient mode** — tap the microphone, ask a question, get a short answer, keep working. Optimized for speed. Two to four sentences maximum unless more is asked for. Available from every screen in the PWA.

**Deep mode** — a full conversational session with no length limit. Architecture decisions, data strategy, planning tomorrow's work, reviewing overnight findings. Gibson brings everything it knows. Conversations are logged, indexed, and searchable permanently.

### The Preparation Cycle

The most important feature in this system. When you tell Gibson what you're working on tomorrow — "I'm cataloguing my Edgar Rice Burroughs collection tomorrow" — Gibson does not generate a report. It prepares.

The preparation cycle runs overnight and does three things:

1. **Bibliographic enrichment:** Pulls complete bibliography for the subject from every available source. Fills gaps in Gibson's local database. Confirms edition identification points. By morning, Gibson's identification pipeline has materially better data on this subject than it had yesterday.

2. **Pricing intelligence:** Runs a full pricing sweep for the subject — Vialibri, eBay sold, Heritage, Swann. Gibson knows what every book in that collection is worth before you pick up the first one.

3. **Inventory cross-reference:** Checks what you already have catalogued, what the overnight spine reader has seen in uncatalogued sections, what's on active customer want lists. Generates a pull list for copies Gibson has seen but you haven't yet catalogued.

The result: you walk in tomorrow working with a better tool than you had yesterday because you told it what you needed.

### New Schema Tables

```sql
CREATE TABLE conversation (
    conversation_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID NOT NULL,
    mode              TEXT CHECK (mode IN ('ambient','deep')),
    started_at        TIMESTAMPTZ DEFAULT now(),
    ended_at          TIMESTAMPTZ,
    title             TEXT,               -- Gibson generates
    summary           TEXT,               -- 3-sentence summary
    topics            TEXT[] DEFAULT '{}',
    decisions         JSONB DEFAULT '[]',
    preparation_tasks JSONB DEFAULT '[]',
    full_transcript   JSONB NOT NULL
);

CREATE TABLE conversation_decision (
    decision_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversation(conversation_id),
    decision_text   TEXT NOT NULL,
    topic           TEXT,
    status          TEXT DEFAULT 'ACTIVE'
                    CHECK (status IN ('ACTIVE','SUPERSEDED','IMPLEMENTED')),
    superseded_by   UUID REFERENCES conversation_decision(decision_id),
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE preparation_task (
    task_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversation(conversation_id),
    subject         TEXT NOT NULL,
    subject_type    TEXT,   -- 'author','publisher','genre','section','topic','architecture'
    scope           JSONB,
    status          TEXT DEFAULT 'QUEUED'
                    CHECK (status IN ('QUEUED','RUNNING','COMPLETE','FAILED')),
    queued_at       TIMESTAMPTZ DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    result_summary  TEXT,
    briefing_url    TEXT
);

CREATE INDEX idx_conversation_topics ON conversation USING gin(topics);
CREATE INDEX idx_conversation_user ON conversation(user_id, started_at DESC);
CREATE INDEX idx_decision_topic ON conversation_decision(topic, status);
CREATE INDEX idx_prep_task_status ON preparation_task(status, queued_at);
```

### System Prompt Assembly

Rebuilt fresh for every conversation. Assembles from the database:

```
- Store identity: names, addresses, staff, current date
- Inventory summary: stock counts, recent sales, dead stock signals
- Store map state: mapped containers, pull recommendations, overnight findings
- Pricing intelligence: recent trends, top-value inventory, market signals
- Customer context: active want lists (aggregate), upcoming visits
- Overnight agent results: new identifications, Ghost Book candidates
- Institutional memory: summaries of 10 most recent deep conversations,
  all active decisions (status = ACTIVE)
- Build state: current phase, known gaps, what is being built
```

Assembled system prompt: approximately 4,000–8,000 tokens. Fits Sonnet context window. After local migration: Llama 3 handles ambient mode, Sonnet handles deep mode.

### Voice Input

Browser Speech Recognition API. Client-side transcription — no server-side speech processing. Works on iOS Safari, Android Chrome, desktop Chrome. Requires network.

```javascript
// pwa/src/lib/voice.js
const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
recognition.continuous = false;
recognition.interimResults = true;  // show words as they're spoken
recognition.lang = 'en-US';
// Tap → start. Silence or second tap → send transcript to Gibson API.
```

### Conversation API

```
POST /api/conversation/message
{
  conversation_id: uuid,      // null for new conversation
  mode: 'ambient' | 'deep',
  message: string,
  context_photo: base64,      // optional — if holding a book
}

Response:
{
  conversation_id: uuid,
  response: string,
  preparation_tasks_queued: [...],
  decisions_logged: [...],
  follow_up_suggested: string
}
```

### Preparation Trigger Detection

Intent-based, not keyword-based. Claude identifies when you are telling Gibson what to work on overnight.

```
Triggers detected:
  'I'm working on X tomorrow'
  'Can you learn everything about X tonight'
  'Focus on X for the overnight run'
  'I want to be ready to catalogue X'
  'What data sources should we add for X'    ← architecture prep
  'Let's think through the X feature'        ← architecture deep mode
```

When detected: preparation_task record created, queued for overnight agent, scope extracted from conversation context.

### Ambient Mode Rules

- Maximum two to four sentences unless more is explicitly requested
- Never volunteer unsolicited information
- Answer the question and wait
- Response time target: under 5 seconds for inventory queries, under 10 seconds for pricing (requires live API call)
- If holding a book: camera activates automatically for identification queries

### Institutional Memory Rules

- Every deep mode conversation is logged completely
- Gibson extracts decisions automatically and logs them to conversation_decision
- When a new decision supersedes an old one, the old one is marked SUPERSEDED with a reference
- Memory is searchable: "what did we decide about X" queries conversation_decision by topic
- Nova can read the decision log to understand architectural choices made before a problem was assigned to him

### Build Sequence

Build after Phase 4 (correction interface). Gibson needs to know the inventory well enough to answer accurately.

```
Conv-1  Basic API. Claude Sonnet. Static system prompt. Text only.
Conv-2  Dynamic system prompt. Inventory/pricing/sales context injected.
Conv-3  Voice input. Ambient microphone on every screen.
Conv-4  Preparation trigger detection. Task queue. Morning briefing.
Conv-5  Institutional memory. Decision logging. Memory search.
Conv-6  Store map context injected. Physical location questions work.
Conv-7  Post-migration: Llama 3 for ambient, Sonnet for deep only.
```

### What Must Not Happen

- Do not expose individual customer names in conversation responses — aggregate only
- Do not log ambient mode conversations in full — log query type and response category only (privacy)
- Deep mode conversations are logged completely
- Do not let Gibson answer architecture questions from training knowledge alone — it must query the institutional memory and CLAUDE.md first
- Response length in ambient mode is a hard constraint — two to four sentences. Not a suggestion.

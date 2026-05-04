-- ═══════════════════════════════════════════════════════════════
-- Gibson Migration 001: Core Bibliographic Schema
-- Work → Edition → Stock Item (FRBR-aligned)
-- Agent + Publisher as entity tables with authority records
-- ═══════════════════════════════════════════════════════════════

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ─── Agent (person, corporate, collective) ──────────────────

CREATE TABLE IF NOT EXISTS gibson_agent (
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

-- ─── Publisher ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS gibson_publisher (
    publisher_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name_display        TEXT NOT NULL,
    name_sort           TEXT NOT NULL,
    name_variants       TEXT[] DEFAULT '{}',
    parent_publisher_id UUID REFERENCES gibson_publisher(publisher_id),
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

-- ─── Work (abstract intellectual creation) ──────────────────

CREATE TABLE IF NOT EXISTS gibson_work (
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

-- ─── Work ↔ Agent junction ──────────────────────────────────

CREATE TABLE IF NOT EXISTS gibson_work_agent (
    work_id                UUID REFERENCES gibson_work(work_id),
    agent_id               UUID REFERENCES gibson_agent(agent_id),
    role                   TEXT NOT NULL CHECK (role IN (
                               'author','editor','compiler',
                               'illustrator','photographer','contributor')),
    role_order             INT DEFAULT 1,
    attribution_confidence NUMERIC(3,2) DEFAULT 1.0,
    attribution_source     TEXT,
    PRIMARY KEY (work_id, agent_id, role)
);

-- ─── Edition (specific published form) ──────────────────────

CREATE TABLE IF NOT EXISTS gibson_edition (
    edition_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    work_id                  UUID NOT NULL REFERENCES gibson_work(work_id),
    isbn_13                  TEXT UNIQUE,
    isbn_10                  TEXT,
    usbn                     TEXT,          -- pre-ISBN identifier (openusbn.org)
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

-- ─── Edition ↔ Agent junction ───────────────────────────────

CREATE TABLE IF NOT EXISTS gibson_edition_agent (
    edition_id  UUID REFERENCES gibson_edition(edition_id),
    agent_id    UUID REFERENCES gibson_agent(agent_id),
    role        TEXT NOT NULL CHECK (role IN (
                    'translator','illustrator','introducer',
                    'editor','designer','photographer')),
    role_order  INT DEFAULT 1,
    PRIMARY KEY (edition_id, agent_id, role)
);

-- ─── Edition ↔ Publisher junction ───────────────────────────

CREATE TABLE IF NOT EXISTS gibson_edition_publisher (
    edition_id   UUID REFERENCES gibson_edition(edition_id),
    publisher_id UUID REFERENCES gibson_publisher(publisher_id),
    role         TEXT NOT NULL CHECK (role IN (
                     'publisher','distributor','printer','imprint')),
    role_order   INT DEFAULT 1,
    PRIMARY KEY (edition_id, publisher_id, role)
);

-- ─── Source Record (raw ingested data) ──────────────────────

CREATE TABLE IF NOT EXISTS gibson_source_record (
    source_record_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source             TEXT NOT NULL,        -- source name: 'isfdb', 'open_library', 'kazam', etc.
    source_id          TEXT UNIQUE,          -- source's own identifier
    raw_data           JSONB NOT NULL,
    normalized_data    JSONB,
    normalized_title   TEXT,
    normalized_author  TEXT,
    isbn_13            TEXT,
    trust_tier         INT DEFAULT 4,        -- 1=manual, 2=amazon, 3=kazam, 4=bibliographic
    matched_work_id    UUID REFERENCES gibson_work(work_id),
    matched_edition_id UUID REFERENCES gibson_edition(edition_id),
    match_confidence   NUMERIC(3,2),
    ingested_at        TIMESTAMPTZ DEFAULT now()
);

-- ─── Stock Item (physical copy in a store) ──────────────────

CREATE TABLE IF NOT EXISTS gibson_stock_item (
    stock_item_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    edition_id          UUID NOT NULL REFERENCES gibson_edition(edition_id),
    gibson_sku          TEXT UNIQUE,
    seller_sku          TEXT,
    store_id            UUID NOT NULL,       -- NEVER query without this filter
    location_id         UUID,
    condition_grade     TEXT CHECK (condition_grade IN (
                            'Fine','Very Good+','Very Good','Good+',
                            'Good','Fair','Poor')),
    condition_dj        TEXT,
    condition_notes     TEXT,
    condition_qa_log    JSONB,
    condition_mode      TEXT DEFAULT 'tap' CHECK (condition_mode IN ('tap','qa')),
    status              TEXT NOT NULL DEFAULT 'AVAILABLE' CHECK (status IN (
                            'AVAILABLE','LISTED','SOLD','HOLD',
                            'IN_STORE_ONLY','PRICING_RESEARCH',
                            'PENDING_IDENTIFICATION','PENDING_REVIEW',
                            'GHOST_BOOK_QUEUE','WITHDRAWN')),
    listing_channels    TEXT[] DEFAULT '{}',
    asking_price        NUMERIC(10,2),
    cost_basis          NUMERIC(10,2),       -- NEVER exposed outside owning store
    images              TEXT[] DEFAULT '{}',
    is_signed           BOOLEAN DEFAULT false,
    is_inscribed        BOOLEAN DEFAULT false,
    inscription_note    TEXT,
    is_association_copy BOOLEAN DEFAULT false,
    provenance_notes    TEXT,
    whatnot_showed      BOOLEAN DEFAULT false,
    whatnot_showed_at   TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now(),
    created_by          UUID
);

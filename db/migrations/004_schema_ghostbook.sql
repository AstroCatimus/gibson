-- ═══════════════════════════════════════════════════════════════
-- Gibson Migration 004: Ghost Book Pipeline
-- Pre-ISBN, no-institutional-record material
-- First-class pipeline path, not an edge case
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS gibson_ghost_book_record (
    ghost_book_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stock_item_id        UUID REFERENCES gibson_stock_item(stock_item_id),
    collection_name      TEXT,
    physical_description TEXT,
    ocr_text_raw         TEXT,
    cover_photo_url      TEXT,
    date_range           TEXT,
    estimated_year       INT,
    estimated_language   TEXT,
    attribution_notes    TEXT,
    source_record        JSONB,
    research_status      TEXT DEFAULT 'QUEUED' CHECK (research_status IN (
                             'QUEUED','RESEARCHING','RESOLVED','UNRESOLVED',
                             'HUMAN_REVIEW','CONFIRMED','CONTRIBUTED_BACK','ERROR')),
    usbn                 TEXT,
    agent_candidate      JSONB,
    confidence_map       JSONB,
    sources_searched     TEXT[] DEFAULT '{}',
    contributed_to_zuc   BOOLEAN DEFAULT false,
    contributed_at       TIMESTAMPTZ,
    created_at           TIMESTAMPTZ DEFAULT now(),
    updated_at           TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS gibson_ghost_book_source_hit (
    hit_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ghost_book_id   UUID REFERENCES gibson_ghost_book_record(ghost_book_id),
    source_name     TEXT NOT NULL,
    hit_type        TEXT,               -- 'MATCH', 'NO_MATCH'
    source_url      TEXT,
    raw_response    JSONB,
    match_confidence NUMERIC(3,2),
    retrieved_at    TIMESTAMPTZ DEFAULT now()
);

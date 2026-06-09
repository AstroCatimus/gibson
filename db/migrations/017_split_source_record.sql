-- Gibson Migration 017: Split gibson_source_record into two tables
-- ─────────────────────────────────────────────────────────────────
-- gibson_source_record was two ideas wearing one name:
--
--   gibson_edition_source  — bibliographic provenance per edition (immutable)
--                            Written by: ISFDB, LOC MARC, Open Library importers,
--                            dedup agent, research agent.
--                            Lifecycle: forever. Never deleted, never compacted.
--
--   gibson_import_receipt  — import audit trail per stock item copy
--                            Written by: Ka-Zam and Amazon importers only.
--                            Lifecycle: follows the stock item.
--
-- Safe to re-run (CREATE IF NOT EXISTS; data migration uses INSERT...SELECT with
-- no-conflict guards; DROP at the end is conditional on both tables existing).
-- ─────────────────────────────────────────────────────────────────


-- ═══════════════════════════════════════════════════════════════
-- 1. gibson_edition_source — bibliographic provenance
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS gibson_edition_source (
    edition_source_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source             TEXT NOT NULL,        -- 'isfdb', 'open_library', 'loc_marc', etc.
    source_id          TEXT UNIQUE,          -- source's own identifier (deduplication key)
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

CREATE INDEX IF NOT EXISTS idx_edition_source_edition
    ON gibson_edition_source(matched_edition_id)
    WHERE matched_edition_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_edition_source_work
    ON gibson_edition_source(matched_work_id)
    WHERE matched_work_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_edition_source_isbn
    ON gibson_edition_source(isbn_13)
    WHERE isbn_13 IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_edition_source_source_id
    ON gibson_edition_source(source_id)
    WHERE source_id IS NOT NULL;


-- ═══════════════════════════════════════════════════════════════
-- 2. gibson_import_receipt — Ka-Zam / Amazon import audit trail
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS gibson_import_receipt (
    receipt_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          TEXT NOT NULL,  -- 'kazam' | 'amazon'
    external_id     TEXT,           -- KZ-XXXXXX or Amazon listing-id
    isbn_norm       TEXT,
    raw_data        JSONB NOT NULL,
    stock_item_id   UUID REFERENCES gibson_stock_item(stock_item_id),
    imported_at     TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_import_receipt_ext_id
    ON gibson_import_receipt(external_id, source)
    WHERE external_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_import_receipt_isbn
    ON gibson_import_receipt(isbn_norm)
    WHERE isbn_norm IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_import_receipt_item
    ON gibson_import_receipt(stock_item_id);


-- ═══════════════════════════════════════════════════════════════
-- 3. Migrate existing data
-- Rows with stock_item_id populated → import receipts
-- Rows without stock_item_id → edition sources
-- ═══════════════════════════════════════════════════════════════

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'gibson_source_record'
    ) THEN

        -- Import receipts (have a stock_item_id)
        INSERT INTO gibson_import_receipt
            (source, external_id, isbn_norm, raw_data, stock_item_id, imported_at)
        SELECT
            COALESCE(source, 'unknown'),
            external_id,
            isbn_norm,
            COALESCE(raw_data, '{}'::jsonb),
            stock_item_id,
            COALESCE(imported_at, ingested_at, now())
        FROM gibson_source_record
        WHERE stock_item_id IS NOT NULL
        ON CONFLICT DO NOTHING;

        -- Bibliographic provenance (no stock_item_id)
        INSERT INTO gibson_edition_source
            (source, source_id, raw_data, normalized_data,
             normalized_title, normalized_author, isbn_13,
             trust_tier, matched_work_id, matched_edition_id,
             match_confidence, ingested_at)
        SELECT
            COALESCE(source, 'unknown'),
            source_id,
            COALESCE(raw_data, '{}'::jsonb),
            normalized_data,
            normalized_title,
            normalized_author,
            isbn_13,
            COALESCE(trust_tier, 4),
            matched_work_id,
            matched_edition_id,
            match_confidence,
            COALESCE(ingested_at, now())
        FROM gibson_source_record
        WHERE stock_item_id IS NULL
        ON CONFLICT (source_id) DO NOTHING;

    END IF;
END $$;


-- ═══════════════════════════════════════════════════════════════
-- 4. Row Level Security
-- gibson_edition_source: bib commons — open to all authenticated users
-- gibson_import_receipt: store-scoped via stock_item → gibson_stock_item RLS
-- ═══════════════════════════════════════════════════════════════

ALTER TABLE gibson_edition_source  ENABLE ROW LEVEL SECURITY;
ALTER TABLE gibson_import_receipt  ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS bib_authenticated ON gibson_edition_source;
CREATE POLICY bib_authenticated ON gibson_edition_source
    FOR ALL
    USING  (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

DROP POLICY IF EXISTS store_member_only ON gibson_import_receipt;
CREATE POLICY store_member_only ON gibson_import_receipt
    FOR ALL
    USING (
        stock_item_id IN (
            SELECT stock_item_id FROM gibson_stock_item
            WHERE store_id IN (SELECT gibson_my_store_ids())
        )
    )
    WITH CHECK (
        stock_item_id IN (
            SELECT stock_item_id FROM gibson_stock_item
            WHERE store_id IN (SELECT gibson_my_store_ids())
        )
    );


-- ═══════════════════════════════════════════════════════════════
-- 5. Drop the old table
-- CASCADE drops its indexes, RLS policies, and any FK constraints.
-- ═══════════════════════════════════════════════════════════════

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'gibson_source_record'
    ) THEN
        DROP TABLE gibson_source_record CASCADE;
    END IF;
END $$;

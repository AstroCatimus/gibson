-- Gibson Inventory Defrag Schema
-- Shelf verification, source records, Ka-Zam location mapping

-- ── Stock item additions ──────────────────────────────────────────
ALTER TABLE gibson_stock_item
    ADD COLUMN IF NOT EXISTS shelf_verification_status TEXT DEFAULT 'UNVERIFIED'
        CHECK (shelf_verification_status IN (
            'UNVERIFIED','VERIFIED','MISSING','NEEDS_VERIFICATION','SOLD_CONFIRMED'
        )),
    ADD COLUMN IF NOT EXISTS trust_tier INT DEFAULT 1
        CHECK (trust_tier IN (1,2,3)),
    -- 1 = physical Gibson scan  2 = Amazon import  3 = Ka-Zam import
    ADD COLUMN IF NOT EXISTS amazon_status  TEXT,
    ADD COLUMN IF NOT EXISTS kz_status      TEXT,
    ADD COLUMN IF NOT EXISTS amazon_listing_id TEXT,
    ADD COLUMN IF NOT EXISTS amazon_asin    TEXT,
    ADD COLUMN IF NOT EXISTS amazon_condition_code INT,
    ADD COLUMN IF NOT EXISTS verified_at    TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS verified_by    UUID;

-- ── Raw source records (Ka-Zam + Amazon preserved as JSONB) ──────
CREATE TABLE IF NOT EXISTS gibson_source_record (
    source_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type     TEXT NOT NULL CHECK (source_type IN ('kazam','amazon')),
    external_id     TEXT,              -- KZ-XXXXXX  or  Amazon listing-id
    isbn_norm       TEXT,
    raw_data        JSONB NOT NULL,
    stock_item_id   UUID REFERENCES gibson_stock_item(stock_item_id),
    imported_at     TIMESTAMPTZ DEFAULT now()
);

-- Backfill columns if table already existed from an earlier partial run
ALTER TABLE gibson_source_record ADD COLUMN IF NOT EXISTS source_type     TEXT;
ALTER TABLE gibson_source_record ADD COLUMN IF NOT EXISTS external_id     TEXT;
ALTER TABLE gibson_source_record ADD COLUMN IF NOT EXISTS isbn_norm       TEXT;
ALTER TABLE gibson_source_record ADD COLUMN IF NOT EXISTS raw_data        JSONB;
ALTER TABLE gibson_source_record ADD COLUMN IF NOT EXISTS stock_item_id   UUID REFERENCES gibson_stock_item(stock_item_id);
ALTER TABLE gibson_source_record ADD COLUMN IF NOT EXISTS imported_at     TIMESTAMPTZ DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_source_record_isbn  ON gibson_source_record(isbn_norm);
CREATE INDEX IF NOT EXISTS idx_source_record_type  ON gibson_source_record(source_type);
CREATE INDEX IF NOT EXISTS idx_source_record_item  ON gibson_source_record(stock_item_id);

-- ── Ka-Zam location → Gibson section mapping ─────────────────────
CREATE TABLE IF NOT EXISTS gibson_kz_location_map (
    kz_location     TEXT PRIMARY KEY,
    section         TEXT,
    section_code    TEXT,
    record_count    INT DEFAULT 0,
    mapped_by       TEXT DEFAULT 'auto',
    reviewed        BOOLEAN DEFAULT false,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ── Shelf verification sessions (audit trail) ────────────────────
CREATE TABLE IF NOT EXISTS gibson_verification_session (
    session_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id        UUID NOT NULL,
    user_id         TEXT NOT NULL,
    section         TEXT,
    started_at      TIMESTAMPTZ DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    verified_count  INT DEFAULT 0,
    missing_count   INT DEFAULT 0,
    skipped_count   INT DEFAULT 0
);

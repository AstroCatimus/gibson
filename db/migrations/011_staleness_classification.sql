-- Gibson Migration 011 — Price Staleness, ISBN Classification, Section Defrag Status

-- ── Stock item additions ─────────────────────────────────────
ALTER TABLE gibson_stock_item
    ADD COLUMN IF NOT EXISTS price_last_refreshed  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS isbn_flag             TEXT DEFAULT 'NORMAL'
        CHECK (isbn_flag IN ('NORMAL','PRE_ISBN','MISSING_ISBN','INVALID_ISBN','NON_STANDARD'));

-- Ka-Zam / Amazon imports land with price_last_refreshed = NULL → computed as LEGACY
-- Gibson scans land with price_last_refreshed = created_at
-- price_staleness is computed at read time from price_last_refreshed — no stored column needed

-- ── Location additions ────────────────────────────────────────
ALTER TABLE gibson_location
    ADD COLUMN IF NOT EXISTS defrag_status  TEXT DEFAULT 'NOT_STARTED'
        CHECK (defrag_status IN (
            'NOT_STARTED','IN_PROGRESS','PHOTO_COMPLETE','VERIFIED','NEEDS_REVISIT'
        )),
    ADD COLUMN IF NOT EXISTS last_scanned_at    TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS verified_count     INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS missing_count      INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS total_count        INT DEFAULT 0;

-- ── Shelf scan sessions (distinct from tap-through sessions) ──
CREATE TABLE IF NOT EXISTS gibson_shelf_scan (
    scan_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID REFERENCES gibson_verification_session(session_id),
    store_id        UUID NOT NULL,
    location_id     UUID REFERENCES gibson_location(location_id),
    section         TEXT,
    scanned_by      TEXT,
    scanned_at      TIMESTAMPTZ DEFAULT now(),
    spines_detected INT DEFAULT 0,
    auto_verified   INT DEFAULT 0,
    conflicts       INT DEFAULT 0,
    not_found       INT DEFAULT 0,
    unclear         INT DEFAULT 0,
    raw_results     JSONB
);

CREATE INDEX IF NOT EXISTS idx_shelf_scan_location  ON gibson_shelf_scan(location_id);
CREATE INDEX IF NOT EXISTS idx_shelf_scan_store      ON gibson_shelf_scan(store_id);
CREATE INDEX IF NOT EXISTS idx_shelf_scan_scanned_at ON gibson_shelf_scan(scanned_at);

-- ── Price refresh log ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS gibson_price_refresh (
    refresh_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stock_item_id   UUID REFERENCES gibson_stock_item(stock_item_id),
    old_price       NUMERIC(10,2),
    new_suggested   NUMERIC(10,2),
    price_low       NUMERIC(10,2),
    price_high      NUMERIC(10,2),
    source          TEXT,           -- vialibri, ebay, booksrun, etc.
    flagged         BOOLEAN DEFAULT false,
    flag_reason     TEXT,           -- PRICE_UP, PRICE_DOWN, LEGACY_REFRESH
    refreshed_at    TIMESTAMPTZ DEFAULT now(),
    actioned_by     TEXT,
    actioned_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_price_refresh_item ON gibson_price_refresh(stock_item_id);

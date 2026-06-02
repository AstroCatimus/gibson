-- ─── Marketplace Infrastructure ────────────────────────────────────────────
-- 016: Per-store platform integrations and per-listing records.
--
-- gibson_store_integration: one row per store per platform.
--   Stores OAuth tokens, seller ID, and platform-specific config (policy IDs etc).
--
-- gibson_listing: one row per stock item per platform.
--   Tracks live listing IDs, status, and the full last-submitted payload
--   (Amazon requires all fields on every resubmission).

CREATE TABLE IF NOT EXISTS gibson_store_integration (
    integration_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id            UUID NOT NULL,
    platform            TEXT NOT NULL CHECK (platform IN ('amazon', 'ebay', 'biblio', 'whatnot')),
    platform_seller_id  TEXT,
    access_token        TEXT,
    refresh_token       TEXT,
    token_expires_at    TIMESTAMPTZ,
    status              TEXT NOT NULL DEFAULT 'connected'
                            CHECK (status IN ('connected', 'disconnected', 'error', 'token_expired')),
    -- Platform-specific config: eBay policy IDs, Amazon marketplace ID, etc.
    platform_meta       JSONB NOT NULL DEFAULT '{}',
    connected_at        TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now(),
    UNIQUE (store_id, platform)
);

CREATE TABLE IF NOT EXISTS gibson_listing (
    listing_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stock_item_id       UUID NOT NULL REFERENCES gibson_stock_item(stock_item_id),
    store_id            UUID NOT NULL,
    platform            TEXT NOT NULL CHECK (platform IN ('amazon', 'ebay', 'biblio', 'whatnot')),
    -- Platform's own identifier for this listing (eBay offer ID, Amazon SKU)
    platform_listing_id TEXT,
    -- Amazon feed ID for async feed tracking
    platform_feed_id    TEXT,
    platform_item_url   TEXT,
    listed_price        NUMERIC(10,2),
    status              TEXT NOT NULL DEFAULT 'PENDING'
                            CHECK (status IN (
                                'PENDING',       -- submitted, awaiting platform confirmation
                                'ACTIVE',        -- live on platform
                                'SOLD',          -- sold via this platform
                                'DELISTED',      -- removed
                                'FAILED',        -- platform rejected it
                                'NEEDS_REVIEW'   -- e.g. Amazon condition_note bug
                            )),
    -- Full last-submitted payload (Amazon requires all fields on every resubmit)
    listing_payload     JSONB,
    error_message       TEXT,
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now(),
    sold_at             TIMESTAMPTZ,
    UNIQUE (stock_item_id, platform)
);

CREATE INDEX IF NOT EXISTS idx_gibson_listing_stock_item
    ON gibson_listing(stock_item_id);
CREATE INDEX IF NOT EXISTS idx_gibson_listing_platform_status
    ON gibson_listing(platform, status);
CREATE INDEX IF NOT EXISTS idx_gibson_listing_feed
    ON gibson_listing(platform_feed_id) WHERE platform_feed_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_gibson_store_integration_store
    ON gibson_store_integration(store_id);

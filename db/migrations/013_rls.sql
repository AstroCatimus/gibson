-- Gibson Migration 013: Row Level Security
-- ─────────────────────────────────────────────────────────────────
-- Enforces the two-layer data model at the database level:
--
--   BIB COMMONS   — Work, Edition, Agent, Source Records
--                   Any authenticated user can read.
--                   Any authenticated user can insert/update
--                   (research agent, corrections, enrichment).
--
--   STORE LAYER   — Stock Item, Location, Sale, Buy Queue, etc.
--                   Read/write only for active members of the
--                   owning store (via gibson_store_member).
--
-- Policy uses auth.uid() from Supabase JWT — no app-layer enforcement needed.
-- Safe to re-run (all statements use IF NOT EXISTS / OR REPLACE).
-- ─────────────────────────────────────────────────────────────────


-- ═══════════════════════════════════════════════════════════════
-- HELPER FUNCTION
-- Returns the set of store_ids the current user is an active member of.
-- Used in every store-layer policy.
-- ═══════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION gibson_my_store_ids()
RETURNS SETOF UUID
LANGUAGE sql
STABLE
SECURITY DEFINER
AS $$
    SELECT store_id
    FROM gibson_store_member
    WHERE user_id = auth.uid()::text
      AND status = 'active';
$$;


-- ═══════════════════════════════════════════════════════════════
-- BIB COMMONS — readable and writable by all authenticated users
-- ═══════════════════════════════════════════════════════════════

ALTER TABLE gibson_work           ENABLE ROW LEVEL SECURITY;
ALTER TABLE gibson_edition        ENABLE ROW LEVEL SECURITY;
ALTER TABLE gibson_agent          ENABLE ROW LEVEL SECURITY;
ALTER TABLE gibson_publisher      ENABLE ROW LEVEL SECURITY;
ALTER TABLE gibson_work_agent     ENABLE ROW LEVEL SECURITY;
ALTER TABLE gibson_edition_agent  ENABLE ROW LEVEL SECURITY;
ALTER TABLE gibson_edition_publisher ENABLE ROW LEVEL SECURITY;
ALTER TABLE gibson_source_record  ENABLE ROW LEVEL SECURITY;

-- One open policy per bib table: authenticated = full access
DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'gibson_work',
        'gibson_edition',
        'gibson_agent',
        'gibson_publisher',
        'gibson_work_agent',
        'gibson_edition_agent',
        'gibson_edition_publisher',
        'gibson_source_record'
    ] LOOP
        EXECUTE format(
            'DROP POLICY IF EXISTS bib_authenticated ON %I;
             CREATE POLICY bib_authenticated ON %I
             FOR ALL
             USING (auth.role() = ''authenticated'')
             WITH CHECK (auth.role() = ''authenticated'');',
            t, t
        );
    END LOOP;
END $$;


-- ═══════════════════════════════════════════════════════════════
-- STORE LAYER — locked to owning store's active members
-- ═══════════════════════════════════════════════════════════════

ALTER TABLE gibson_stock_item     ENABLE ROW LEVEL SECURITY;
ALTER TABLE gibson_location       ENABLE ROW LEVEL SECURITY;
ALTER TABLE gibson_sale_record    ENABLE ROW LEVEL SECURITY;
ALTER TABLE gibson_sale_item      ENABLE ROW LEVEL SECURITY;
ALTER TABLE gibson_buy_queue      ENABLE ROW LEVEL SECURITY;
-- gibson_want_list has no store_id (links to customer, not store)
-- treat as authenticated-only, same as bib commons
ALTER TABLE gibson_want_list      ENABLE ROW LEVEL SECURITY;
ALTER TABLE gibson_store          ENABLE ROW LEVEL SECURITY;
ALTER TABLE gibson_store_member   ENABLE ROW LEVEL SECURITY;

-- gibson_stock_item
DROP POLICY IF EXISTS store_member_only ON gibson_stock_item;
CREATE POLICY store_member_only ON gibson_stock_item
    FOR ALL
    USING  (store_id IN (SELECT gibson_my_store_ids()))
    WITH CHECK (store_id IN (SELECT gibson_my_store_ids()));

-- gibson_location
DROP POLICY IF EXISTS store_member_only ON gibson_location;
CREATE POLICY store_member_only ON gibson_location
    FOR ALL
    USING  (store_id IN (SELECT gibson_my_store_ids()))
    WITH CHECK (store_id IN (SELECT gibson_my_store_ids()));

-- gibson_sale_record
DROP POLICY IF EXISTS store_member_only ON gibson_sale_record;
CREATE POLICY store_member_only ON gibson_sale_record
    FOR ALL
    USING  (store_id IN (SELECT gibson_my_store_ids()))
    WITH CHECK (store_id IN (SELECT gibson_my_store_ids()));

-- gibson_sale_item (joins through sale_record — filter via subquery)
DROP POLICY IF EXISTS store_member_only ON gibson_sale_item;
CREATE POLICY store_member_only ON gibson_sale_item
    FOR ALL
    USING (
        sale_id IN (
            SELECT sale_id FROM gibson_sale_record
            WHERE store_id IN (SELECT gibson_my_store_ids())
        )
    )
    WITH CHECK (
        sale_id IN (
            SELECT sale_id FROM gibson_sale_record
            WHERE store_id IN (SELECT gibson_my_store_ids())
        )
    );

-- gibson_buy_queue
DROP POLICY IF EXISTS store_member_only ON gibson_buy_queue;
CREATE POLICY store_member_only ON gibson_buy_queue
    FOR ALL
    USING  (store_id IN (SELECT gibson_my_store_ids()))
    WITH CHECK (store_id IN (SELECT gibson_my_store_ids()));

-- gibson_want_list — no store_id, customer-linked, open to authenticated users
DROP POLICY IF EXISTS want_list_authenticated ON gibson_want_list;
CREATE POLICY want_list_authenticated ON gibson_want_list
    FOR ALL
    USING  (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

-- gibson_store — members can read their own store's record
DROP POLICY IF EXISTS store_read_own ON gibson_store;
CREATE POLICY store_read_own ON gibson_store
    FOR SELECT
    USING (store_id IN (SELECT gibson_my_store_ids()));

-- gibson_store_member — users can see membership records for their own stores
DROP POLICY IF EXISTS store_member_read ON gibson_store_member;
CREATE POLICY store_member_read ON gibson_store_member
    FOR SELECT
    USING (store_id IN (SELECT gibson_my_store_ids()));

-- Only owners/admins can add or remove members
DROP POLICY IF EXISTS store_member_manage ON gibson_store_member;
CREATE POLICY store_member_manage ON gibson_store_member
    FOR ALL
    USING (
        store_id IN (
            SELECT store_id FROM gibson_store_member
            WHERE user_id = auth.uid()::text
              AND status = 'active'
              AND role IN ('owner', 'admin')
        )
    )
    WITH CHECK (
        store_id IN (
            SELECT store_id FROM gibson_store_member
            WHERE user_id = auth.uid()::text
              AND status = 'active'
              AND role IN ('owner', 'admin')
        )
    );


-- ═══════════════════════════════════════════════════════════════
-- PRICING RECORD — cooperative commons, no store_id by design
-- All authenticated users read aggregate pricing.
-- Inserts allowed from any authenticated user (pricing agent).
-- ═══════════════════════════════════════════════════════════════

ALTER TABLE gibson_pricing_record ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pricing_authenticated ON gibson_pricing_record;
CREATE POLICY pricing_authenticated ON gibson_pricing_record
    FOR ALL
    USING  (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');


-- ═══════════════════════════════════════════════════════════════
-- SERVICE ROLE BYPASS
-- The backend API runs with the Supabase service role key which
-- bypasses RLS entirely. This is correct — the API enforces
-- store_id at the query level. RLS is a second layer of defence
-- for direct DB access (Supabase Studio, external tools).
-- ═══════════════════════════════════════════════════════════════
-- No action needed — service role bypass is Supabase default behaviour.

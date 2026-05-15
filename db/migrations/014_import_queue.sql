-- Gibson Migration 014: Durable Import Queue
-- ─────────────────────────────────────────────────────────────────
-- Decouples file uploads from API availability.
--
-- Flow:
--   1. Mobile uploads TSV/CSV to Supabase Storage bucket "gibson-imports"
--   2. Mobile inserts a row here — no API needed for steps 1-2.
--   3. Gibson API (when running) polls for PENDING rows, downloads the file
--      from Storage using the service role key, runs the existing import
--      pipeline, and writes stats back to this row.
--   4. Mobile polls this table directly via Supabase client to show progress.
--
-- Storage bucket policy (set up once in Supabase dashboard):
--   Bucket: gibson-imports
--   INSERT: authenticated users (mobile uploads use session JWT)
--   SELECT: service role only (API downloads)
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS gibson_import_queue (
    queue_id      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id      UUID        NOT NULL,
    source        TEXT        NOT NULL CHECK (source IN ('amazon', 'kazam')),
    storage_path  TEXT        NOT NULL,   -- e.g. "dl/1716000000-inventory.tsv"
    filename      TEXT        NOT NULL,
    status        TEXT        NOT NULL DEFAULT 'PENDING'
                  CHECK (status IN ('PENDING', 'PROCESSING', 'DONE', 'FAILED')),
    total         INTEGER,
    processed     INTEGER     DEFAULT 0,
    created       INTEGER     DEFAULT 0,
    skipped       INTEGER     DEFAULT 0,
    errors        INTEGER     DEFAULT 0,
    pct           INTEGER     DEFAULT 0,
    error_details JSONB       DEFAULT '[]'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Worker polls by status+age; store filters for SELECT policies
CREATE INDEX IF NOT EXISTS idx_import_queue_status
    ON gibson_import_queue (status, created_at);
CREATE INDEX IF NOT EXISTS idx_import_queue_store
    ON gibson_import_queue (store_id, created_at DESC);


-- ── Row Level Security ───────────────────────────────────────────
ALTER TABLE gibson_import_queue ENABLE ROW LEVEL SECURITY;

-- Store members may queue imports for their own store
CREATE POLICY "store members can insert import queue"
    ON gibson_import_queue
    FOR INSERT
    WITH CHECK (store_id IN (SELECT gibson_my_store_ids()));

-- Store members may read their store's queue (for progress polling)
CREATE POLICY "store members can read import queue"
    ON gibson_import_queue
    FOR SELECT
    USING (store_id IN (SELECT gibson_my_store_ids()));

-- Note: the API uses the service role key, which bypasses RLS entirely.
-- All UPDATE/DELETE for processing happen via service role — no policy needed.

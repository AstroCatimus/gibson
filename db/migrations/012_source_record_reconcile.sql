-- Gibson Migration 012: Reconcile gibson_source_record
-- ─────────────────────────────────────────────────────────────────
-- Migration 001 created this table with the canonical schema.
-- Migration 010 added import-specific columns via ALTER TABLE.
-- This migration ensures the complete canonical column set exists
-- and adds indexes for fast idempotency lookups during imports.
-- Safe to re-run (all statements use IF NOT EXISTS / IF EXISTS).

-- Ensure import columns from migration 010 exist with correct types
ALTER TABLE gibson_source_record
    ADD COLUMN IF NOT EXISTS external_id   TEXT,
    ADD COLUMN IF NOT EXISTS isbn_norm     TEXT,
    ADD COLUMN IF NOT EXISTS stock_item_id UUID REFERENCES gibson_stock_item(stock_item_id),
    ADD COLUMN IF NOT EXISTS imported_at   TIMESTAMPTZ DEFAULT now();

-- Drop the source_type column added by migration 010 — canonical column is 'source' (from 001)
-- Only drop if source_type exists and source already has data
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'gibson_source_record' AND column_name = 'source_type'
    ) THEN
        -- Backfill source from source_type where source is empty
        UPDATE gibson_source_record
        SET source = source_type
        WHERE (source IS NULL OR source = '') AND source_type IS NOT NULL;

        ALTER TABLE gibson_source_record DROP COLUMN IF EXISTS source_type;
    END IF;
END $$;

-- Index for fast idempotency checks during import (external_id + source)
CREATE INDEX IF NOT EXISTS idx_source_record_ext_id
    ON gibson_source_record(external_id, source)
    WHERE external_id IS NOT NULL;

-- Index for ISBN lookups (agent source cascade uses this)
CREATE INDEX IF NOT EXISTS idx_source_record_isbn_norm
    ON gibson_source_record(isbn_norm)
    WHERE isbn_norm IS NOT NULL;

-- Index for source lookups
CREATE INDEX IF NOT EXISTS idx_source_record_source
    ON gibson_source_record(source);

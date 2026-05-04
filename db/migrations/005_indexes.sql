-- ═══════════════════════════════════════════════════════════════
-- Gibson Migration 005: Indexes
-- Performance-critical lookups for identification and pricing
-- ═══════════════════════════════════════════════════════════════

-- Edition lookups
CREATE INDEX IF NOT EXISTS idx_gibson_edition_isbn13 ON gibson_edition(isbn_13);
CREATE INDEX IF NOT EXISTS idx_gibson_edition_isbn10 ON gibson_edition(isbn_10);
CREATE INDEX IF NOT EXISTS idx_gibson_edition_usbn ON gibson_edition(usbn);
CREATE INDEX IF NOT EXISTS idx_gibson_edition_work ON gibson_edition(work_id);

-- Stock item lookups (store_id first — always filtered)
CREATE INDEX IF NOT EXISTS idx_gibson_stock_item_edition ON gibson_stock_item(edition_id);
CREATE INDEX IF NOT EXISTS idx_gibson_stock_item_sku ON gibson_stock_item(gibson_sku);
CREATE INDEX IF NOT EXISTS idx_gibson_stock_item_seller_sku ON gibson_stock_item(seller_sku);
CREATE INDEX IF NOT EXISTS idx_gibson_stock_item_status ON gibson_stock_item(status);
CREATE INDEX IF NOT EXISTS idx_gibson_stock_item_store ON gibson_stock_item(store_id);
CREATE INDEX IF NOT EXISTS idx_gibson_stock_item_store_status ON gibson_stock_item(store_id, status);

-- Name lookups (sort order)
CREATE INDEX IF NOT EXISTS idx_gibson_work_title_sort ON gibson_work(title_sort);
CREATE INDEX IF NOT EXISTS idx_gibson_agent_name_sort ON gibson_agent(name_sort);
CREATE INDEX IF NOT EXISTS idx_gibson_publisher_name_sort ON gibson_publisher(name_sort);

-- Pricing lookups
CREATE INDEX IF NOT EXISTS idx_gibson_pricing_edition ON gibson_pricing_record(edition_id);
CREATE INDEX IF NOT EXISTS idx_gibson_pricing_source ON gibson_pricing_record(source);

-- Correction review queue
CREATE INDEX IF NOT EXISTS idx_gibson_correction_concern ON gibson_correction(concern_level, reviewed_by);

-- Ghost Book pipeline
CREATE INDEX IF NOT EXISTS idx_gibson_ghost_book_status ON gibson_ghost_book_record(research_status);

-- Customer features
CREATE INDEX IF NOT EXISTS idx_gibson_visit_date ON gibson_visit_schedule(store_id, visit_date);
CREATE INDEX IF NOT EXISTS idx_gibson_want_list_status ON gibson_want_list(status);

-- Full-text search
CREATE INDEX IF NOT EXISTS idx_gibson_work_title_fts ON gibson_work USING gin(to_tsvector('english', title));
CREATE INDEX IF NOT EXISTS idx_gibson_agent_name_fts ON gibson_agent USING gin(to_tsvector('english', name_display));

-- Trigram similarity search
CREATE INDEX IF NOT EXISTS idx_gibson_work_title_trgm ON gibson_work USING gin(title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_gibson_agent_name_trgm ON gibson_agent USING gin(name_display gin_trgm_ops);

-- Location lookups
CREATE INDEX IF NOT EXISTS idx_gibson_location_store ON gibson_location(store_id);

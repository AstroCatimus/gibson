-- ═══════════════════════════════════════════════════════════════
-- Gibson Migration 003: Correction Engine & Training Loop
-- ═══════════════════════════════════════════════════════════════

-- ─── Correction ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS gibson_correction (
    correction_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stock_item_id    UUID REFERENCES gibson_stock_item(stock_item_id),
    edition_id       UUID REFERENCES gibson_edition(edition_id),
    field_name       TEXT NOT NULL,
    original_value   TEXT,
    corrected_value  TEXT,
    corrected_by     UUID REFERENCES gibson_employee(employee_id),
    correction_reason TEXT,
    gibson_original_confidence NUMERIC(3,2),
    concern_level    TEXT DEFAULT 'MEDIUM' CHECK (concern_level IN ('HIGH','MEDIUM','LOW')),
    is_training_pair BOOLEAN DEFAULT false,
    reviewed_by      UUID REFERENCES gibson_employee(employee_id),
    created_at       TIMESTAMPTZ DEFAULT now()
);

-- Concern level rules (set by correction service):
-- HIGH: bib field on book >$25, conflicts source record,
--       confidence >85% and corrected, same field corrected by multiple people
-- MEDIUM: condition override on online-listed book, price >40% from comps,
--         any Ghost Book correction
-- LOW: first-floor commodity condition tap, section change, confidence <50%

-- ─── Training Example ───────────────────────────────────────

CREATE TABLE IF NOT EXISTS gibson_training_example (
    example_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    example_type  TEXT NOT NULL CHECK (example_type IN (
                      'bibliographic_extraction','condition_grade',
                      'pricing_decision','routing_decision',
                      'ghost_book_identification')),
    input_data    JSONB NOT NULL,
    output_data   JSONB NOT NULL,
    source        TEXT,
    quality_score NUMERIC(3,2),
    reviewed      BOOLEAN DEFAULT false,
    created_at    TIMESTAMPTZ DEFAULT now()
);

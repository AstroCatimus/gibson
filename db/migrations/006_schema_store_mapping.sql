-- ═══════════════════════════════════════════════════════════════
-- Gibson Migration 006: Store Mapping & Physical Intelligence
-- Room → Container → Shelf → Container Item
-- Continuous spatial intelligence layer over the physical store
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS gibson_room (
    room_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id        UUID REFERENCES gibson_store(store_id),
    name            TEXT NOT NULL,
    floor           TEXT,
    video_url       TEXT,
    floor_plan_json JSONB,       -- spatial model (post-migration, local GPU)
    mapped_at       TIMESTAMPTZ,
    last_updated    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS gibson_container (
    container_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    room_id          UUID REFERENCES gibson_room(room_id),
    container_type   TEXT NOT NULL CHECK (container_type IN (
                         'shelf_unit','box','table','cart','pile','other')),
    name             TEXT NOT NULL,
    name_source      TEXT CHECK (name_source IN (
                         'sticky_note','user_input','gibson_proposed')),
    sticky_note_text TEXT,
    position_in_room JSONB,      -- {x, y, orientation}
    photo_url        TEXT,
    video_url        TEXT,
    shelf_count      INT,
    status           TEXT DEFAULT 'MAPPED' CHECK (status IN (
                         'MAPPED','PARTIALLY_INVENTORIED',
                         'FULLY_INVENTORIED','NEEDS_RESHOOT','SEALED')),
    notes            TEXT,
    created_at       TIMESTAMPTZ DEFAULT now(),
    updated_at       TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS gibson_shelf (
    shelf_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    container_id        UUID REFERENCES gibson_container(container_id),
    shelf_number        INT NOT NULL,     -- 1 = top shelf, counts down
    photo_url           TEXT,
    book_count_est      INT,
    spine_manifest      JSONB,            -- [{text, confidence, position}]
    last_photographed   TIMESTAMPTZ,
    last_scanned        TIMESTAMPTZ,
    status              TEXT DEFAULT 'UNCATALOGUED' CHECK (status IN (
                            'UNCATALOGUED','PARTIALLY_CATALOGUED',
                            'FULLY_CATALOGUED','NEEDS_RESHOOT'))
);

CREATE TABLE IF NOT EXISTS gibson_container_item (
    item_id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shelf_id                  UUID REFERENCES gibson_shelf(shelf_id),
    container_id              UUID REFERENCES gibson_container(container_id),
    stock_item_id             UUID REFERENCES gibson_stock_item(stock_item_id),
    spine_text_raw            TEXT,
    identified_work_id        UUID REFERENCES gibson_work(work_id),
    identification_confidence NUMERIC(3,2),
    position_on_shelf         INT,
    photo_region              JSONB,       -- bounding box in shelf photo
    pull_recommended          BOOLEAN DEFAULT false,
    pull_reason               TEXT,
    pull_priority             INT,         -- 1 = highest
    resolved_at               TIMESTAMPTZ,
    created_at                TIMESTAMPTZ DEFAULT now()
);

-- Indexes for store mapping
CREATE INDEX IF NOT EXISTS idx_gibson_container_room ON gibson_container(room_id);
CREATE INDEX IF NOT EXISTS idx_gibson_shelf_container ON gibson_shelf(container_id);
CREATE INDEX IF NOT EXISTS idx_gibson_container_item_shelf ON gibson_container_item(shelf_id);
CREATE INDEX IF NOT EXISTS idx_gibson_container_item_pull ON gibson_container_item(pull_recommended, pull_priority);
CREATE INDEX IF NOT EXISTS idx_gibson_container_item_stock ON gibson_container_item(stock_item_id);

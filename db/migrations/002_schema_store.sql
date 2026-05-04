-- ═══════════════════════════════════════════════════════════════
-- Gibson Migration 002: Store, Location, Employee, Sales, Customer
-- ═══════════════════════════════════════════════════════════════

-- ─── Store ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS gibson_store (
    store_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name       TEXT NOT NULL,
    prefix     TEXT NOT NULL,    -- 'DL', 'MG'
    address    TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ─── Location (section within a store) ──────────────────────

CREATE TABLE IF NOT EXISTS gibson_location (
    location_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id     UUID NOT NULL REFERENCES gibson_store(store_id),
    floor        TEXT,
    section      TEXT,
    section_code TEXT,
    subsection   TEXT,
    shelf_unit   TEXT,
    slot         TEXT,
    notes        TEXT
);

-- ─── Employee ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS gibson_employee (
    employee_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id     UUID REFERENCES gibson_store(store_id),
    name         TEXT NOT NULL,
    initials     TEXT NOT NULL,   -- used in SKU: JS-1213
    role         TEXT,
    pin          TEXT,            -- hashed
    created_at   TIMESTAMPTZ DEFAULT now()
);

-- SKU sequence: employee initials + global sequential number
CREATE SEQUENCE IF NOT EXISTS gibson_sku_seq START 1000;

-- ─── Customer ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS gibson_customer (
    customer_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT,
    email       TEXT UNIQUE,
    phone       TEXT,
    auth_token  TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- ─── Sale Record ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS gibson_sale_record (
    sale_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id       UUID NOT NULL REFERENCES gibson_store(store_id),
    employee_id    UUID REFERENCES gibson_employee(employee_id),
    sale_timestamp TIMESTAMPTZ DEFAULT now(),
    total_amount   NUMERIC(10,2),
    tax_amount     NUMERIC(10,2),
    payment_method TEXT,
    customer_id    UUID REFERENCES gibson_customer(customer_id),
    notes          TEXT
);

-- ─── Sale Item ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS gibson_sale_item (
    sale_item_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sale_id        UUID NOT NULL REFERENCES gibson_sale_record(sale_id),
    stock_item_id  UUID NOT NULL REFERENCES gibson_stock_item(stock_item_id),
    asking_price   NUMERIC(10,2),
    realized_price NUMERIC(10,2) NOT NULL,
    discount_reason TEXT
);

-- ─── Buy Queue ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS gibson_buy_queue (
    buy_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id      UUID REFERENCES gibson_store(store_id),
    employee_id   UUID REFERENCES gibson_employee(employee_id),
    customer_id   UUID REFERENCES gibson_customer(customer_id),
    status        TEXT DEFAULT 'PENDING' CHECK (status IN (
                      'PENDING','OFFERED','ACCEPTED','DECLINED','COMPLETE')),
    haul_images   TEXT[] DEFAULT '{}',
    cash_offer    NUMERIC(10,2),
    credit_offer  NUMERIC(10,2),
    offer_accepted_at TIMESTAMPTZ,
    notes         TEXT,
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ DEFAULT now()
);

-- ─── Want List ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS gibson_want_list (
    want_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID REFERENCES gibson_customer(customer_id),
    query_text  TEXT NOT NULL,
    work_id     UUID REFERENCES gibson_work(work_id),
    agent_id    UUID REFERENCES gibson_agent(agent_id),
    status      TEXT DEFAULT 'ACTIVE',
    notified_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- ─── Visit Schedule ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS gibson_visit_schedule (
    visit_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id  UUID REFERENCES gibson_customer(customer_id),
    store_id     UUID REFERENCES gibson_store(store_id),
    visit_date   DATE NOT NULL,
    arrival_time TEXT,
    wants_note   TEXT,
    prep_note    TEXT,
    status       TEXT DEFAULT 'SCHEDULED' CHECK (status IN (
                     'SCHEDULED','PREPPED','VISITED','CANCELLED')),
    created_at   TIMESTAMPTZ DEFAULT now()
);

-- ─── Pricing Record ─────────────────────────────────────────
-- NO store_id — realized prices are cooperative commons

CREATE TABLE IF NOT EXISTS gibson_pricing_record (
    pricing_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    edition_id      UUID REFERENCES gibson_edition(edition_id),
    source          TEXT NOT NULL,
    price_type      TEXT NOT NULL CHECK (price_type IN ('asking','realized','trend')),
    amount          NUMERIC(10,2),
    currency        TEXT DEFAULT 'USD',
    condition_grade TEXT,
    url             TEXT,
    retrieved_at    TIMESTAMPTZ DEFAULT now(),
    listing_date    DATE
);

-- Add foreign key from stock_item to store and location
ALTER TABLE gibson_stock_item
    ADD CONSTRAINT fk_stock_item_store
    FOREIGN KEY (store_id) REFERENCES gibson_store(store_id);

ALTER TABLE gibson_stock_item
    ADD CONSTRAINT fk_stock_item_location
    FOREIGN KEY (location_id) REFERENCES gibson_location(location_id);

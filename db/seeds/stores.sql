-- ═══════════════════════════════════════════════════════════════
-- Gibson Seeds: Stores, Employees, Test Data
-- ═══════════════════════════════════════════════════════════════

-- ─── Stores ─────────────────────────────────────────────────

INSERT INTO gibson_store (store_id, name, prefix, address)
VALUES
    ('a1b2c3d4-0001-4000-8000-000000000001', 'Driftless Books & Music', 'DL',
     '518 Walnut Street, Viroqua, Wisconsin 54665'),
    ('a1b2c3d4-0002-4000-8000-000000000002', 'Metaphysical Graffiti', 'MG',
     'Viroqua, Wisconsin')
ON CONFLICT (store_id) DO NOTHING;

-- ─── Employees ──────────────────────────────────────────────

INSERT INTO gibson_employee (store_id, name, initials, role)
VALUES
    ('a1b2c3d4-0001-4000-8000-000000000001', 'Jill', 'JS', 'bookseller'),
    ('a1b2c3d4-0001-4000-8000-000000000001', 'Kim', 'KK', 'bookseller'),
    ('a1b2c3d4-0001-4000-8000-000000000001', 'Eddy', 'ES', 'owner')
ON CONFLICT DO NOTHING;

-- ─── Sample Sections (Driftless — partial, pending master list photo) ──

INSERT INTO gibson_location (store_id, floor, section, section_code)
VALUES
    ('a1b2c3d4-0001-4000-8000-000000000001', 'First Floor', 'Fiction', 'F'),
    ('a1b2c3d4-0001-4000-8000-000000000001', 'First Floor', 'Science Fiction', 'SF'),
    ('a1b2c3d4-0001-4000-8000-000000000001', 'First Floor', 'Mystery', 'M'),
    ('a1b2c3d4-0001-4000-8000-000000000001', 'First Floor', 'Biography', 'Bio'),
    ('a1b2c3d4-0001-4000-8000-000000000001', 'First Floor', 'History', 'H'),
    ('a1b2c3d4-0001-4000-8000-000000000001', 'First Floor', 'Wisconsin / Nature', 'WN'),
    ('a1b2c3d4-0001-4000-8000-000000000001', 'First Floor', 'Religion / Christian', 'RC'),
    ('a1b2c3d4-0001-4000-8000-000000000001', 'First Floor', 'Philosophy', 'P'),
    ('a1b2c3d4-0001-4000-8000-000000000001', 'First Floor', 'Art', 'A'),
    ('a1b2c3d4-0001-4000-8000-000000000001', 'First Floor', 'Music', 'Mu'),
    ('a1b2c3d4-0001-4000-8000-000000000001', 'First Floor', 'Poetry', 'Po'),
    ('a1b2c3d4-0001-4000-8000-000000000001', 'First Floor', 'Cooking', 'C'),
    ('a1b2c3d4-0001-4000-8000-000000000001', 'First Floor', 'Children', 'Ch'),
    ('a1b2c3d4-0001-4000-8000-000000000001', 'Second Floor', 'Catalogued Stock', 'CAT'),
    ('a1b2c3d4-0001-4000-8000-000000000001', 'Second Floor', 'Unresearched', 'UNR'),
    -- Metaphysical Graffiti sections
    ('a1b2c3d4-0002-4000-8000-000000000002', 'Main Floor', 'Metaphysics', 'MG-Meta'),
    ('a1b2c3d4-0002-4000-8000-000000000002', 'Main Floor', 'Radical Politics', 'MG-Pol'),
    ('a1b2c3d4-0002-4000-8000-000000000002', 'Main Floor', 'Homesteading', 'MG-Home'),
    ('a1b2c3d4-0002-4000-8000-000000000002', 'Main Floor', 'Conspiracy', 'MG-Con'),
    ('a1b2c3d4-0002-4000-8000-000000000002', 'Main Floor', 'SF Paperbacks', 'MG-SF'),
    ('a1b2c3d4-0002-4000-8000-000000000002', 'Main Floor', 'eBay Room', 'MG-eBay')
ON CONFLICT DO NOTHING;

-- ─── Test Book (one complete Work → Edition → Stock Item) ───

DO $$
DECLARE
    v_work_id UUID;
    v_edition_id UUID;
    v_agent_id UUID;
    v_publisher_id UUID;
BEGIN
    -- Agent
    INSERT INTO gibson_agent (name_display, name_sort, agent_type)
    VALUES ('Edward Abbey', 'Abbey, Edward', 'person')
    RETURNING agent_id INTO v_agent_id;

    -- Publisher
    INSERT INTO gibson_publisher (name_display, name_sort, publisher_type)
    VALUES ('J.B. Lippincott', 'Lippincott, J.B.', 'commercial')
    RETURNING publisher_id INTO v_publisher_id;

    -- Work
    INSERT INTO gibson_work (title, title_sort, work_type, subject_terms, genre_terms)
    VALUES ('Desert Solitaire', 'desert solitaire', 'monograph',
            ARRAY['nature','environment','desert','Utah'],
            ARRAY['nature writing','memoir'])
    RETURNING work_id INTO v_work_id;

    -- Work ↔ Agent
    INSERT INTO gibson_work_agent (work_id, agent_id, role)
    VALUES (v_work_id, v_agent_id, 'author');

    -- Edition
    INSERT INTO gibson_edition (work_id, isbn_13, isbn_10, title_on_piece,
                                edition_statement, publication_year, format, page_count)
    VALUES (v_work_id, '9780671695880', '0671695886', 'Desert Solitaire',
            'First Touchstone Edition', 1990, 'trade_paperback', 303)
    RETURNING edition_id INTO v_edition_id;

    -- Edition ↔ Publisher
    INSERT INTO gibson_edition_publisher (edition_id, publisher_id, role)
    VALUES (v_edition_id, v_publisher_id, 'publisher');

    -- Stock Item
    INSERT INTO gibson_stock_item (edition_id, gibson_sku, store_id, condition_grade,
                                    condition_mode, status, asking_price, cost_basis)
    VALUES (v_edition_id, 'ES-1000',
            'a1b2c3d4-0001-4000-8000-000000000001',
            'Very Good', 'tap', 'AVAILABLE', 12.00, 2.00);
END $$;

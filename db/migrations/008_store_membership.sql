-- ═══════════════════════════════════════════════════════════════
-- Gibson Migration 008: Store Membership & Join Requests
-- ═══════════════════════════════════════════════════════════════
-- Adds invite codes, store membership tracking, and a join
-- request queue with owner/admin approval gating.
-- ═══════════════════════════════════════════════════════════════

-- ─── Add invite_code + created_by to gibson_store ────────────

ALTER TABLE gibson_store
    ADD COLUMN IF NOT EXISTS invite_code TEXT UNIQUE,
    ADD COLUMN IF NOT EXISTS created_by  TEXT;   -- Supabase auth user UUID

-- Give the two seed stores stable invite codes
UPDATE gibson_store
   SET invite_code = 'DRIFT1'
 WHERE store_id = 'a1b2c3d4-0001-4000-8000-000000000001'
   AND invite_code IS NULL;

UPDATE gibson_store
   SET invite_code = 'META01'
 WHERE store_id = 'a1b2c3d4-0002-4000-8000-000000000002'
   AND invite_code IS NULL;

-- Any other stores without a code get a random one
UPDATE gibson_store
   SET invite_code = upper(substring(md5(random()::text || store_id::text), 1, 6))
 WHERE invite_code IS NULL;

-- ─── Store Membership ────────────────────────────────────────

CREATE TABLE IF NOT EXISTS gibson_store_member (
    store_id   UUID NOT NULL REFERENCES gibson_store(store_id) ON DELETE CASCADE,
    user_id    TEXT NOT NULL,   -- Supabase auth.users id (UUID as text)
    role       TEXT NOT NULL DEFAULT 'employee'
                   CHECK (role IN ('owner', 'admin', 'employee')),
    status     TEXT NOT NULL DEFAULT 'active'
                   CHECK (status IN ('active', 'suspended')),
    joined_at  TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (store_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_store_member_user ON gibson_store_member(user_id);
CREATE INDEX IF NOT EXISTS idx_store_member_store ON gibson_store_member(store_id);

-- ─── Store Join Requests ─────────────────────────────────────

CREATE TABLE IF NOT EXISTS gibson_store_join_request (
    request_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id    UUID NOT NULL REFERENCES gibson_store(store_id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL,   -- requesting user's Supabase ID
    user_email  TEXT NOT NULL,
    user_name   TEXT,
    message     TEXT,
    status      TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'denied')),
    reviewed_by TEXT,            -- user_id of the owner/admin who acted
    created_at  TIMESTAMPTZ DEFAULT now(),
    reviewed_at TIMESTAMPTZ,
    UNIQUE (store_id, user_id)   -- one active request per user per store
);

CREATE INDEX IF NOT EXISTS idx_join_request_store  ON gibson_store_join_request(store_id, status);
CREATE INDEX IF NOT EXISTS idx_join_request_user   ON gibson_store_join_request(user_id);

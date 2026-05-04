-- ═══════════════════════════════════════════════════════════════
-- Gibson Migration 007: Conversational Intelligence System
-- Ambient mode + Deep mode + Preparation cycle + Institutional memory
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS gibson_conversation (
    conversation_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID NOT NULL,
    mode              TEXT CHECK (mode IN ('ambient','deep')),
    started_at        TIMESTAMPTZ DEFAULT now(),
    ended_at          TIMESTAMPTZ,
    title             TEXT,
    summary           TEXT,
    topics            TEXT[] DEFAULT '{}',
    decisions         JSONB DEFAULT '[]',
    preparation_tasks JSONB DEFAULT '[]',
    full_transcript   JSONB NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS gibson_conversation_decision (
    decision_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES gibson_conversation(conversation_id),
    decision_text   TEXT NOT NULL,
    topic           TEXT,
    status          TEXT DEFAULT 'ACTIVE'
                    CHECK (status IN ('ACTIVE','SUPERSEDED','IMPLEMENTED')),
    superseded_by   UUID REFERENCES gibson_conversation_decision(decision_id),
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS gibson_preparation_task (
    task_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES gibson_conversation(conversation_id),
    subject         TEXT NOT NULL,
    subject_type    TEXT,
    scope           JSONB,
    status          TEXT DEFAULT 'QUEUED'
                    CHECK (status IN ('QUEUED','RUNNING','COMPLETE','FAILED')),
    queued_at       TIMESTAMPTZ DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    result_summary  TEXT,
    briefing_url    TEXT
);

-- Indexes for conversation system
CREATE INDEX IF NOT EXISTS idx_gibson_conversation_topics ON gibson_conversation USING gin(topics);
CREATE INDEX IF NOT EXISTS idx_gibson_conversation_user ON gibson_conversation(user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_gibson_decision_topic ON gibson_conversation_decision(topic, status);
CREATE INDEX IF NOT EXISTS idx_gibson_prep_task_status ON gibson_preparation_task(status, queued_at);

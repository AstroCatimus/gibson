-- Track whether an edition has been checked against Open Library.
-- NULL = never checked. Timestamp = last check.
ALTER TABLE gibson_edition
    ADD COLUMN IF NOT EXISTS ol_checked_at TIMESTAMPTZ;

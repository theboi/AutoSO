-- AutoSO transcripts table
-- Run in Supabase dashboard: SQL Editor after 001_initial_schema.sql

CREATE TABLE IF NOT EXISTS transcripts (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    url         TEXT        NOT NULL,
    title       TEXT        NOT NULL,
    transcript  TEXT        NOT NULL,
    language    TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transcripts_created_at
    ON transcripts (created_at DESC);

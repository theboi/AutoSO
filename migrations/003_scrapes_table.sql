-- AutoSO Phase 1X: scrapes cache table + analyses.scrape_id reference.
-- Run in Supabase dashboard: SQL Editor after 001_initial_schema.sql and 002_transcripts_table.sql.
-- This truncates all prior analyses/citations rows (Phase 1X has no backward compat).

TRUNCATE TABLE citations, analyses RESTART IDENTITY CASCADE;

CREATE TABLE IF NOT EXISTS scrapes (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    url        TEXT        NOT NULL,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    result     JSONB       NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scrapes_url_scraped_at
    ON scrapes (url, scraped_at DESC);

ALTER TABLE analyses
    ADD COLUMN IF NOT EXISTS scrape_id UUID REFERENCES scrapes(id);

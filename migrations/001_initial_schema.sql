-- AutoSO initial schema
-- Run in Supabase dashboard: SQL Editor

CREATE TABLE IF NOT EXISTS analyses (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url           TEXT        NOT NULL,
    mode          TEXT        NOT NULL CHECK (mode IN ('texture', 'bucket')),
    title         TEXT        NOT NULL,
    output        TEXT        NOT NULL,
    output_cited  TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS citations (
    id              UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID    NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    citation_number INTEGER NOT NULL,
    text            TEXT    NOT NULL,
    platform        TEXT    NOT NULL,
    comment_id      TEXT,
    position        INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_citations_run_id
    ON citations (run_id);

CREATE INDEX IF NOT EXISTS idx_analyses_created_at
    ON analyses (created_at DESC);

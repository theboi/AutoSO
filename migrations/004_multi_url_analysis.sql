-- Phase 1Y: multi-URL analyses.
-- Existing analyses rows are wiped (small DB, shape changed too much to backfill).

DO $$
BEGIN
    IF to_regclass('public.citations') IS NOT NULL
       AND to_regclass('public.analyses') IS NOT NULL THEN
        TRUNCATE TABLE citations, analyses RESTART IDENTITY CASCADE;
    END IF;
END $$;

ALTER TABLE IF EXISTS analyses
    DROP COLUMN IF EXISTS url;

ALTER TABLE IF EXISTS analyses
    ADD COLUMN IF NOT EXISTS analysis_mode TEXT NOT NULL DEFAULT 'prompt';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'analyses_analysis_mode_check'
    ) THEN
        ALTER TABLE analyses
            ADD CONSTRAINT analyses_analysis_mode_check
            CHECK (analysis_mode IN ('prompt', 'rag'));
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS analysis_sources (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID        NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    url         TEXT        NOT NULL,
    link_index  INTEGER     NOT NULL,
    scrape_id   UUID        REFERENCES scrapes(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_analysis_sources_analysis_id
    ON analysis_sources (analysis_id);

ALTER TABLE IF EXISTS citations
    ADD COLUMN IF NOT EXISTS source_id UUID REFERENCES analysis_sources(id);

ALTER TABLE IF EXISTS citations
    DROP COLUMN IF EXISTS platform;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'citations_run_citation_unique'
    ) THEN
        ALTER TABLE citations
            ADD CONSTRAINT citations_run_citation_unique
            UNIQUE (run_id, citation_number);
    END IF;
END $$;

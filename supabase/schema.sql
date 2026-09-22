-- Supabase schema for the live dashboard backend. Mirrors the 8 JSON
-- shapes the local Spark export (spark/export_dashboard_data.scala) and
-- the dashboard's TypeScript types (dashboard/lib/data.ts) already define
-- exactly — one table per export, not a general-purpose schema.
--
-- Design (confirmed with the user before implementing, see
-- docs/ARCHITECTURE.md's Application Layer section for the full report):
--   - Data volume is tiny (well under Supabase's 500MB free-tier cap —
--     confirmed at the time this schema was first written at 68KB across
--     7 exports; live_price_timeline grows slowly, one row per pair per
--     project per finalized hour, nowhere near the cap even after months).
--   - Full delete+insert (replace) per table on each push, matching the
--     existing export's "overwrite the whole file" semantics exactly — no
--     incremental/upsert complexity needed at this volume/frequency.
--   - Two key roles: `sb_secret_...` (bypasses RLS, used only by the local
--     push script, ingestion/push_to_supabase.py, never leaves that
--     machine's .env) writes; `sb_publishable_...` (respects RLS, used by
--     the Render backend) reads. The publishable key is safe to be
--     effectively public since RLS restricts it to SELECT only — the
--     Vercel frontend never holds any Supabase credential at all, it only
--     talks to the Render backend.
--
-- Run this once in the Supabase SQL Editor when setting up the project.

CREATE TABLE IF NOT EXISTS current_risk (
    pair             TEXT NOT NULL,
    project          TEXT NOT NULL,
    baseline_status  TEXT NOT NULL,
    risk_score       DOUBLE PRECISION NOT NULL,
    dt               TEXT NOT NULL,
    window_start_ts  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (pair, project)
);

CREATE TABLE IF NOT EXISTS current_risk_live (
    pair             TEXT NOT NULL,
    project          TEXT NOT NULL,
    risk_score       DOUBLE PRECISION NOT NULL,
    window_start_ts  TIMESTAMPTZ NOT NULL,
    source           TEXT NOT NULL,
    PRIMARY KEY (pair, project)
);

CREATE TABLE IF NOT EXISTS usdc_crisis_timeline (
    window_start_ts  TIMESTAMPTZ NOT NULL PRIMARY KEY,
    implied_price     DOUBLE PRECISION,
    volume_usd         DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS ust_crisis_timeline (
    window_start_ts  TIMESTAMPTZ NOT NULL PRIMARY KEY,
    implied_price     DOUBLE PRECISION,
    volume_usd         DOUBLE PRECISION
);

-- Unlike the two fixed historical timelines above (one row per hour, one
-- pair each), this covers multiple (pair, project) series that all grow
-- over time as the streaming consumer finalizes more hourly windows —
-- primary key reflects that.
CREATE TABLE IF NOT EXISTS live_price_timeline (
    pair             TEXT NOT NULL,
    project          TEXT NOT NULL,
    window_start_ts  TIMESTAMPTZ NOT NULL,
    implied_price    DOUBLE PRECISION,
    volume_usd       DOUBLE PRECISION,
    PRIMARY KEY (pair, project, window_start_ts)
);

CREATE TABLE IF NOT EXISTS classifier_metrics (
    direction         TEXT NOT NULL,
    scorer            TEXT NOT NULL,
    n_test            BIGINT NOT NULL,
    n_test_crisis     BIGINT NOT NULL,
    precision_crisis  DOUBLE PRECISION NOT NULL,
    recall_crisis     DOUBLE PRECISION NOT NULL,
    f1_crisis         DOUBLE PRECISION NOT NULL,
    pr_auc            DOUBLE PRECISION NOT NULL,
    threshold_used    DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (direction, scorer)
);

CREATE TABLE IF NOT EXISTS wallet_rankings (
    window_label         TEXT NOT NULL,
    node_id               TEXT NOT NULL,
    pagerank_score        DOUBLE PRECISION NOT NULL,
    rank_within_window    INT NOT NULL,
    is_contract           BOOLEAN NOT NULL,
    label                 TEXT,
    PRIMARY KEY (window_label, node_id)
);

-- Single-row table — simplest way to mirror metadata.json (one JSON
-- object, not an array of rows) without inventing a different shape.
CREATE TABLE IF NOT EXISTS metadata (
    id                  INT PRIMARY KEY DEFAULT 1,
    exported_at            TIMESTAMPTZ NOT NULL,
    dataset_end_usdc          TEXT NOT NULL,
    dataset_end_ust             TEXT NOT NULL,
    usdc_crisis_window            JSONB NOT NULL,
    ust_crisis_window                JSONB NOT NULL,
    CONSTRAINT single_row CHECK (id = 1)
);

-- Row Level Security: enabled on every table (a table without RLS is
-- accessible to anyone with the project URL and publishable key, full
-- stop) with exactly one SELECT-only policy each — the publishable key
-- used by the Render backend can read, never write. The secret key used
-- by the local push script bypasses RLS entirely, so it needs no policy.
-- ALTER TABLE ... ENABLE ROW LEVEL SECURITY is itself idempotent (a no-op
-- if already enabled), but CREATE POLICY has no IF NOT EXISTS form in
-- Postgres — confirmed the hard way: re-running this whole file against
-- an already-set-up project failed with "policy already exists" on the
-- very first CREATE POLICY line, and because Supabase's SQL Editor runs a
-- pasted multi-statement script as one transaction, that single error
-- rolled back every statement in the run, including ones after it that
-- had never been applied before (e.g. a newly added table). DROP POLICY
-- IF EXISTS immediately before each CREATE POLICY makes the whole file
-- safe to run any number of times.
ALTER TABLE current_risk ENABLE ROW LEVEL SECURITY;
ALTER TABLE current_risk_live ENABLE ROW LEVEL SECURITY;
ALTER TABLE usdc_crisis_timeline ENABLE ROW LEVEL SECURITY;
ALTER TABLE ust_crisis_timeline ENABLE ROW LEVEL SECURITY;
ALTER TABLE live_price_timeline ENABLE ROW LEVEL SECURITY;
ALTER TABLE classifier_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE wallet_rankings ENABLE ROW LEVEL SECURITY;
ALTER TABLE metadata ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "public read" ON current_risk;
CREATE POLICY "public read" ON current_risk FOR SELECT USING (true);
DROP POLICY IF EXISTS "public read" ON current_risk_live;
CREATE POLICY "public read" ON current_risk_live FOR SELECT USING (true);
DROP POLICY IF EXISTS "public read" ON usdc_crisis_timeline;
CREATE POLICY "public read" ON usdc_crisis_timeline FOR SELECT USING (true);
DROP POLICY IF EXISTS "public read" ON ust_crisis_timeline;
CREATE POLICY "public read" ON ust_crisis_timeline FOR SELECT USING (true);
DROP POLICY IF EXISTS "public read" ON live_price_timeline;
CREATE POLICY "public read" ON live_price_timeline FOR SELECT USING (true);
DROP POLICY IF EXISTS "public read" ON classifier_metrics;
CREATE POLICY "public read" ON classifier_metrics FOR SELECT USING (true);
DROP POLICY IF EXISTS "public read" ON wallet_rankings;
CREATE POLICY "public read" ON wallet_rankings FOR SELECT USING (true);
DROP POLICY IF EXISTS "public read" ON metadata;
CREATE POLICY "public read" ON metadata FOR SELECT USING (true);

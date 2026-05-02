-- DUKES Chapter 6 — Renewable sources of energy (DESNZ).
-- Long/tidy rows loaded by pipeline/ingest/dukes_chapter6.py

CREATE TABLE IF NOT EXISTS stg_dukes_chapter6 (
    dukes_table   TEXT NOT NULL,
    period_year   INTEGER,
    period_label  TEXT,
    row_label     TEXT NOT NULL,
    column_label  TEXT,
    metric_name   TEXT NOT NULL,
    value         NUMERIC,
    unit          TEXT,
    source_file   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_stg_dukes_ch6_table_year
    ON stg_dukes_chapter6 (dukes_table, period_year);
CREATE INDEX IF NOT EXISTS idx_stg_dukes_ch6_metric
    ON stg_dukes_chapter6 (dukes_table, metric_name);

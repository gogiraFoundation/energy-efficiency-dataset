-- DUKES Chapter 1 — supplementary workbooks (aggregate balances, sales, etc.).
-- Long/tidy rows; same shape as stg_dukes_chapter6 for consistent querying.

CREATE TABLE IF NOT EXISTS stg_dukes_chapter1_sup (
    dukes_table   TEXT NOT NULL,
    period_year   INTEGER,
    period_label  TEXT,
    row_label     TEXT NOT NULL,
    column_label  TEXT,
    metric_name   TEXT NOT NULL,
    value         NUMERIC,
    unit          TEXT,
    source_file   TEXT NOT NULL,
    value_text    TEXT
);

-- Existing databases created before value_text (dashboard queries require same columns as ch4/ch5).
ALTER TABLE stg_dukes_chapter1_sup ADD COLUMN IF NOT EXISTS value_text TEXT;

CREATE INDEX IF NOT EXISTS idx_stg_dukes_ch1_sup_table_year
    ON stg_dukes_chapter1_sup (dukes_table, period_year);
CREATE INDEX IF NOT EXISTS idx_stg_dukes_ch1_sup_metric
    ON stg_dukes_chapter1_sup (dukes_table, metric_name);

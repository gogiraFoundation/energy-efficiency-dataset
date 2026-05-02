-- DUKES Chapter 5 — electricity (DESNZ / GOV.UK).
-- Long/tidy rows; same shape as stg_dukes_chapter1_sup / stg_dukes_chapter6.

CREATE TABLE IF NOT EXISTS stg_dukes_chapter5 (
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

CREATE INDEX IF NOT EXISTS idx_stg_dukes_ch5_table_year
    ON stg_dukes_chapter5 (dukes_table, period_year);
CREATE INDEX IF NOT EXISTS idx_stg_dukes_ch5_metric
    ON stg_dukes_chapter5 (dukes_table, metric_name);

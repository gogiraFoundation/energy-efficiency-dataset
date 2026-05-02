-- DUKES Chapter 4 — natural gas (DESNZ / GOV.UK).
-- Same layout as stg_dukes_chapter5.

CREATE TABLE IF NOT EXISTS stg_dukes_chapter4 (
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

CREATE INDEX IF NOT EXISTS idx_stg_dukes_ch4_table_year
    ON stg_dukes_chapter4 (dukes_table, period_year);
CREATE INDEX IF NOT EXISTS idx_stg_dukes_ch4_metric
    ON stg_dukes_chapter4 (dukes_table, metric_name);

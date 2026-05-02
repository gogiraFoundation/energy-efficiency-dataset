-- =============================================================================
-- raw_xlsx_scheme_metric — long-form policy / scheme administration statistics.
--
-- Covers queue lengths, voucher issuance, ECO/RHI/FIT-style monthly series, and
-- similar Ofgem portal workbooks that do not fit network or retail raw shapes.
-- Loaded by pipeline/ingest/load_xlsx.py (parsers scheme_metric_long,
-- scheme_period_supplier_matrix).
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw_xlsx_scheme_metric (
    raw_xlsx_id BIGSERIAL PRIMARY KEY,
    period_date DATE,
    period_label TEXT,
    year INT,
    quarter INT,
    month INT,
    scheme_key TEXT NOT NULL,
    entity TEXT,
    metric_name TEXT NOT NULL,
    value NUMERIC,
    unit TEXT,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT raw_xlsx_scheme_metric_natural_uniq
        UNIQUE NULLS NOT DISTINCT
        (source_file, period_label, scheme_key, entity, metric_name)
);

CREATE INDEX IF NOT EXISTS idx_raw_xlsx_scheme_metric_scheme
    ON raw_xlsx_scheme_metric (scheme_key, metric_name, year);

-- Policy / low-carbon scheme facts (administration queues, BUS vouchers, ECO
-- progress files loaded into raw_xlsx_scheme_metric).

CREATE TABLE IF NOT EXISTS core_fact_scheme_metric (
    scheme_metric_id BIGSERIAL PRIMARY KEY,
    period_date DATE,
    period_label TEXT,
    calendar_year INT,
    calendar_month INT,
    quarter INT,
    scheme_key TEXT NOT NULL,
    entity TEXT,
    metric_name TEXT NOT NULL,
    value NUMERIC,
    unit TEXT,
    source_file TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT core_fact_scheme_metric_uniq
        UNIQUE NULLS NOT DISTINCT
        (source_file, period_label, scheme_key, entity, metric_name)
);

CREATE INDEX IF NOT EXISTS idx_core_fact_scheme_metric_scheme
    ON core_fact_scheme_metric (scheme_key, metric_name, calendar_year);

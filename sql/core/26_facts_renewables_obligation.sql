-- Renewables Obligation (RO) facts from Ofgem portal / everviz extracts.

CREATE TABLE IF NOT EXISTS core_fact_renewables_obligation (
    renew_obligation_id BIGSERIAL PRIMARY KEY,
    date_id INTEGER REFERENCES core_dim_date(date_id),
    obligation_period TEXT,
    period_label TEXT,
    technology TEXT,
    metric_name TEXT NOT NULL,
    value NUMERIC,
    unit TEXT,
    source_file TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT core_fact_renewables_obligation_uniq
        UNIQUE NULLS NOT DISTINCT (obligation_period, period_label, technology, metric_name)
);

CREATE INDEX IF NOT EXISTS idx_core_fact_renewables_obligation_metric
    ON core_fact_renewables_obligation (metric_name, obligation_period);

-- =============================================================================
-- raw_xlsx_* tables for the ~60 Ofgem Data Portal retail xlsx files.
--
-- Three target shapes are produced by pipeline/ingest/load_xlsx.py from the
-- new RETAIL & CONSUMER registry entries:
--
--   raw_xlsx_supplier_metric    period x supplier matrix
--   raw_xlsx_retail_timeseries  period x fixed-dimension matrix
--   raw_xlsx_retail_snapshot    no period; category/aspect/component grain
--
-- All UNIQUE constraints use NULLS NOT DISTINCT so upserts stay idempotent
-- when an optional dimension is absent (mirrors sql/raw/05_create_raw_xlsx_tables.sql).
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw_xlsx_supplier_metric (
    raw_xlsx_id BIGSERIAL PRIMARY KEY,
    period_date DATE,
    period_label TEXT,
    year INT,
    quarter INT,
    supplier_name TEXT NOT NULL,
    segment TEXT,
    commodity TEXT,
    metric_name TEXT NOT NULL,
    value NUMERIC,
    unit TEXT,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT raw_xlsx_supplier_metric_natural_uniq
        UNIQUE NULLS NOT DISTINCT
        (source_file, period_label, supplier_name, segment, commodity, metric_name)
);

CREATE INDEX IF NOT EXISTS idx_raw_xlsx_supplier_metric_yc
    ON raw_xlsx_supplier_metric (year, supplier_name, metric_name);

CREATE TABLE IF NOT EXISTS raw_xlsx_retail_timeseries (
    raw_xlsx_id BIGSERIAL PRIMARY KEY,
    period_date DATE,
    period_label TEXT,
    year INT,
    quarter INT,
    commodity TEXT,
    payment_method TEXT,
    supplier_group TEXT,
    supplier_size TEXT,
    segment TEXT,
    tariff_type TEXT,
    component TEXT,
    metric_name TEXT NOT NULL,
    value NUMERIC,
    unit TEXT,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT raw_xlsx_retail_timeseries_natural_uniq
        UNIQUE NULLS NOT DISTINCT
        (source_file, period_label, commodity, payment_method, supplier_group,
         supplier_size, segment, tariff_type, component, metric_name)
);

CREATE INDEX IF NOT EXISTS idx_raw_xlsx_retail_timeseries_period
    ON raw_xlsx_retail_timeseries (year, commodity, metric_name);

CREATE TABLE IF NOT EXISTS raw_xlsx_retail_snapshot (
    raw_xlsx_id BIGSERIAL PRIMARY KEY,
    year INT,
    category TEXT,
    supplier_name TEXT,
    segment TEXT,
    commodity TEXT,
    payment_method TEXT,
    supplier_size TEXT,
    aspect TEXT,
    component TEXT,
    tariff_type TEXT,
    metric_name TEXT NOT NULL,
    value NUMERIC,
    unit TEXT,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT raw_xlsx_retail_snapshot_natural_uniq
        UNIQUE NULLS NOT DISTINCT
        (source_file, year, category, supplier_name, segment, commodity,
         payment_method, supplier_size, aspect, component, tariff_type, metric_name)
);

CREATE INDEX IF NOT EXISTS idx_raw_xlsx_retail_snapshot_yc
    ON raw_xlsx_retail_snapshot (year, supplier_name, metric_name);

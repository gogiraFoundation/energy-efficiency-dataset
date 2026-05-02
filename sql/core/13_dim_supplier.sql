-- =============================================================================
-- Retail dimensions: supplier, payment method, supplier size band.
--
-- core_dim_supplier is alias-resolved from metadata/supplier_mapping.csv loaded
-- into stg_supplier_alias by pipeline/ingest/load_xlsx.py.  Unmatched supplier
-- names from the raw layer are also inserted with supplier_size = 'unknown' so
-- nothing is silently dropped.
-- =============================================================================

CREATE TABLE IF NOT EXISTS core_dim_supplier (
    supplier_id BIGSERIAL PRIMARY KEY,
    supplier_name TEXT UNIQUE NOT NULL,
    supplier_group TEXT,
    supplier_size TEXT,
    ofgem_supplier_id TEXT,
    exited_quarter TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_core_dim_supplier_size ON core_dim_supplier (supplier_size);
CREATE INDEX IF NOT EXISTS idx_core_dim_supplier_group ON core_dim_supplier (supplier_group);

CREATE TABLE IF NOT EXISTS core_dim_payment_method (
    payment_method_id BIGSERIAL PRIMARY KEY,
    payment_method TEXT UNIQUE NOT NULL,
    is_prepayment BOOLEAN DEFAULT FALSE,
    description TEXT
);

INSERT INTO core_dim_payment_method (payment_method, is_prepayment, description)
VALUES
    ('direct_debit',       FALSE, 'Monthly direct debit'),
    ('standard_credit',    FALSE, 'Standard credit / pay on receipt of bill'),
    ('prepayment',         TRUE,  'Traditional prepayment meter'),
    ('smart_prepayment',   TRUE,  'Smart prepayment (smart-PPM)'),
    ('dual_fuel_typical',  FALSE, 'Typical dual-fuel customer (composite)'),
    ('unknown',            FALSE, 'Payment method not specified by source')
ON CONFLICT (payment_method) DO UPDATE
    SET is_prepayment = EXCLUDED.is_prepayment,
        description   = EXCLUDED.description;

CREATE TABLE IF NOT EXISTS core_dim_supplier_size (
    supplier_size_id BIGSERIAL PRIMARY KEY,
    size_band TEXT UNIQUE NOT NULL,
    description TEXT
);

INSERT INTO core_dim_supplier_size (size_band, description)
VALUES
    ('large',        'Large suppliers (>250k domestic accounts; large legacy + scaled new entrants)'),
    ('large_legacy', 'Six legacy suppliers: British Gas, EDF, E.ON, nPower, ScottishPower, SSE'),
    ('medium',       'Medium suppliers (50k-250k accounts)'),
    ('small',        'Small suppliers (<50k accounts)'),
    ('all',          'All suppliers / overall market'),
    ('aggregate',    'Aggregate / segment-level (no supplier identity)'),
    ('unknown',      'Size band not provided by source')
ON CONFLICT (size_band) DO UPDATE SET description = EXCLUDED.description;

-- =============================================================================
-- Seed core_dim_supplier from the alias mapping CSV.
-- Defensive: ensure stg_supplier_alias exists even if the xlsx step skipped it.
-- =============================================================================

CREATE TABLE IF NOT EXISTS stg_supplier_alias (
    source_supplier_name TEXT,
    supplier_name        TEXT,
    supplier_group       TEXT,
    supplier_size        TEXT,
    ofgem_supplier_id    TEXT,
    exited_quarter       TEXT
);

INSERT INTO core_dim_supplier (supplier_name, supplier_group, supplier_size, ofgem_supplier_id, exited_quarter)
SELECT DISTINCT ON (supplier_name)
    supplier_name,
    supplier_group,
    supplier_size,
    ofgem_supplier_id,
    NULLIF(exited_quarter, '')
FROM stg_supplier_alias
WHERE supplier_name IS NOT NULL
ORDER BY supplier_name
ON CONFLICT (supplier_name) DO UPDATE
    SET supplier_group     = COALESCE(EXCLUDED.supplier_group, core_dim_supplier.supplier_group),
        supplier_size      = COALESCE(EXCLUDED.supplier_size, core_dim_supplier.supplier_size),
        ofgem_supplier_id  = COALESCE(EXCLUDED.ofgem_supplier_id, core_dim_supplier.ofgem_supplier_id),
        exited_quarter     = COALESCE(EXCLUDED.exited_quarter, core_dim_supplier.exited_quarter);

-- Catch-all for supplier names appearing in the raw layer that are not yet in
-- the alias CSV.  They land with supplier_size = 'unknown' so analytics queries
-- can surface them via core_dim_supplier filtering.
CREATE TABLE IF NOT EXISTS raw_xlsx_supplier_metric (
    raw_xlsx_id BIGSERIAL PRIMARY KEY,
    period_date DATE,
    period_label TEXT,
    year INT,
    quarter INT,
    supplier_name TEXT,
    segment TEXT,
    commodity TEXT,
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT,
    loaded_at TIMESTAMPTZ DEFAULT now()
);
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
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT,
    loaded_at TIMESTAMPTZ DEFAULT now()
);

INSERT INTO core_dim_supplier (supplier_name, supplier_group, supplier_size)
SELECT DISTINCT
    s.supplier_name,
    NULL::text AS supplier_group,
    'unknown'  AS supplier_size
FROM (
    SELECT supplier_name FROM raw_xlsx_supplier_metric WHERE supplier_name IS NOT NULL
    UNION
    SELECT supplier_name FROM raw_xlsx_retail_snapshot WHERE supplier_name IS NOT NULL
) s
WHERE s.supplier_name <> ''
ON CONFLICT (supplier_name) DO NOTHING;

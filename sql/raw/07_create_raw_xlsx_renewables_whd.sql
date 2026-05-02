-- =============================================================================
-- raw_xlsx_renewables and raw_xlsx_whd
--
-- Loaded by pipeline/ingest/load_xlsx.py via the new "tech_period_matrix" and
-- "whd_scheme_year_matrix" parsers, registered in metadata/xlsx_registry.yaml.
--
-- Both tables follow the existing raw_xlsx_* convention: NULLS NOT DISTINCT
-- unique constraints so MERGE upserts stay idempotent even when an optional
-- dimension (region, installation_type, supplier_name, obligation_method) is
-- null for a GB / aggregate row.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Renewables (MCS-style deployment): annual or quarterly TIC and installation
-- counts by technology, optionally split by region or installation type.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_xlsx_renewables (
    raw_xlsx_id BIGSERIAL PRIMARY KEY,
    period_date DATE,             -- end-of-quarter for quarterly, end-of-year for annual
    period_label TEXT,            -- e.g. "2023" or "2023 Q3"
    year INT,
    quarter INT,                  -- NULL for annual rows
    technology TEXT,              -- Solar PV, Wind, Hydro, Biomass, ...
    region TEXT,                  -- NULL for GB total
    installation_type TEXT,       -- NULL when not split (domestic / non-domestic / ...)
    metric_name TEXT,             -- capacity_kw | installations | share_pct
    value NUMERIC,
    unit TEXT,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT raw_xlsx_renewables_natural_uniq
        UNIQUE NULLS NOT DISTINCT
        (source_file, period_label, technology, region, installation_type, metric_name)
);

CREATE INDEX IF NOT EXISTS idx_raw_xlsx_renewables_yt
    ON raw_xlsx_renewables (year, technology);
CREATE INDEX IF NOT EXISTS idx_raw_xlsx_renewables_yqt
    ON raw_xlsx_renewables (year, quarter, technology);
CREATE INDEX IF NOT EXISTS idx_raw_xlsx_renewables_region
    ON raw_xlsx_renewables (year, region, technology);

-- -----------------------------------------------------------------------------
-- Warm Home Discount (WHD): scheme-year level series (national distribution,
-- scheme value), optional supplier/obligation-method splits.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_xlsx_whd (
    raw_xlsx_id BIGSERIAL PRIMARY KEY,
    scheme_year INT,              -- 1..N (Ofgem scheme year)
    calendar_year INT,            -- April-March mapped to the trailing calendar year
    nation TEXT,                  -- "England and Wales" | "Scotland" | "GB"
    supplier_name TEXT,           -- NULL for aggregates
    obligation_method TEXT,       -- "core rebate" | "industry initiatives" | NULL
    metric_name TEXT,             -- expenditure_pct | scheme_value_mgbp | obligation_amount_mgbp | redistributed_mgbp
    value NUMERIC,
    unit TEXT,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT raw_xlsx_whd_natural_uniq
        UNIQUE NULLS NOT DISTINCT
        (source_file, scheme_year, nation, supplier_name, obligation_method, metric_name)
);

CREATE INDEX IF NOT EXISTS idx_raw_xlsx_whd_year
    ON raw_xlsx_whd (calendar_year, nation);
CREATE INDEX IF NOT EXISTS idx_raw_xlsx_whd_supplier
    ON raw_xlsx_whd (calendar_year, supplier_name);

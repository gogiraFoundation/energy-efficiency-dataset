-- =============================================================================
-- Staging tables for Warm Home Discount (WHD).
--
-- Reads from raw_xlsx_whd (loaded by pipeline/ingest/load_xlsx.py via the
-- WHD section of metadata/xlsx_registry.yaml).  Splits into two staging
-- tables matching the natural grains of the public WHD workbooks:
--
--   stg_whd_scheme_year : (scheme_year, calendar_year, nation, metric_name)
--                         covers expenditure_pct distribution and the
--                         national scheme_value_mgbp series.
--   stg_whd_obligation  : (scheme_year, calendar_year, supplier_name,
--                         obligation_method, metric_name) covers supplier
--                         obligations and redistribution.
--
-- TRUNCATE-and-rebuild on each staging run.
-- =============================================================================

-- Defensive shell so staging runs cleanly even before any WHD xlsx is loaded.
CREATE TABLE IF NOT EXISTS raw_xlsx_whd (
    raw_xlsx_id BIGSERIAL PRIMARY KEY,
    scheme_year INT, calendar_year INT,
    nation TEXT, supplier_name TEXT, obligation_method TEXT,
    metric_name TEXT, value NUMERIC, unit TEXT,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ DEFAULT now()
);

DROP TABLE IF EXISTS stg_whd_scheme_year CASCADE;
DROP TABLE IF EXISTS stg_whd_obligation CASCADE;

-- -----------------------------------------------------------------------------
-- National scheme-year aggregates (supplier_name IS NULL, obligation_method IS NULL).
-- One row per (scheme_year, calendar_year, nation, metric_name).
-- -----------------------------------------------------------------------------

CREATE TABLE stg_whd_scheme_year AS
SELECT
    scheme_year,
    calendar_year,
    nation,
    metric_name,
    AVG(value)::numeric AS value,
    MAX(unit)           AS unit,
    MAX(source_file)    AS source_file
FROM raw_xlsx_whd
WHERE supplier_name IS NULL
  AND obligation_method IS NULL
  AND metric_name IN ('expenditure_pct', 'scheme_value_mgbp')
GROUP BY scheme_year, calendar_year, nation, metric_name;

CREATE INDEX IF NOT EXISTS idx_stg_whd_scheme_year_yn
    ON stg_whd_scheme_year (calendar_year, nation);

-- -----------------------------------------------------------------------------
-- Supplier-grain rows (supplier_name NOT NULL OR obligation_method NOT NULL).
-- One row per (scheme_year, calendar_year, supplier_name, obligation_method,
-- metric_name).
-- -----------------------------------------------------------------------------

CREATE TABLE stg_whd_obligation AS
SELECT
    scheme_year,
    calendar_year,
    supplier_name,
    obligation_method,
    metric_name,
    AVG(value)::numeric AS value,
    MAX(unit)           AS unit,
    MAX(source_file)    AS source_file
FROM raw_xlsx_whd
WHERE (supplier_name IS NOT NULL OR obligation_method IS NOT NULL)
  AND metric_name IN ('obligation_amount_mgbp', 'redistributed_mgbp')
GROUP BY scheme_year, calendar_year, supplier_name, obligation_method, metric_name;

CREATE INDEX IF NOT EXISTS idx_stg_whd_obligation_ys
    ON stg_whd_obligation (calendar_year, supplier_name);

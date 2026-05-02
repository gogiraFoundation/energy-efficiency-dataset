-- =============================================================================
-- Policy / scheme metric staging (Boiler Upgrade Scheme queues, ECO admin, etc.)
--
-- Requires raw_xlsx_scheme_metric from sql/raw/08_create_raw_xlsx_scheme_metric.sql
-- (applied when running the xlsx loader / full_refresh before staging).
-- =============================================================================

DROP TABLE IF EXISTS stg_scheme_metric CASCADE;

CREATE TABLE stg_scheme_metric AS
SELECT
    period_date,
    period_label,
    year,
    quarter,
    month,
    scheme_key,
    entity,
    metric_name,
    value,
    unit,
    source_file
FROM raw_xlsx_scheme_metric
WHERE value IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_stg_scheme_metric_key
    ON stg_scheme_metric (scheme_key, metric_name, year);

CREATE INDEX IF NOT EXISTS idx_stg_scheme_metric_period
    ON stg_scheme_metric (period_label, scheme_key);

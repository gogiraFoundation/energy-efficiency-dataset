-- Renewables Obligation + accreditation metrics sourced from everviz extracts
-- loaded into raw_xlsx_renewables by pipeline/ingest/load_ofgem_portal.py.

DROP TABLE IF EXISTS stg_renewables_obligation CASCADE;

CREATE TABLE stg_renewables_obligation AS
SELECT
    year,
    quarter,
    period_label,
    CASE
        WHEN metric_name = 'rocs_monthly_millions'
             AND position('|' IN COALESCE(period_label, '')) > 0
            THEN split_part(period_label, '|', 2)
        WHEN metric_name IN ('rocs_issued_millions', 'accredited_capacity_mw')
             AND period_label ~ '^\d{4}-\d{2}$'
            THEN period_label
        ELSE NULL
    END AS obligation_period,
    technology,
    metric_name,
    value,
    unit,
    source_file
FROM raw_xlsx_renewables
WHERE metric_name IN (
    'rocs_issued_millions',
    'rocs_monthly_millions',
    'accredited_capacity_mw',
    'accredited_stations_cumulative_all',
    'accredited_stations_cumulative_over50kw'
);

CREATE INDEX IF NOT EXISTS idx_stg_renewables_obligation_metric
    ON stg_renewables_obligation (metric_name, year);

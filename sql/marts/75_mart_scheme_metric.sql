-- mart_scheme_metric — passthrough of policy / scheme administration facts for
-- dashboards (queues, BUS vouchers, ECO progress, etc.).

DROP MATERIALIZED VIEW IF EXISTS mart_scheme_metric CASCADE;

CREATE MATERIALIZED VIEW mart_scheme_metric AS
SELECT
    scheme_metric_id,
    period_date,
    period_label,
    calendar_year,
    calendar_month,
    quarter,
    scheme_key,
    entity,
    metric_name,
    value,
    unit,
    source_file
FROM core_fact_scheme_metric;

CREATE INDEX IF NOT EXISTS idx_mart_scheme_metric_scheme
    ON mart_scheme_metric (scheme_key, metric_name, calendar_year);

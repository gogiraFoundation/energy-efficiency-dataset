-- mart_renewables_obligation
--
-- Obligation-period grain by technology: ROC issuance (millions) and accredited
-- capacity (MW) for comparison narratives.

DROP MATERIALIZED VIEW IF EXISTS mart_renewables_obligation CASCADE;

CREATE MATERIALIZED VIEW mart_renewables_obligation AS
SELECT
    obligation_period,
    technology,
    MAX(value) FILTER (WHERE metric_name = 'rocs_issued_millions')    AS rocs_issued_millions,
    MAX(value) FILTER (WHERE metric_name = 'accredited_capacity_mw')    AS accredited_capacity_mw,
    MIN(source_file) FILTER (WHERE metric_name = 'rocs_issued_millions') AS rocs_source_file,
    MIN(source_file) FILTER (WHERE metric_name = 'accredited_capacity_mw') AS capacity_source_file
FROM core_fact_renewables_obligation
WHERE obligation_period IS NOT NULL
  AND technology IS NOT NULL
GROUP BY obligation_period, technology;

CREATE INDEX IF NOT EXISTS idx_mart_renewables_obligation_period
    ON mart_renewables_obligation (obligation_period, technology);

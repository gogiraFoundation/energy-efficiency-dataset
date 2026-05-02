DROP MATERIALIZED VIEW IF EXISTS mart_daily_market_monitoring;
CREATE MATERIALIZED VIEW mart_daily_market_monitoring AS
WITH base AS (
    SELECT
        period_date,
        EXTRACT(year FROM period_date)::int AS year,
        commodity,
        source_name,
        metric_name,
        value
    FROM core_fact_daily_prices
    WHERE value IS NOT NULL
),
stats AS (
    SELECT
        year,
        commodity,
        source_name,
        metric_name,
        AVG(value) AS avg_value,
        STDDEV_POP(value) AS volatility_stddev,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY value) AS p95_value
    FROM base
    GROUP BY year, commodity, source_name, metric_name
)
SELECT
    b.year,
    b.commodity,
    b.source_name,
    b.metric_name,
    COUNT(*) AS observation_count,
    MIN(b.period_date) AS first_observation_date,
    MAX(b.period_date) AS last_observation_date,
    AVG(b.value) AS avg_daily_value,
    MIN(b.value) AS min_daily_value,
    MAX(b.value) AS max_daily_value,
    s.volatility_stddev,
    SUM(CASE WHEN b.value >= s.p95_value THEN 1 ELSE 0 END) AS spike_days_ge_p95
FROM base b
JOIN stats s
  ON s.year = b.year
 AND s.commodity = b.commodity
 AND s.source_name = b.source_name
 AND s.metric_name = b.metric_name
GROUP BY b.year, b.commodity, b.source_name, b.metric_name, s.volatility_stddev;

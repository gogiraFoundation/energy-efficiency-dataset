CREATE TABLE IF NOT EXISTS stg_daily_market_prices (
    period_date date,
    year int,
    commodity text,
    source_name text,
    metric_name text,
    value numeric,
    unit text
);

TRUNCATE TABLE stg_daily_market_prices;

INSERT INTO stg_daily_market_prices
SELECT
    (payload->>'date')::date AS period_date,
    EXTRACT(year FROM (payload->>'date')::date)::int AS year,
    lower(trim(payload->>'commodity')) AS commodity,
    lower(trim(COALESCE(payload->>'source_name', source_id))) AS source_name,
    lower(trim(payload->>'metric_name')) AS metric_name,
    (payload->>'value')::numeric AS value,
    nullif(payload->>'unit', '') AS unit
FROM raw.raw_daily_market_prices
WHERE payload ? 'date'
  AND payload ? 'commodity'
  AND payload ? 'metric_name'
  AND payload ? 'value';

CREATE UNIQUE INDEX IF NOT EXISTS idx_stg_daily_market_prices_uniq
    ON stg_daily_market_prices(period_date, commodity, source_name, metric_name);

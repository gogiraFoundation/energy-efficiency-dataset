-- Market staging tables.  Annual roll-ups of the time-series market files,
-- ready to be merged into core_fact_market_prices / core_fact_market_context.

-- Defensive shells for `staging` runs without prior `xlsx` load.
CREATE TABLE IF NOT EXISTS raw_xlsx_market_prices    (period_date DATE, period_label TEXT, year INT, commodity TEXT, instrument TEXT, metric_name TEXT, value NUMERIC, unit TEXT, source_file TEXT);
CREATE TABLE IF NOT EXISTS raw_xlsx_generation_mix   (period_date DATE, period_label TEXT, year INT, commodity TEXT, instrument TEXT, metric_name TEXT, value NUMERIC, unit TEXT, source_file TEXT);
CREATE TABLE IF NOT EXISTS raw_xlsx_gas_supply       (period_date DATE, period_label TEXT, year INT, commodity TEXT, instrument TEXT, metric_name TEXT, value NUMERIC, unit TEXT, source_file TEXT);
CREATE TABLE IF NOT EXISTS raw_xlsx_generation_share (year INT, company_name TEXT, metric_name TEXT, value NUMERIC, unit TEXT, source_file TEXT);

DROP TABLE IF EXISTS stg_market_prices CASCADE;
DROP TABLE IF EXISTS stg_market_context CASCADE;
DROP TABLE IF EXISTS stg_market_share CASCADE;

-- =============================================================================
-- stg_market_prices : annual avg by (commodity, instrument, metric)
-- =============================================================================

CREATE TABLE stg_market_prices (
    year INT,
    commodity TEXT,
    instrument TEXT,
    metric_name TEXT,
    period_label TEXT,
    avg_value NUMERIC,
    min_value NUMERIC,
    max_value NUMERIC,
    obs_count INT,
    unit TEXT
);

INSERT INTO stg_market_prices
SELECT
    year,
    commodity,
    instrument,
    metric_name,
    NULL::text AS period_label,
    AVG(value)  AS avg_value,
    MIN(value)  AS min_value,
    MAX(value)  AS max_value,
    COUNT(*)    AS obs_count,
    MAX(unit)   AS unit
FROM raw_xlsx_market_prices
WHERE year IS NOT NULL
GROUP BY year, commodity, instrument, metric_name;

CREATE UNIQUE INDEX IF NOT EXISTS idx_stg_market_prices_uniq
    ON stg_market_prices (year, commodity, instrument, metric_name);

-- =============================================================================
-- stg_market_context : annual fuel-mix shares from generation_mix +
-- aggregated gas supply by source.  The fuel column on raw_xlsx_generation_mix
-- is `instrument`; values are quarterly TWh, so summing four quarters gives an
-- annual TWh, and the per-fuel share is computed at mart time.
-- =============================================================================

CREATE TABLE stg_market_context (
    year INT,
    commodity TEXT,
    fuel_source TEXT,
    metric_name TEXT,
    value NUMERIC,
    unit TEXT
);

-- electricity generation: sum quarterly TWh per fuel
INSERT INTO stg_market_context
SELECT
    year,
    'electricity'         AS commodity,
    instrument            AS fuel_source,
    'generation_twh'      AS metric_name,
    SUM(value)            AS value,
    'TWh'                 AS unit
FROM raw_xlsx_generation_mix
WHERE year IS NOT NULL
GROUP BY year, instrument;

-- electricity total (computed later in core, but stage convenience row)
INSERT INTO stg_market_context
SELECT
    year,
    'electricity'             AS commodity,
    'TOTAL'                   AS fuel_source,
    'generation_total_twh'    AS metric_name,
    SUM(value)                AS value,
    'TWh'                     AS unit
FROM raw_xlsx_generation_mix
WHERE year IS NOT NULL
GROUP BY year;

-- gas supply: sum monthly mcm/d per source (mcm/d * days approximation skipped;
-- treat as raw monthly average aggregated to annual SUM for relative shares)
INSERT INTO stg_market_context
SELECT
    year,
    'gas'                AS commodity,
    instrument           AS fuel_source,
    'gas_supply_mcm_year_sum' AS metric_name,
    SUM(value)           AS value,
    'mcm_per_day_sum'    AS unit
FROM raw_xlsx_gas_supply
WHERE year IS NOT NULL
GROUP BY year, instrument;

INSERT INTO stg_market_context
SELECT
    year,
    'gas'                AS commodity,
    'TOTAL'              AS fuel_source,
    'gas_supply_total'   AS metric_name,
    SUM(value)           AS value,
    'mcm_per_day_sum'    AS unit
FROM raw_xlsx_gas_supply
WHERE year IS NOT NULL
GROUP BY year;

CREATE UNIQUE INDEX IF NOT EXISTS idx_stg_market_context_uniq
    ON stg_market_context (year, commodity, fuel_source, metric_name);

-- =============================================================================
-- stg_market_share : 2024 wholesale electricity share snapshot
-- =============================================================================

CREATE TABLE stg_market_share (
    year INT,
    commodity TEXT,
    company_name TEXT,
    share_pct NUMERIC,
    source_file TEXT
);

INSERT INTO stg_market_share
SELECT
    year,
    'electricity'        AS commodity,
    company_name,
    value                AS share_pct,
    source_file
FROM raw_xlsx_generation_share
WHERE metric_name = 'generation_market_share_pct';

CREATE UNIQUE INDEX IF NOT EXISTS idx_stg_market_share_uniq
    ON stg_market_share (year, commodity, company_name);

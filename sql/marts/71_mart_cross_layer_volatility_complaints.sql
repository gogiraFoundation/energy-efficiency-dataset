-- mart_cross_layer_volatility_complaints
--
-- Annual association view: wholesale volatility/spreads (from core_fact_market_prices,
-- commodity-explicit) vs GB market-level retail complaints, switching, and supplier exits.
--
-- Grain policy:
--   complaints: annual AVG across supplier-level observations (facts carry supplier_id; true GB
--     rollup rows are not present in every extract).
--   switching: supplier_size_id IS NULL for GB aggregate switching statistics where staged that way.
--   exits: supplier_exits metric where commodity is NULL or all/both/total (avoid summing gas+electric doubles).

DROP MATERIALIZED VIEW IF EXISTS mart_cross_layer_volatility_complaints CASCADE;

CREATE MATERIALIZED VIEW mart_cross_layer_volatility_complaints AS
WITH wholesale_year AS (
    SELECT
        year,
        -- Volatility workbook uses commodity = 'all' in xlsx_registry; match on metric_name only.
        AVG(value) FILTER (WHERE metric_name = 'volatility_electricity_baseload')
            AS elec_baseload_volatility,
        AVG(value) FILTER (WHERE metric_name = 'volatility_electricity_peakload')
            AS elec_peakload_volatility,
        AVG(value) FILTER (WHERE metric_name = 'volatility_gas')
            AS gas_volatility,
        AVG(value) FILTER (WHERE commodity = 'electricity' AND metric_name = 'spark_spread_central')
            AS spark_spread_avg,
        AVG(value) FILTER (WHERE commodity = 'electricity' AND metric_name = 'summer_winter_spread')
            AS summer_winter_spread_avg,
        AVG(value) FILTER (WHERE commodity = 'electricity' AND metric_name = 'power_price_baseload')
            AS power_baseload_avg,
        AVG(value) FILTER (WHERE commodity = 'gas' AND metric_name = 'gas_day_ahead_price')
            AS gas_day_ahead_avg,
        COUNT(*) FILTER (WHERE metric_name = 'volatility_electricity_baseload')
            AS wholesale_vol_obs_electricity,
        COUNT(*) FILTER (WHERE metric_name = 'volatility_gas')
            AS wholesale_vol_obs_gas
    FROM core_fact_market_prices
    GROUP BY year
),
complaints_year AS (
    SELECT
        d.year,
        AVG(cr.value) FILTER (WHERE cr.metric_name = 'complaints_received_per_100k')
            AS complaints_received_per_100k_avg,
        AVG(cr.value) FILTER (WHERE cr.metric_name = 'complaints_resolved_next_day_pct')
            AS resolved_next_day_avg_pct,
        AVG(cr.value) FILTER (WHERE cr.metric_name = 'complaints_resolved_8w_pct')
            AS resolved_8w_avg_pct,
        COUNT(*)::bigint AS complaints_obs_rows,
        COUNT(DISTINCT d.quarter) FILTER (WHERE d.quarter IS NOT NULL)::bigint AS complaints_distinct_quarters
    FROM core_fact_complaints_resolution cr
    JOIN core_dim_date d ON d.date_id = cr.date_id
    GROUP BY d.year
),
switching_year AS (
    SELECT
        d.year,
        SUM(sw.value) FILTER (WHERE sw.metric_name = 'total_switches') AS total_switches,
        AVG(sw.value) FILTER (WHERE sw.metric_name = 'avg_switching_time_days') AS avg_switching_time_days,
        COUNT(*)::bigint AS switching_obs_rows
    FROM core_fact_switching_activity sw
    JOIN core_dim_date d ON d.date_id = sw.date_id
    WHERE sw.supplier_size_id IS NULL
    GROUP BY d.year
),
exits_year AS (
    SELECT
        d.year,
        SUM(ms.value) AS supplier_exits,
        COUNT(*)::bigint AS exits_obs_rows
    FROM core_fact_market_structure ms
    JOIN core_dim_date d ON d.date_id = ms.date_id
    WHERE ms.metric_name = 'supplier_exits'
      AND (
          ms.commodity IS NULL
          OR lower(trim(ms.commodity)) IN ('all', 'both', 'total')
      )
    GROUP BY d.year
),
-- Years where both baseload-volatility and market complaints exist (intersection);
-- avoids output rows that cannot satisfy cross-layer completeness checks.
years AS (
    SELECT w.year
    FROM wholesale_year w
    INNER JOIN complaints_year c ON c.year = w.year
    WHERE w.elec_baseload_volatility IS NOT NULL
),
base AS (
    SELECT
        y.year,
        wy.elec_baseload_volatility,
        wy.elec_peakload_volatility,
        wy.gas_volatility,
        wy.spark_spread_avg,
        wy.summer_winter_spread_avg,
        wy.power_baseload_avg,
        wy.gas_day_ahead_avg,
        wy.wholesale_vol_obs_electricity,
        wy.wholesale_vol_obs_gas,
        (COALESCE(wy.wholesale_vol_obs_electricity, 0) = 0
            OR COALESCE(wy.wholesale_vol_obs_gas, 0) = 0) AS is_wholesale_low_confidence,
        cy.complaints_received_per_100k_avg,
        cy.resolved_next_day_avg_pct,
        cy.resolved_8w_avg_pct,
        cy.complaints_obs_rows,
        cy.complaints_distinct_quarters,
        sy.total_switches,
        sy.avg_switching_time_days,
        sy.switching_obs_rows,
        ey.supplier_exits,
        ey.exits_obs_rows,
        false AS is_retail_mixed_grain,
        (COALESCE(cy.complaints_obs_rows, 0) = 0 OR COALESCE(sy.switching_obs_rows, 0) = 0) AS is_retail_low_confidence,
        true AS is_contemporaneous_only
    FROM years y
    LEFT JOIN wholesale_year wy ON wy.year = y.year
    LEFT JOIN complaints_year cy ON cy.year = y.year
    LEFT JOIN switching_year sy ON sy.year = y.year
    LEFT JOIN exits_year ey ON ey.year = y.year
)
SELECT
    year,
    elec_baseload_volatility,
    elec_peakload_volatility,
    gas_volatility,
    spark_spread_avg,
    summer_winter_spread_avg,
    power_baseload_avg,
    gas_day_ahead_avg,
    LAG(elec_baseload_volatility) OVER (ORDER BY year) AS elec_baseload_volatility_lag1,
    LAG(gas_volatility) OVER (ORDER BY year) AS gas_volatility_lag1,
    LAG(spark_spread_avg) OVER (ORDER BY year) AS spark_spread_avg_lag1,
    complaints_received_per_100k_avg,
    resolved_next_day_avg_pct,
    resolved_8w_avg_pct,
    LAG(complaints_received_per_100k_avg) OVER (ORDER BY year) AS complaints_received_per_100k_lag1,
    total_switches,
    avg_switching_time_days,
    LAG(total_switches) OVER (ORDER BY year) AS total_switches_lag1,
    supplier_exits,
    LAG(supplier_exits) OVER (ORDER BY year) AS supplier_exits_lag1,
    wholesale_vol_obs_electricity,
    wholesale_vol_obs_gas,
    is_wholesale_low_confidence,
    complaints_obs_rows,
    complaints_distinct_quarters,
    switching_obs_rows,
    exits_obs_rows,
    is_retail_mixed_grain,
    is_retail_low_confidence,
    is_contemporaneous_only
FROM base
ORDER BY year;

CREATE INDEX IF NOT EXISTS idx_mart_cross_layer_volatility_complaints_year
    ON mart_cross_layer_volatility_complaints (year);

-- mart_cross_layer_cost_to_consumer
--
-- Annual GB view: YoY change in dual-fuel price-cap components vs wholesale baseload prices.
-- Wholesale levels come from core_fact_market_prices (commodity-explicit), not an AVG across
-- mart_market_context fuel-mix rows.

DROP MATERIALIZED VIEW IF EXISTS mart_cross_layer_cost_to_consumer CASCADE;

CREATE MATERIALIZED VIEW mart_cross_layer_cost_to_consumer AS
WITH cap_year AS (
    SELECT
        d.year,
        bb.component,
        AVG(bb.value) AS component_gbp
    FROM core_fact_bill_breakdown bb
    JOIN core_dim_date d ON d.date_id = bb.date_id
    JOIN core_dim_payment_method pm ON pm.payment_method_id = bb.payment_method_id
    WHERE bb.metric_name = 'price_cap_component_gbp'
      AND pm.payment_method = 'direct_debit'
    GROUP BY d.year, bb.component
),
cap_yearly_pivot AS (
    SELECT
        year,
        SUM(component_gbp) FILTER (WHERE component = 'wholesale')   AS wholesale_gbp,
        SUM(component_gbp) FILTER (WHERE component = 'network')         AS network_gbp,
        SUM(component_gbp) FILTER (WHERE component = 'policy')            AS policy_gbp,
        SUM(component_gbp) FILTER (WHERE component = 'operating')       AS operating_gbp,
        SUM(component_gbp) FILTER (WHERE component = 'vat')             AS vat_gbp,
        SUM(component_gbp) FILTER (WHERE component = 'ebit')            AS ebit_gbp,
        SUM(component_gbp) FILTER (WHERE component = 'total')           AS total_cap_gbp
    FROM cap_year
    GROUP BY year
),
wholesale_yr AS (
    SELECT
        year,
        AVG(value) FILTER (WHERE commodity = 'electricity' AND metric_name = 'power_price_baseload')
            AS power_baseload_avg,
        AVG(value) FILTER (WHERE commodity = 'gas' AND metric_name = 'gas_day_ahead_price')
            AS gas_day_ahead_avg,
        COUNT(*) FILTER (WHERE commodity = 'electricity' AND metric_name = 'power_price_baseload')
            AS wholesale_obs_electricity,
        COUNT(*) FILTER (WHERE commodity = 'gas' AND metric_name = 'gas_day_ahead_price')
            AS wholesale_obs_gas
    FROM core_fact_market_prices
    GROUP BY year
),
joined AS (
    SELECT
        p.year,
        p.wholesale_gbp,
        p.network_gbp,
        p.policy_gbp,
        p.operating_gbp,
        p.vat_gbp,
        p.ebit_gbp,
        p.total_cap_gbp,
        p.wholesale_gbp - LAG(p.wholesale_gbp) OVER (ORDER BY p.year) AS wholesale_yoy_change,
        p.network_gbp   - LAG(p.network_gbp)   OVER (ORDER BY p.year) AS network_yoy_change,
        p.policy_gbp    - LAG(p.policy_gbp)    OVER (ORDER BY p.year) AS policy_yoy_change,
        p.total_cap_gbp - LAG(p.total_cap_gbp) OVER (ORDER BY p.year) AS total_yoy_change,
        w.power_baseload_avg,
        w.gas_day_ahead_avg,
        w.wholesale_obs_electricity,
        w.wholesale_obs_gas,
        (COALESCE(w.wholesale_obs_electricity, 0) = 0 OR COALESCE(w.wholesale_obs_gas, 0) = 0)
            AS is_wholesale_low_confidence,
        true AS is_contemporaneous_only
    FROM cap_yearly_pivot p
    LEFT JOIN wholesale_yr w ON w.year = p.year
)
SELECT
    year,
    wholesale_gbp,
    network_gbp,
    policy_gbp,
    operating_gbp,
    vat_gbp,
    ebit_gbp,
    total_cap_gbp,
    wholesale_yoy_change,
    network_yoy_change,
    policy_yoy_change,
    total_yoy_change,
    power_baseload_avg,
    gas_day_ahead_avg,
    LAG(power_baseload_avg) OVER (ORDER BY year) AS power_baseload_avg_lag1,
    LAG(gas_day_ahead_avg) OVER (ORDER BY year) AS gas_day_ahead_avg_lag1,
    wholesale_obs_electricity,
    wholesale_obs_gas,
    is_wholesale_low_confidence,
    is_contemporaneous_only
FROM joined
ORDER BY year;

CREATE INDEX IF NOT EXISTS idx_mart_cross_layer_cost_to_consumer_year
    ON mart_cross_layer_cost_to_consumer (year);

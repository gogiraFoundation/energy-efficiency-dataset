-- mart_market_context
--
-- Annual GB wholesale market view that pairs the (year, commodity) price /
-- volume signals with the generation-mix shares and the 2024 market-share
-- snapshot.  Built directly from core_fact_market_prices, core_fact_market_context
-- and core_fact_market_share so it stays in sync with the typed market facts.
--
-- One row per (year, commodity, fuel_source) with annual aggregates.  The
-- 2024 wholesale share rows are appended with fuel_source = '2024_share'.

DROP MATERIALIZED VIEW IF EXISTS mart_market_context CASCADE;

CREATE MATERIALIZED VIEW mart_market_context AS
WITH gen_mix AS (
    SELECT
        ctx.year,
        ctx.commodity,
        ctx.fuel_source,
        ctx.value AS fuel_value,
        ctx.unit  AS fuel_unit,
        SUM(ctx.value) FILTER (WHERE ctx.fuel_source <> 'TOTAL') OVER (PARTITION BY ctx.year, ctx.commodity)
            AS commodity_total
    FROM core_fact_market_context ctx
    WHERE ctx.metric_name IN ('generation_twh','generation_total_twh','gas_supply_mcm_year_sum','gas_supply_total')
),
prices AS (
    SELECT
        year,
        commodity,
        AVG(value) FILTER (WHERE metric_name = 'gas_day_ahead_price') AS gas_day_ahead_avg_price,
        AVG(value) FILTER (WHERE metric_name = 'volatility_electricity_baseload') AS elec_baseload_volatility,
        AVG(value) FILTER (WHERE metric_name = 'volatility_electricity_peakload') AS elec_peakload_volatility,
        AVG(value) FILTER (WHERE metric_name = 'volatility_gas') AS gas_volatility,
        AVG(value) FILTER (WHERE metric_name = 'spark_spread_central') AS spark_spread_avg,
        AVG(value) FILTER (WHERE metric_name = 'dark_spread') AS dark_spread_avg,
        AVG(value) FILTER (WHERE metric_name = 'power_price_baseload') AS power_baseload_avg,
        AVG(value) FILTER (WHERE metric_name = 'bid_offer_spread') AS bid_offer_avg,
        AVG(value) FILTER (WHERE metric_name = 'summer_winter_spread') AS summer_winter_spread_avg
    FROM core_fact_market_prices
    GROUP BY year, commodity
),
trading AS (
    SELECT
        year,
        commodity,
        SUM(value) FILTER (WHERE metric_name = 'trading_volume_twh' AND instrument <> 'churn') AS trading_volume_total,
        AVG(value) FILTER (WHERE metric_name = 'trading_volume_twh' AND instrument = 'churn') AS churn_ratio_avg
    FROM core_fact_market_prices
    WHERE commodity IN ('electricity','gas')
    GROUP BY year, commodity
),
shares AS (
    SELECT year, commodity, company_name AS fuel_source,
           share_pct AS fuel_value, '%' AS fuel_unit
    FROM core_fact_market_share
)
SELECT
    g.year,
    g.commodity,
    g.fuel_source,
    g.fuel_value,
    g.fuel_unit,
    CASE WHEN g.fuel_source = 'TOTAL' OR g.commodity_total IS NULL OR g.commodity_total = 0
         THEN NULL
         ELSE g.fuel_value / g.commodity_total
    END AS fuel_share_of_total,
    p.gas_day_ahead_avg_price,
    p.elec_baseload_volatility,
    p.elec_peakload_volatility,
    p.gas_volatility,
    p.spark_spread_avg,
    p.dark_spread_avg,
    p.power_baseload_avg,
    p.bid_offer_avg,
    p.summer_winter_spread_avg,
    t.trading_volume_total,
    t.churn_ratio_avg,
    NULL::numeric AS market_share_pct_2024
FROM gen_mix g
LEFT JOIN prices  p ON p.year = g.year AND p.commodity = g.commodity
LEFT JOIN trading t ON t.year = g.year AND t.commodity = g.commodity

UNION ALL

SELECT
    s.year,
    s.commodity,
    s.fuel_source,
    NULL::numeric AS fuel_value,
    NULL::text    AS fuel_unit,
    NULL::numeric AS fuel_share_of_total,
    NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
    NULL, NULL,
    s.fuel_value AS market_share_pct_2024
FROM shares s;

CREATE INDEX IF NOT EXISTS idx_mart_market_context_year_commodity
    ON mart_market_context (year, commodity);

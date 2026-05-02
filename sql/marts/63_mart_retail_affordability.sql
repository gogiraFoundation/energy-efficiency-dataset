-- mart_retail_affordability
--
-- Tariff benchmarks, price-cap component breakdowns, and household energy
-- spend share.  Two grain layers:
--   * tariff_benchmarks_q  : (year, quarter, payment_method, supplier_group, tariff_type)
--   * household_spend_y    : (year, segment) annual share

DROP MATERIALIZED VIEW IF EXISTS mart_retail_affordability CASCADE;

CREATE MATERIALIZED VIEW mart_retail_affordability AS
WITH tariff AS (
    SELECT
        d.year, d.quarter, d.period_start_date,
        t.commodity, t.supplier_group,
        pm.payment_method,
        t.tariff_type,
        AVG(t.value) AS gbp_per_year
    FROM core_fact_tariff_benchmarks t
    JOIN core_dim_date d ON d.date_id = t.date_id
    LEFT JOIN core_dim_payment_method pm ON pm.payment_method_id = t.payment_method_id
    WHERE t.metric_name IN ('cheapest_tariff_gbp_per_year', 'tariff_price_gbp_per_year')
    GROUP BY d.year, d.quarter, d.period_start_date, t.commodity, t.supplier_group, pm.payment_method, t.tariff_type
),
cap_components AS (
    SELECT
        d.year, d.quarter, d.period_start_date, d.period_label,
        bb.commodity, bb.component,
        pm.payment_method,
        AVG(bb.value) AS component_value
    FROM core_fact_bill_breakdown bb
    JOIN core_dim_date d ON d.date_id = bb.date_id
    LEFT JOIN core_dim_payment_method pm ON pm.payment_method_id = bb.payment_method_id
    WHERE bb.metric_name = 'price_cap_component_gbp'
    GROUP BY d.year, d.quarter, d.period_start_date, d.period_label, bb.commodity, bb.component, pm.payment_method
),
household AS (
    SELECT d.year, hs.segment, hs.value_pct
    FROM core_fact_household_spend hs
    JOIN core_dim_date d ON d.date_id = hs.date_id
)
-- Long-format mart so all three layers can share filters in the dashboard.
SELECT
    'tariff' AS layer,
    t.year, t.quarter, t.period_start_date,
    NULL::text AS period_label,
    t.commodity, t.payment_method, t.supplier_group, t.tariff_type,
    NULL::text AS component,
    t.gbp_per_year     AS value,
    NULL::text AS segment,
    NULL::numeric AS value_pct
FROM tariff t
UNION ALL
SELECT
    'price_cap_component',
    c.year, c.quarter, c.period_start_date, c.period_label,
    c.commodity, c.payment_method, NULL::text, NULL::text,
    c.component, c.component_value, NULL::text, NULL::numeric
FROM cap_components c
UNION ALL
SELECT
    'household_spend',
    h.year, NULL, make_date(h.year, 1, 1), h.year::text || '-annual',
    NULL, NULL, NULL, NULL, NULL, NULL,
    h.segment, h.value_pct
FROM household h;

CREATE INDEX IF NOT EXISTS idx_mart_retail_affordability_layer
    ON mart_retail_affordability (layer, year);

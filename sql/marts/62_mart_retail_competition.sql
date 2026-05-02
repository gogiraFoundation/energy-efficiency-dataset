-- mart_retail_competition
--
-- Quarterly switching activity, internal/external switching rates, supplier
-- entries/exits, and number of active suppliers.  One row per (year, quarter,
-- commodity) where applicable.

DROP MATERIALIZED VIEW IF EXISTS mart_retail_competition CASCADE;

CREATE MATERIALIZED VIEW mart_retail_competition AS
WITH switching AS (
    SELECT
        d.year, d.quarter, d.period_start_date, sw.commodity,
        AVG(sw.value) FILTER (WHERE sw.metric_name = 'avg_switching_time_days')                AS avg_switching_time_days,
        SUM(sw.value) FILTER (WHERE sw.metric_name = 'total_switches')                         AS total_switches,
        SUM(sw.value) FILTER (WHERE sw.metric_name = 'switches_to_other_suppliers')            AS switches_to_other_suppliers,
        SUM(sw.value) FILTER (WHERE sw.metric_name = 'net_gains_other_suppliers')              AS net_gains_other_suppliers,
        AVG(sw.value) FILTER (WHERE sw.metric_name = 'switching_rate_internal_total_pct')      AS switching_rate_internal_total_pct,
        AVG(sw.value) FILTER (WHERE sw.metric_name = 'switching_rate_external_total_pct')      AS switching_rate_external_total_pct,
        AVG(sw.value) FILTER (WHERE sw.metric_name = 'switching_rate_internal_by_tariff_pct')  AS switching_rate_internal_by_tariff_pct
    FROM core_fact_switching_activity sw
    JOIN core_dim_date d ON d.date_id = sw.date_id
    GROUP BY d.year, d.quarter, d.period_start_date, sw.commodity
),
structure AS (
    SELECT
        d.year, d.quarter, ms.commodity,
        AVG(ms.value) FILTER (WHERE ms.metric_name = 'active_suppliers')   AS active_suppliers,
        SUM(ms.value) FILTER (WHERE ms.metric_name = 'supplier_entries')   AS supplier_entries,
        SUM(ms.value) FILTER (WHERE ms.metric_name = 'supplier_exits')     AS supplier_exits,
        AVG(ms.value) FILTER (WHERE ms.metric_name = 'continuing_active') AS continuing_active
    FROM core_fact_market_structure ms
    JOIN core_dim_date d ON d.date_id = ms.date_id
    GROUP BY d.year, d.quarter, ms.commodity
)
SELECT
    COALESCE(s.year, m.year)         AS year,
    COALESCE(s.quarter, m.quarter)   AS quarter,
    s.period_start_date,
    COALESCE(s.commodity, m.commodity) AS commodity,
    s.avg_switching_time_days,
    s.total_switches,
    s.switches_to_other_suppliers,
    s.net_gains_other_suppliers,
    s.switching_rate_internal_total_pct,
    s.switching_rate_external_total_pct,
    s.switching_rate_internal_by_tariff_pct,
    m.active_suppliers,
    m.supplier_entries,
    m.supplier_exits,
    m.continuing_active
FROM switching s
FULL OUTER JOIN structure m
    ON m.year = s.year
   AND COALESCE(m.quarter, -1) = COALESCE(s.quarter, -1)
   AND COALESCE(m.commodity, '__N__') = COALESCE(s.commodity, '__N__');

CREATE INDEX IF NOT EXISTS idx_mart_retail_competition_yc
    ON mart_retail_competition (year, quarter, commodity);

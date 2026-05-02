-- mart_cross_layer_supplier_quality
--
-- Per-supplier annual mart joining profit margin, complaint metrics and
-- satisfaction scores so the dashboard can answer:
--   "Do the more profitable suppliers also score higher on customer service?"
--
-- One row per (year, supplier_id).  Suppliers with no profit data still appear
-- if they have complaints / satisfaction data.

DROP MATERIALIZED VIEW IF EXISTS mart_cross_layer_supplier_quality CASCADE;

CREATE MATERIALIZED VIEW mart_cross_layer_supplier_quality AS
WITH financial AS (
    SELECT
        d.year,
        f.supplier_id,
        AVG(f.value) FILTER (WHERE f.metric_name = 'profit_million_gbp' AND f.segment = 'domestic')      AS domestic_profit_million_gbp,
        AVG(f.value) FILTER (WHERE f.metric_name = 'profit_million_gbp' AND f.segment = 'non_domestic')  AS non_domestic_profit_million_gbp,
        AVG(f.value) FILTER (WHERE f.metric_name = 'profit_million_gbp' AND f.segment = 'generation')    AS generation_profit_million_gbp,
        AVG(f.value) FILTER (WHERE f.metric_name = 'pretax_domestic_margin_pct')                          AS pretax_domestic_margin_pct
    FROM core_fact_supplier_financial f
    JOIN core_dim_date d ON d.date_id = f.date_id
    WHERE f.supplier_id IS NOT NULL
    GROUP BY d.year, f.supplier_id
),
complaints AS (
    SELECT
        d.year,
        cr.supplier_id,
        AVG(cr.value) FILTER (WHERE cr.metric_name = 'complaints_received_per_100k')   AS complaints_received_per_100k_avg,
        AVG(cr.value) FILTER (WHERE cr.metric_name = 'complaints_resolved_next_day_pct') AS resolved_next_day_avg_pct,
        AVG(cr.value) FILTER (WHERE cr.metric_name = 'complaints_resolved_8w_pct')       AS resolved_8w_avg_pct
    FROM core_fact_complaints_resolution cr
    JOIN core_dim_date d ON d.date_id = cr.date_id
    WHERE cr.supplier_id IS NOT NULL
    GROUP BY d.year, cr.supplier_id
),
satisfaction AS (
    SELECT
        d.year,
        sat.supplier_id,
        AVG(sat.value) FILTER (WHERE sat.metric_name = 'satisfaction_pct')          AS satisfaction_pct_avg,
        AVG(sat.value) FILTER (WHERE sat.metric_name = 'satisfaction_overall_pct')  AS satisfaction_overall_pct,
        AVG(sat.value) FILTER (WHERE sat.metric_name = 'nps_score')                 AS nps_score
    FROM core_fact_satisfaction_scores sat
    JOIN core_dim_date d ON d.date_id = sat.date_id
    WHERE sat.supplier_id IS NOT NULL
    GROUP BY d.year, sat.supplier_id
),
universe AS (
    SELECT year, supplier_id FROM financial
    UNION
    SELECT year, supplier_id FROM complaints
    UNION
    SELECT year, supplier_id FROM satisfaction
),
joined AS (
    SELECT
        u.year,
        u.supplier_id,
        s.supplier_name,
        s.supplier_group,
        s.supplier_size,
        f.domestic_profit_million_gbp,
        f.non_domestic_profit_million_gbp,
        f.generation_profit_million_gbp,
        f.pretax_domestic_margin_pct,
        c.complaints_received_per_100k_avg,
        c.resolved_next_day_avg_pct,
        c.resolved_8w_avg_pct,
        sat.satisfaction_pct_avg,
        sat.satisfaction_overall_pct,
        sat.nps_score
    FROM universe u
    LEFT JOIN core_dim_supplier s ON s.supplier_id = u.supplier_id
    LEFT JOIN financial f         ON f.year = u.year AND f.supplier_id = u.supplier_id
    LEFT JOIN complaints c        ON c.year = u.year AND c.supplier_id = u.supplier_id
    LEFT JOIN satisfaction sat    ON sat.year = u.year AND sat.supplier_id = u.supplier_id
)
SELECT
    year,
    supplier_id,
    supplier_name,
    supplier_group,
    supplier_size,
    domestic_profit_million_gbp,
    non_domestic_profit_million_gbp,
    generation_profit_million_gbp,
    pretax_domestic_margin_pct,
    complaints_received_per_100k_avg,
    resolved_next_day_avg_pct,
    resolved_8w_avg_pct,
    satisfaction_pct_avg,
    satisfaction_overall_pct,
    nps_score,
    LAG(pretax_domestic_margin_pct) OVER (PARTITION BY supplier_id ORDER BY year) AS pretax_domestic_margin_pct_lag1,
    LAG(complaints_received_per_100k_avg) OVER (PARTITION BY supplier_id ORDER BY year) AS complaints_received_per_100k_lag1,
    (domestic_profit_million_gbp IS NOT NULL) AS has_domestic_profit,
    (complaints_received_per_100k_avg IS NOT NULL
        OR resolved_next_day_avg_pct IS NOT NULL
        OR resolved_8w_avg_pct IS NOT NULL) AS has_complaints_metrics,
    (satisfaction_pct_avg IS NOT NULL
        OR satisfaction_overall_pct IS NOT NULL
        OR nps_score IS NOT NULL) AS has_satisfaction_metrics,
    (
        (CASE WHEN domestic_profit_million_gbp IS NOT NULL THEN 1 ELSE 0 END)
      + (CASE WHEN pretax_domestic_margin_pct IS NOT NULL THEN 1 ELSE 0 END)
      + (CASE WHEN complaints_received_per_100k_avg IS NOT NULL THEN 1 ELSE 0 END)
      + (CASE WHEN satisfaction_pct_avg IS NOT NULL OR nps_score IS NOT NULL THEN 1 ELSE 0 END)
    )::integer AS non_null_metric_count,
    true AS is_contemporaneous_only
FROM joined;

CREATE INDEX IF NOT EXISTS idx_mart_cross_layer_supplier_quality_supplier
    ON mart_cross_layer_supplier_quality (supplier_id, year);

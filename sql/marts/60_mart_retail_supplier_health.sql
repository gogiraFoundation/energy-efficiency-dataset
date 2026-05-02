-- mart_retail_supplier_health
--
-- Annual supplier financial profile + market-structure context. One row per
-- (year, supplier_id, segment, commodity) with segment='domestic' and commodity='all'
-- (rollup aligned to domestic profit facts); pretax domestic margin and annual
-- market-structure summaries. HHI is normalized to 0..1 (share_pct stored as 0..100 in facts).

DROP MATERIALIZED VIEW IF EXISTS mart_retail_supplier_health CASCADE;

CREATE MATERIALIZED VIEW mart_retail_supplier_health AS
WITH supplier_year AS (
    SELECT
        d.year,
        s.supplier_id,
        s.supplier_name,
        s.supplier_group,
        s.supplier_size,
        MAX(s.exited_quarter) AS exited_quarter,
        -- Sum profit across date_ids in the year (e.g. quarters) so market totals match additive reporting.
        SUM(f.value) FILTER (
            WHERE f.metric_name = 'profit_million_gbp'
              AND COALESCE(f.segment, 'domestic') = 'domestic'
        ) AS profit_million_gbp,
        AVG(f.value) FILTER (WHERE f.metric_name = 'pretax_domestic_margin_pct') AS pretax_margin_pct
    FROM core_fact_supplier_financial f
    JOIN core_dim_date d ON d.date_id = f.date_id
    LEFT JOIN core_dim_supplier s ON s.supplier_id = f.supplier_id
    GROUP BY d.year, s.supplier_id, s.supplier_name, s.supplier_group, s.supplier_size
),
structure AS (
    SELECT
        d.year,
        SUM(ms.value) FILTER (WHERE ms.metric_name = 'supplier_entries')      AS supplier_entries,
        SUM(ms.value) FILTER (WHERE ms.metric_name = 'supplier_exits')        AS supplier_exits,
        AVG(ms.value) FILTER (WHERE ms.metric_name = 'active_suppliers')      AS active_suppliers_avg,
        AVG(ms.value) FILTER (WHERE ms.metric_name = 'continuing_active')    AS continuing_active_avg
    FROM core_fact_market_structure ms
    JOIN core_dim_date d ON d.date_id = ms.date_id
    GROUP BY d.year
),
-- Mean of per-commodity HHI (electricity vs gas); not a dual-fuel single-market index.
hhi AS (
    SELECT
        year,
        AVG(hhi_by_commodity) AS hhi
    FROM (
        SELECT
            d.year,
            msr.commodity,
            SUM(POWER(msr.share_pct / 100.0, 2)) AS hhi_by_commodity
        FROM core_fact_market_share_retail msr
        JOIN core_dim_date d ON d.date_id = msr.date_id
        GROUP BY d.year, msr.commodity
    ) c
    GROUP BY year
)
SELECT
    sy.year,
    sy.supplier_id,
    sy.supplier_name,
    sy.supplier_group,
    sy.supplier_size,
    'domestic'::text AS segment,
    'all'::text AS commodity,
    sy.exited_quarter,
    sy.profit_million_gbp,
    sy.pretax_margin_pct,
    s.supplier_entries,
    s.supplier_exits,
    s.active_suppliers_avg,
    s.continuing_active_avg,
    h.hhi
FROM supplier_year sy
LEFT JOIN structure s ON s.year = sy.year
LEFT JOIN hhi h       ON h.year = sy.year;

CREATE INDEX IF NOT EXISTS idx_mart_retail_supplier_health_year
    ON mart_retail_supplier_health (year, supplier_name);

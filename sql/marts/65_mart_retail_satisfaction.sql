-- mart_retail_satisfaction
--
-- All satisfaction / NPS metrics in one long table.  Supports two grains:
--  * Quarterly satisfaction-by-aspect (no supplier).
--  * Annual snapshot satisfaction by supplier (Six large) or by supplier-size
--    band (NPS, overall satisfaction).

DROP MATERIALIZED VIEW IF EXISTS mart_retail_satisfaction CASCADE;

CREATE MATERIALIZED VIEW mart_retail_satisfaction AS
SELECT
    d.year,
    d.quarter,
    d.period_start_date,
    s.supplier_id,
    s.supplier_name,
    s.supplier_group,
    sz.size_band     AS supplier_size,
    sat.commodity,
    sat.aspect,
    sat.metric_name,
    sat.value,
    sat.unit,
    sat.source_file
FROM core_fact_satisfaction_scores sat
JOIN core_dim_date d                ON d.date_id = sat.date_id
LEFT JOIN core_dim_supplier s       ON s.supplier_id = sat.supplier_id
LEFT JOIN core_dim_supplier_size sz ON sz.supplier_size_id = sat.supplier_size_id;

CREATE INDEX IF NOT EXISTS idx_mart_retail_satisfaction_year
    ON mart_retail_satisfaction (year, metric_name);

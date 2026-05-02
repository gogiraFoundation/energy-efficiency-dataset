-- mart_retail_complaints
--
-- Quarterly complaints metrics by supplier and by supplier-size band.

DROP MATERIALIZED VIEW IF EXISTS mart_retail_complaints CASCADE;

CREATE MATERIALIZED VIEW mart_retail_complaints AS
SELECT
    d.year,
    d.quarter,
    d.period_start_date,
    s.supplier_id,
    s.supplier_name,
    s.supplier_group,
    s.supplier_size,
    sz.size_band       AS reported_size_band,
    cr.metric_name,
    cr.value,
    cr.unit,
    cr.source_file
FROM core_fact_complaints_resolution cr
JOIN core_dim_date d        ON d.date_id = cr.date_id
LEFT JOIN core_dim_supplier s      ON s.supplier_id = cr.supplier_id
LEFT JOIN core_dim_supplier_size sz ON sz.supplier_size_id = cr.supplier_size_id;

CREATE INDEX IF NOT EXISTS idx_mart_retail_complaints_supplier
    ON mart_retail_complaints (year, quarter, supplier_name);

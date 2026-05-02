-- Validation queries for deep-theme analytics fixes (run manually after refresh).
-- 1) mart_economic_impact: national ENS conservation
WITH src AS (
    SELECT d.year, SUM(COALESCE(nr.ens_mwh, 0)) AS ens_src
    FROM core_fact_network_reliability nr
    JOIN core_dim_date d ON d.date_id = nr.date_id
    GROUP BY d.year
),
mart AS (
    SELECT year, SUM(COALESCE(ens_mwh_in_region_industry, 0)) AS ens_mart
    FROM mart_economic_impact
    GROUP BY year
)
SELECT s.year, s.ens_src, m.ens_mart, (m.ens_mart - s.ens_src) AS diff
FROM src s
LEFT JOIN mart m USING (year)
ORDER BY s.year;

-- 2) mart_retail_consumer_vulnerability: no metric rows with null keys
SELECT COUNT(*) AS bad_rows
FROM mart_retail_consumer_vulnerability
WHERE (year IS NULL OR quarter IS NULL OR commodity IS NULL)
  AND (
      avg_debt_no_arrangement_gbp IS NOT NULL
      OR disconnections_for_debt IS NOT NULL
      OR smart_ppm_self_disconnect_events IS NOT NULL
  );

-- 3) mart_retail_supplier_health: at most one row per (year, supplier_id) when supplier_id not null
SELECT year, supplier_id, COUNT(*) AS n
FROM mart_retail_supplier_health
WHERE supplier_id IS NOT NULL
GROUP BY year, supplier_id
HAVING COUNT(*) > 1;

-- 4) core_fact_network_reliability duplicate keys (full grain)
SELECT date_id, geography_id, company_id, network_sector_id, COUNT(*) AS c
FROM core_fact_network_reliability
GROUP BY 1, 2, 3, 4
HAVING COUNT(*) > 1;

-- 5) Renewables: mart_renewables_deployment populates each grain.
--    (Rows are 0 only if the matching xlsx files have not been dropped in yet.)
SELECT
    grain,
    COUNT(*)                        AS row_count,
    COUNT(DISTINCT technology)      AS technologies,
    MIN(year) AS year_min, MAX(year) AS year_max
FROM mart_renewables_deployment
GROUP BY grain
ORDER BY grain;

-- 6) Warm Home Discount: each grain populates and supplier rows resolve to core_dim_supplier.
SELECT
    grain,
    COUNT(*)                                    AS row_count,
    COUNT(*) FILTER (WHERE supplier_id IS NULL) AS unresolved_supplier_rows,
    MIN(calendar_year) AS year_min, MAX(calendar_year) AS year_max
FROM mart_warm_home_discount
GROUP BY grain
ORDER BY grain;

-- 7) mart_retail_complaints: confirms both incident families round-trip from the
--    snapshot xlsx all the way to the mart. Expect at least one of each metric
--    to appear once Major_incidents.xlsx and Minor_incidents.xlsx are loaded.
SELECT
    metric_name,
    COUNT(*) AS rows
FROM mart_retail_complaints
WHERE metric_name IN (
    'minor_incidents_historical', 'minor_incidents_current',
    'major_incidents_historical', 'major_incidents_current'
)
GROUP BY metric_name
ORDER BY metric_name;

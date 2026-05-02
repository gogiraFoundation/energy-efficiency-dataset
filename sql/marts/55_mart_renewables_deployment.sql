-- mart_renewables_deployment
--
-- Materialized view summarising renewables (MCS-style) deployment from
-- stg_renewables_*.  Row-shapes are distinguished by `grain`:
--
--   grain = 'annual_gb'              : GB-wide annual capacity / installs (technology)
--   grain = 'quarterly_gb'           : GB quarterly net additions
--   grain = 'regional'               : region x technology (shares + capacity/installs)
--   grain = 'by_installation_type' : domestic / non-domestic / … × technology
--
-- The mart degrades gracefully: any CTE may be empty.

DROP MATERIALIZED VIEW IF EXISTS mart_renewables_deployment CASCADE;

CREATE MATERIALIZED VIEW mart_renewables_deployment AS
WITH annual AS (
    SELECT
        year,
        technology,
        MAX(value) FILTER (WHERE metric_name = 'capacity_kw')   AS capacity_kw,
        MAX(value) FILTER (WHERE metric_name = 'installations') AS installations
    FROM stg_renewables_capacity
    GROUP BY year, technology
),
annual_cum AS (
    SELECT
        year,
        technology,
        capacity_kw,
        installations,
        SUM(COALESCE(capacity_kw, 0)) OVER (
            PARTITION BY technology ORDER BY year
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_capacity_kw,
        SUM(COALESCE(installations, 0)) OVER (
            PARTITION BY technology ORDER BY year
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_installations
    FROM annual
),
quarterly AS (
    SELECT
        year,
        quarter,
        period_date,
        technology,
        MAX(value) FILTER (WHERE metric_name = 'capacity_kw')   AS capacity_kw_quarter,
        MAX(value) FILTER (WHERE metric_name = 'installations') AS installations_quarter
    FROM stg_renewables_quarterly
    GROUP BY year, quarter, period_date, technology
),
regional AS (
    SELECT
        year,
        region,
        technology,
        MAX(value) FILTER (WHERE metric_name = 'share_pct')     AS share_pct,
        MAX(value) FILTER (WHERE metric_name = 'capacity_kw')   AS capacity_kw,
        MAX(value) FILTER (WHERE metric_name = 'installations') AS installations
    FROM stg_renewables_regional
    GROUP BY year, region, technology
),
by_inst_annual AS (
    SELECT
        year,
        installation_type,
        technology,
        MAX(value) FILTER (WHERE metric_name = 'capacity_kw')   AS capacity_kw,
        MAX(value) FILTER (WHERE metric_name = 'installations') AS installations
    FROM stg_renewables_installation_type
    GROUP BY year, installation_type, technology
),
by_inst_cum AS (
    SELECT
        year,
        installation_type,
        technology,
        capacity_kw,
        installations,
        SUM(COALESCE(capacity_kw, 0)) OVER (
            PARTITION BY technology, installation_type ORDER BY year
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_capacity_kw,
        SUM(COALESCE(installations, 0)) OVER (
            PARTITION BY technology, installation_type ORDER BY year
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_installations
    FROM by_inst_annual
)
SELECT
    'annual_gb'::text  AS grain,
    year, NULL::int    AS quarter, NULL::date AS period_date,
    technology,
    NULL::text         AS region,
    NULL::text         AS installation_type,
    capacity_kw,
    installations,
    cumulative_capacity_kw,
    cumulative_installations,
    NULL::numeric      AS capacity_kw_quarter,
    NULL::numeric      AS installations_quarter,
    NULL::numeric      AS share_pct
FROM annual_cum
UNION ALL
SELECT
    'quarterly_gb'::text AS grain,
    year, quarter, period_date,
    technology, NULL::text AS region,
    NULL::text AS installation_type,
    NULL::numeric AS capacity_kw,
    NULL::numeric AS installations,
    NULL::numeric AS cumulative_capacity_kw,
    NULL::numeric AS cumulative_installations,
    capacity_kw_quarter,
    installations_quarter,
    NULL::numeric AS share_pct
FROM quarterly
UNION ALL
SELECT
    'regional'::text AS grain,
    year, NULL::int AS quarter, NULL::date AS period_date,
    technology, region,
    NULL::text AS installation_type,
    capacity_kw, installations,
    NULL::numeric AS cumulative_capacity_kw,
    NULL::numeric AS cumulative_installations,
    NULL::numeric AS capacity_kw_quarter,
    NULL::numeric AS installations_quarter,
    share_pct
FROM regional
UNION ALL
SELECT
    'by_installation_type'::text AS grain,
    year, NULL::int AS quarter, NULL::date AS period_date,
    technology,
    NULL::text AS region,
    installation_type::text,
    capacity_kw,
    installations,
    cumulative_capacity_kw,
    cumulative_installations,
    NULL::numeric AS capacity_kw_quarter,
    NULL::numeric AS installations_quarter,
    NULL::numeric AS share_pct
FROM by_inst_cum;

CREATE INDEX IF NOT EXISTS idx_mart_renewables_grain_year
    ON mart_renewables_deployment (grain, year, technology);

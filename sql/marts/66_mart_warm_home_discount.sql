-- mart_warm_home_discount
--
-- Materialized view summarising Warm Home Discount (WHD) data from
-- stg_whd_*.  Two row-shapes are returned, distinguished by `grain`:
--
--   grain = 'national'  : (scheme_year, calendar_year, nation, expenditure_pct,
--                          scheme_value_mgbp)
--                         from stg_whd_scheme_year.
--
--   grain = 'supplier'  : (scheme_year, calendar_year, supplier_id, supplier_name,
--                          supplier_group, supplier_size, obligation_method,
--                          obligation_amount_mgbp, redistributed_mgbp)
--                         from stg_whd_obligation, joined to core_dim_supplier
--                         where the supplier name resolves; raw supplier names
--                         that do not match are kept with supplier_id IS NULL.
--
-- The mart degrades gracefully: either CTE may be empty.

DROP MATERIALIZED VIEW IF EXISTS mart_warm_home_discount CASCADE;

CREATE MATERIALIZED VIEW mart_warm_home_discount AS
WITH national AS (
    SELECT
        scheme_year,
        calendar_year,
        nation,
        MAX(value) FILTER (WHERE metric_name = 'expenditure_pct')   AS expenditure_pct,
        MAX(value) FILTER (WHERE metric_name = 'scheme_value_mgbp') AS scheme_value_mgbp,
        MAX(source_file)                                            AS source_file
    FROM stg_whd_scheme_year
    GROUP BY scheme_year, calendar_year, nation
),
supplier AS (
    SELECT
        o.scheme_year,
        o.calendar_year,
        o.supplier_name,
        o.obligation_method,
        MAX(o.value) FILTER (WHERE o.metric_name = 'obligation_amount_mgbp') AS obligation_amount_mgbp,
        MAX(o.value) FILTER (WHERE o.metric_name = 'redistributed_mgbp')     AS redistributed_mgbp,
        MAX(o.source_file)                                                   AS source_file
    FROM stg_whd_obligation o
    GROUP BY o.scheme_year, o.calendar_year, o.supplier_name, o.obligation_method
)
SELECT
    'national'::text AS grain,
    scheme_year,
    calendar_year,
    nation,
    NULL::bigint        AS supplier_id,
    NULL::text          AS supplier_name,
    NULL::text          AS supplier_group,
    NULL::text          AS supplier_size,
    NULL::text          AS obligation_method,
    expenditure_pct,
    scheme_value_mgbp,
    NULL::numeric       AS obligation_amount_mgbp,
    NULL::numeric       AS redistributed_mgbp,
    source_file
FROM national
UNION ALL
SELECT
    'supplier'::text AS grain,
    s.scheme_year,
    s.calendar_year,
    NULL::text       AS nation,
    d.supplier_id,
    COALESCE(d.supplier_name, s.supplier_name) AS supplier_name,
    d.supplier_group,
    d.supplier_size,
    s.obligation_method,
    NULL::numeric    AS expenditure_pct,
    NULL::numeric    AS scheme_value_mgbp,
    s.obligation_amount_mgbp,
    s.redistributed_mgbp,
    s.source_file
FROM supplier s
LEFT JOIN core_dim_supplier d ON d.supplier_name = s.supplier_name;

CREATE INDEX IF NOT EXISTS idx_mart_whd_grain_year
    ON mart_warm_home_discount (grain, calendar_year);
CREATE INDEX IF NOT EXISTS idx_mart_whd_supplier
    ON mart_warm_home_discount (grain, supplier_name);

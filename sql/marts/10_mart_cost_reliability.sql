-- mart_cost_reliability
-- One row per (year, company, network sector) with the headline value-for-money
-- metrics required by the spec:
--   * ens_per_million_gbp_spend = ens_mwh / actual_totex_million_gbp
--   * reliability_rate          = 1 - ens_mwh / total_demand_mwh
--   * cost_efficiency_score     = (actual_totex / totex_allowance) /
--                                 (1 - reliability_rate)
--     (= cost-overspend ratio per loss-rate point; lower is better)
-- riio_scheme is exposed via a left join to core_dim_riio_period so analysts
-- can filter by control window (T1: 2014-2021, ED1: 2016-2023, GD1: 2014-2021).

DROP MATERIALIZED VIEW IF EXISTS mart_cost_reliability CASCADE;

CREATE MATERIALIZED VIEW mart_cost_reliability AS
WITH base AS (
    SELECT
        d.year,
        c.company_name,
        c.owner_group,
        ns.sector_name,
        ns.sector_code,
        ns.commodity,
        fp.actual_totex_million_gbp,
        fp.totex_allowance_million_gbp,
        fp.rore_pct,
        nr.ens_mwh,
        nr.total_demand_mwh,
        nr.minutes_lost,
        nr.customer_interruptions,
        CASE WHEN fp.actual_totex_million_gbp > 0 THEN nr.ens_mwh / fp.actual_totex_million_gbp END
            AS ens_per_million_gbp_spend,
        CASE WHEN nr.total_demand_mwh > 0 THEN 1 - (nr.ens_mwh / nr.total_demand_mwh) END
            AS reliability_rate
    FROM core_fact_network_reliability nr
    JOIN core_fact_financial_performance fp
        ON fp.date_id = nr.date_id
       AND fp.company_id = nr.company_id
       AND fp.network_sector_id = nr.network_sector_id
    JOIN core_dim_date d            ON d.date_id = nr.date_id
    JOIN core_dim_company c         ON c.company_id = nr.company_id
    JOIN core_dim_network_sector ns ON ns.network_sector_id = nr.network_sector_id
)
SELECT
    base.*,
    -- Cost-efficiency score: ratio of actual-to-allowance spend, scaled by the
    -- network's loss rate. NULL when ENS is zero (no losses) or when demand
    -- denominator is unavailable.
    CASE
        WHEN base.totex_allowance_million_gbp > 0
         AND base.ens_mwh IS NOT NULL
         AND base.ens_mwh > 0
         AND base.total_demand_mwh > 0
        THEN (base.actual_totex_million_gbp / base.totex_allowance_million_gbp)
             / (base.ens_mwh / base.total_demand_mwh)
    END AS cost_efficiency_score,
    rp.scheme AS riio_scheme,
    rp.start_year AS riio_start_year,
    rp.end_year   AS riio_end_year,
    -- Convenience helpers
    base.actual_totex_million_gbp - base.totex_allowance_million_gbp AS totex_variance_million_gbp,
    CASE WHEN base.totex_allowance_million_gbp > 0
         THEN base.actual_totex_million_gbp / base.totex_allowance_million_gbp
    END AS totex_actual_to_allowance_ratio
FROM base
LEFT JOIN core_dim_riio_period rp
    ON base.sector_name = ANY(rp.network_sectors)
   AND base.year BETWEEN rp.start_year AND rp.end_year;

CREATE INDEX IF NOT EXISTS idx_mart_cost_reliability_year_company
    ON mart_cost_reliability (year, company_name);
CREATE INDEX IF NOT EXISTS idx_mart_cost_reliability_scheme
    ON mart_cost_reliability (riio_scheme, year);

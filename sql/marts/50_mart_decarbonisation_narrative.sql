DROP MATERIALIZED VIEW IF EXISTS mart_decarbonisation_narrative;
CREATE MATERIALIZED VIEW mart_decarbonisation_narrative AS
SELECT
    d.year,
    SUM(COALESCE(nr.ens_mwh,0)) AS total_ens_mwh,
    AVG(CASE WHEN nr.total_demand_mwh > 0 THEN 1 - (nr.ens_mwh / nr.total_demand_mwh) END) AS avg_reliability_rate,
    l.lcree_turnover_million_gbp,
    l.lcree_turnover_million_gbp - LAG(l.lcree_turnover_million_gbp) OVER (ORDER BY d.year) AS lcree_turnover_change_million_gbp,
    SUM(COALESCE(nr.ens_mwh,0)) - LAG(SUM(COALESCE(nr.ens_mwh,0))) OVER (ORDER BY d.year) AS ens_change_mwh,
    'Narrative and correlation only. No causal inference.'::text AS interpretation_note
FROM core_fact_network_reliability nr
JOIN core_dim_date d ON d.date_id = nr.date_id
LEFT JOIN stg_lcree l ON l.year = d.year
GROUP BY d.year, l.lcree_turnover_million_gbp;

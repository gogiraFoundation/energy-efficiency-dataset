DROP MATERIALIZED VIEW IF EXISTS mart_regulatory_performance;
CREATE MATERIALIZED VIEW mart_regulatory_performance AS
SELECT
    d.year,
    c.company_name,
    ns.sector_name,
    fp.totex_allowance_million_gbp,
    fp.actual_totex_million_gbp,
    fp.actual_totex_million_gbp - fp.totex_allowance_million_gbp AS totex_variance_million_gbp,
    fp.rore_pct,
    cm.satisfaction_score,
    cm.cost_per_customer_gbp,
    e.sf6_kg,
    e.carbon_footprint_tco2e
FROM core_fact_financial_performance fp
JOIN core_dim_date d ON d.date_id = fp.date_id
JOIN core_dim_company c ON c.company_id = fp.company_id
JOIN core_dim_network_sector ns ON ns.network_sector_id = fp.network_sector_id
LEFT JOIN core_fact_customer_metrics cm ON cm.date_id = fp.date_id AND cm.company_id = fp.company_id AND cm.network_sector_id = fp.network_sector_id
LEFT JOIN core_fact_emissions e ON e.date_id = fp.date_id AND e.company_id = fp.company_id AND e.network_sector_id = fp.network_sector_id;

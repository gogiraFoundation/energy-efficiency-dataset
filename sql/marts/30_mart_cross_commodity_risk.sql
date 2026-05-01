DROP MATERIALIZED VIEW IF EXISTS mart_cross_commodity_risk;
CREATE MATERIALIZED VIEW mart_cross_commodity_risk AS
SELECT
    d.year,
    g.geography_name,
    ns.commodity,
    ns.sector_name,
    SUM(COALESCE(nr.ens_mwh,0)) AS ens_mwh,
    SUM(COALESCE(nr.gas_interruption_volume,0) + COALESCE(nr.gas_lost_volume,0)) AS gas_disruption_volume,
    AVG(CASE WHEN nr.total_demand_mwh > 0 THEN 1 - (nr.ens_mwh / nr.total_demand_mwh) END) AS avg_reliability_rate,
    AVG(CASE WHEN nr.total_gas_supply > 0 THEN nr.gas_interruption_volume / nr.total_gas_supply END) AS gas_vulnerability_index
FROM core_fact_network_reliability nr
JOIN core_dim_date d ON d.date_id = nr.date_id
JOIN core_dim_geography g ON g.geography_id = nr.geography_id
JOIN core_dim_network_sector ns ON ns.network_sector_id = nr.network_sector_id
GROUP BY d.year, g.geography_name, ns.commodity, ns.sector_name;

DROP MATERIALIZED VIEW IF EXISTS mart_economic_impact;
CREATE MATERIALIZED VIEW mart_economic_impact AS
WITH ens_region_industry AS (
    SELECT
        d.year,
        rg.geography_id,
        rg.industry_id,
        SUM(COALESCE(nr.ens_mwh,0)) * (
            rg.gva_million_gbp / NULLIF(SUM(rg.gva_million_gbp) OVER (PARTITION BY d.year, rg.geography_id), 0)
        ) AS ens_mwh_in_region_industry,
        rg.gva_million_gbp,
        ei.kwh_per_gva,
        ei.electricity_pct_of_total_energy,
        ei.energy_intensity_index,
        COUNT(*) OVER (PARTITION BY d.year, rg.industry_id) AS ens_frequency
    FROM core_fact_network_reliability nr
    JOIN core_dim_date d ON d.date_id = nr.date_id
    JOIN core_fact_regional_gva rg ON rg.date_id = nr.date_id
    LEFT JOIN core_fact_energy_intensity ei ON ei.date_id = nr.date_id AND ei.industry_id = rg.industry_id
    GROUP BY d.year, rg.geography_id, rg.industry_id, rg.gva_million_gbp, ei.kwh_per_gva, ei.electricity_pct_of_total_energy, ei.energy_intensity_index
)
SELECT
    eri.year,
    g.geography_code,
    g.geography_name,
    i.sic_code,
    i.industry_name,
    eri.ens_mwh_in_region_industry,
    eri.gva_million_gbp,
    eri.kwh_per_gva,
    (eri.gva_million_gbp * 1000000) / NULLIF(eri.kwh_per_gva,0) AS industry_gva_per_mwh_weighted,
    eri.ens_mwh_in_region_industry * ((eri.gva_million_gbp * 1000000) / NULLIF(eri.kwh_per_gva,0)) AS output_at_risk_gbp,
    COALESCE(eri.electricity_pct_of_total_energy, 0) * COALESCE(eri.energy_intensity_index, 0) * COALESCE(eri.ens_frequency, 0) AS sector_exposure_score
FROM ens_region_industry eri
JOIN core_dim_geography g ON g.geography_id = eri.geography_id
JOIN core_dim_industry i ON i.industry_id = eri.industry_id;

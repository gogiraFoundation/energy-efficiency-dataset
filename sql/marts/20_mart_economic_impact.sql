-- mart_economic_impact
--
-- Regional industry exposure to network ENS, with national ENS conserved:
-- yearly SUM(ens_mwh) is computed once, then allocated to each (geography, industry)
-- row in proportion to that row's share of total national GVA for the same year.
-- sector_exposure_score is a structural intensity proxy (not outage frequency).

DROP MATERIALIZED VIEW IF EXISTS mart_economic_impact;
CREATE MATERIALIZED VIEW mart_economic_impact AS
WITH ens_year AS (
    SELECT
        d.year,
        SUM(COALESCE(nr.ens_mwh, 0)) AS ens_mwh_year_national
    FROM core_fact_network_reliability nr
    JOIN core_dim_date d ON d.date_id = nr.date_id
    GROUP BY d.year
),
gva_base AS (
    SELECT
        d.year,
        rg.date_id,
        rg.geography_id,
        rg.industry_id,
        rg.gva_million_gbp,
        SUM(rg.gva_million_gbp) OVER (PARTITION BY d.year) AS gva_year_total_national
    FROM core_fact_regional_gva rg
    JOIN core_dim_date d ON d.date_id = rg.date_id
),
io_agg AS (
    SELECT
        date_id,
        industry_id,
        MAX(intermediate_consumption_share) AS intermediate_consumption_share
    FROM core_fact_input_output
    WHERE commodity IN ('energy', 'electricity', 'gas', 'total_intermediate')
    GROUP BY date_id, industry_id
),
ens_region_industry AS (
    SELECT
        gb.year,
        gb.geography_id,
        gb.industry_id,
        ey.ens_mwh_year_national
            * (gb.gva_million_gbp / NULLIF(gb.gva_year_total_national, 0)) AS ens_mwh_in_region_industry,
        gb.gva_million_gbp,
        gb.gva_million_gbp / NULLIF(gb.gva_year_total_national, 0) AS gva_share_of_national,
        ey.ens_mwh_year_national,
        'national_gva_share_v1'::text AS allocation_method,
        ei.kwh_per_gva,
        ei.electricity_pct_of_total_energy,
        ei.energy_intensity_index,
        io.intermediate_consumption_share
    FROM gva_base gb
    LEFT JOIN ens_year ey ON ey.year = gb.year
    LEFT JOIN core_fact_energy_intensity ei
        ON ei.date_id = gb.date_id AND ei.industry_id = gb.industry_id
    LEFT JOIN io_agg io ON io.date_id = gb.date_id AND io.industry_id = gb.industry_id
)
SELECT
    eri.year,
    g.geography_code,
    g.geography_name,
    i.sic_code,
    i.industry_name,
    eri.ens_mwh_in_region_industry,
    eri.ens_mwh_year_national,
    eri.gva_share_of_national,
    eri.allocation_method,
    eri.gva_million_gbp,
    eri.kwh_per_gva,
    eri.intermediate_consumption_share,
    (eri.gva_million_gbp * 1000000) / NULLIF(eri.kwh_per_gva, 0) AS industry_gva_per_mwh_weighted,
    eri.ens_mwh_in_region_industry
        * ((eri.gva_million_gbp * 1000000) / NULLIF(eri.kwh_per_gva, 0))
        * COALESCE(eri.intermediate_consumption_share, 1.0) AS output_at_risk_gbp,
    COALESCE(eri.electricity_pct_of_total_energy, 0) * COALESCE(eri.energy_intensity_index, 0) AS sector_exposure_score
FROM ens_region_industry eri
JOIN core_dim_geography g ON g.geography_id = eri.geography_id
JOIN core_dim_industry i ON i.industry_id = eri.industry_id;

CREATE INDEX IF NOT EXISTS idx_mart_economic_impact_year_geo
    ON mart_economic_impact (year, geography_code);

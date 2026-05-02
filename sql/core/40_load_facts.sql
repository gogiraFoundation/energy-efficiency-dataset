MERGE INTO core_fact_network_reliability AS tgt
USING (
    SELECT
        d.date_id,
        g.geography_id,
        c.company_id,
        ns.network_sector_id,
        s.ens_mwh,
        s.customer_interruptions,
        s.minutes_lost,
        s.gas_interruption_volume,
        s.gas_lost_volume,
        -- Annual GB total electricity generation in MWh (from generation mix file).
        -- Used as the denominator for reliability_rate on ET/ED rows.
        CASE WHEN ns.commodity = 'electricity'
             THEN demand_e.total_twh * 1000000.0
        END AS total_demand_mwh,
        -- Annual GB total gas supply (sum of monthly mcm/d across sources).
        CASE WHEN ns.commodity = 'gas'
             THEN supply_g.total_value
        END AS total_gas_supply
    FROM stg_network_reliability s
    JOIN core_dim_date d ON d.year = s.year AND d.quarter IS NULL
    JOIN core_dim_geography g ON g.geography_code = 'GB'
    JOIN core_dim_company c ON c.company_name = s.company_name
    JOIN core_dim_network_sector ns ON ns.sector_code = s.network_sector
    LEFT JOIN (
        SELECT year, value AS total_twh
        FROM stg_market_context
        WHERE commodity = 'electricity'
          AND fuel_source = 'TOTAL'
          AND metric_name = 'generation_total_twh'
    ) demand_e ON demand_e.year = s.year
    LEFT JOIN (
        SELECT year, value AS total_value
        FROM stg_market_context
        WHERE commodity = 'gas'
          AND fuel_source = 'TOTAL'
          AND metric_name = 'gas_supply_total'
    ) supply_g ON supply_g.year = s.year
) src
ON (tgt.date_id = src.date_id AND tgt.geography_id = src.geography_id AND tgt.company_id = src.company_id AND tgt.network_sector_id = src.network_sector_id)
WHEN MATCHED THEN UPDATE SET
    ens_mwh = src.ens_mwh,
    customer_interruptions = src.customer_interruptions,
    minutes_lost = src.minutes_lost,
    gas_interruption_volume = src.gas_interruption_volume,
    gas_lost_volume = src.gas_lost_volume,
    total_demand_mwh = src.total_demand_mwh,
    total_gas_supply = src.total_gas_supply
WHEN NOT MATCHED THEN INSERT (
    date_id, geography_id, company_id, network_sector_id, ens_mwh, customer_interruptions, minutes_lost, gas_interruption_volume, gas_lost_volume, total_demand_mwh, total_gas_supply
) VALUES (
    src.date_id, src.geography_id, src.company_id, src.network_sector_id, src.ens_mwh, src.customer_interruptions, src.minutes_lost, src.gas_interruption_volume, src.gas_lost_volume, src.total_demand_mwh, src.total_gas_supply
);

MERGE INTO core_fact_financial_performance AS tgt
USING (
    SELECT d.date_id, c.company_id, ns.network_sector_id, s.totex_allowance_million_gbp, s.actual_totex_million_gbp, s.rore_pct
    FROM stg_financial_performance s
    JOIN core_dim_date d ON d.year = s.year AND d.quarter IS NULL
    JOIN core_dim_company c ON c.company_name = s.company_name
    JOIN core_dim_network_sector ns ON ns.sector_code = s.network_sector
) src
ON (tgt.date_id = src.date_id AND tgt.company_id = src.company_id AND tgt.network_sector_id = src.network_sector_id)
WHEN MATCHED THEN UPDATE SET
    totex_allowance_million_gbp = src.totex_allowance_million_gbp,
    actual_totex_million_gbp = src.actual_totex_million_gbp,
    rore_pct = src.rore_pct
WHEN NOT MATCHED THEN INSERT (date_id, company_id, network_sector_id, totex_allowance_million_gbp, actual_totex_million_gbp, rore_pct)
VALUES (src.date_id, src.company_id, src.network_sector_id, src.totex_allowance_million_gbp, src.actual_totex_million_gbp, src.rore_pct);

MERGE INTO core_fact_customer_metrics AS tgt
USING (
    SELECT d.date_id, g.geography_id, c.company_id, ns.network_sector_id, s.cost_per_customer_gbp, s.satisfaction_score
    FROM stg_customer_metrics s
    JOIN core_dim_date d ON d.year = s.year AND d.quarter IS NULL
    JOIN core_dim_geography g ON g.geography_code = s.geography_code
    LEFT JOIN core_dim_company c ON c.company_name = s.company_name
    LEFT JOIN core_dim_network_sector ns ON ns.sector_code = s.network_sector
) src
ON (tgt.date_id = src.date_id AND tgt.geography_id = src.geography_id AND coalesce(tgt.company_id, -1) = coalesce(src.company_id, -1) AND coalesce(tgt.network_sector_id, -1) = coalesce(src.network_sector_id, -1))
WHEN MATCHED THEN UPDATE SET
    cost_per_customer_gbp = src.cost_per_customer_gbp,
    satisfaction_score = src.satisfaction_score
WHEN NOT MATCHED THEN INSERT (date_id, geography_id, company_id, network_sector_id, cost_per_customer_gbp, satisfaction_score)
VALUES (src.date_id, src.geography_id, src.company_id, src.network_sector_id, src.cost_per_customer_gbp, src.satisfaction_score);

MERGE INTO core_fact_emissions AS tgt
USING (
    SELECT d.date_id, c.company_id, ns.network_sector_id, s.sf6_kg, s.carbon_footprint_tco2e
    FROM stg_emissions s
    JOIN core_dim_date d ON d.year = s.year AND d.quarter IS NULL
    JOIN core_dim_company c ON c.company_name = s.company_name
    JOIN core_dim_network_sector ns ON ns.sector_code = s.network_sector
) src
ON (tgt.date_id = src.date_id AND tgt.company_id = src.company_id AND tgt.network_sector_id = src.network_sector_id)
WHEN MATCHED THEN UPDATE SET sf6_kg = src.sf6_kg, carbon_footprint_tco2e = src.carbon_footprint_tco2e
WHEN NOT MATCHED THEN INSERT (date_id, company_id, network_sector_id, sf6_kg, carbon_footprint_tco2e)
VALUES (src.date_id, src.company_id, src.network_sector_id, src.sf6_kg, src.carbon_footprint_tco2e);

MERGE INTO core_fact_energy_intensity AS tgt
USING (
    SELECT d.date_id, i.industry_id, ei.kwh_per_gva, fu.electricity_pct AS electricity_pct_of_total_energy, fu.gas_pct AS gas_pct_of_total_energy, ei.energy_intensity_index
    FROM stg_energy_intensity ei
    JOIN core_dim_date d ON d.year = ei.year AND d.quarter IS NULL
    JOIN core_dim_industry i ON i.sic_code = ei.sic_code
    LEFT JOIN stg_sector_fuel_use fu ON fu.year = ei.year AND fu.sic_code = ei.sic_code
) src
ON (tgt.date_id = src.date_id AND tgt.industry_id = src.industry_id)
WHEN MATCHED THEN UPDATE SET
    kwh_per_gva = src.kwh_per_gva,
    electricity_pct_of_total_energy = src.electricity_pct_of_total_energy,
    gas_pct_of_total_energy = src.gas_pct_of_total_energy,
    energy_intensity_index = src.energy_intensity_index
WHEN NOT MATCHED THEN INSERT (date_id, industry_id, kwh_per_gva, electricity_pct_of_total_energy, gas_pct_of_total_energy, energy_intensity_index)
VALUES (src.date_id, src.industry_id, src.kwh_per_gva, src.electricity_pct_of_total_energy, src.gas_pct_of_total_energy, src.energy_intensity_index);

MERGE INTO core_fact_regional_gva AS tgt
USING (
    SELECT d.date_id, g.geography_id, i.industry_id, rg.gva_million_gbp
    FROM stg_regional_gva rg
    JOIN core_dim_date d ON d.year = rg.year AND d.quarter IS NULL
    JOIN core_dim_geography g ON g.geography_code = rg.region_code
    JOIN core_dim_industry i ON i.sic_code = rg.sic_code
) src
ON (tgt.date_id = src.date_id AND tgt.geography_id = src.geography_id AND tgt.industry_id = src.industry_id)
WHEN MATCHED THEN UPDATE SET gva_million_gbp = src.gva_million_gbp
WHEN NOT MATCHED THEN INSERT (date_id, geography_id, industry_id, gva_million_gbp)
VALUES (src.date_id, src.geography_id, src.industry_id, src.gva_million_gbp);

MERGE INTO core_fact_input_output AS tgt
USING (
    SELECT
        d.date_id,
        i.industry_id,
        io.commodity,
        io.intermediate_consumption_share,
        io.intermediate_consumption_value
    FROM stg_intermediate_consumption io
    JOIN core_dim_date d ON d.year = io.year AND d.quarter IS NULL
    JOIN core_dim_industry i ON i.sic_code = io.sic_code
) src
ON (tgt.date_id = src.date_id AND tgt.industry_id = src.industry_id AND tgt.commodity = src.commodity)
WHEN MATCHED THEN UPDATE SET
    intermediate_consumption_share = src.intermediate_consumption_share,
    intermediate_consumption_value = src.intermediate_consumption_value
WHEN NOT MATCHED THEN INSERT (
    date_id, industry_id, commodity, intermediate_consumption_share, intermediate_consumption_value
)
VALUES (
    src.date_id, src.industry_id, src.commodity, src.intermediate_consumption_share, src.intermediate_consumption_value
);

-- =============================================================================
-- Market facts: prices, context fuel-mix, 2024 market shares
-- =============================================================================

MERGE INTO core_fact_market_prices AS tgt
USING (
    SELECT
        d.date_id,
        g.geography_id,
        s.year,
        s.commodity,
        s.instrument,
        s.metric_name,
        s.avg_value AS value,
        s.unit
    FROM stg_market_prices s
    JOIN core_dim_date d ON d.year = s.year AND d.quarter IS NULL
    JOIN core_dim_geography g ON g.geography_code = 'GB'
) src
ON (tgt.year = src.year AND tgt.commodity = src.commodity
    AND coalesce(tgt.instrument, '__NULL__') = coalesce(src.instrument, '__NULL__')
    AND tgt.metric_name = src.metric_name
    AND tgt.period_label IS NULL)   -- annual rows only; period_label intentionally NULL
WHEN MATCHED THEN UPDATE SET
    date_id = src.date_id,
    geography_id = src.geography_id,
    value = src.value,
    unit = src.unit
WHEN NOT MATCHED THEN INSERT (date_id, geography_id, year, commodity, instrument, metric_name, value, unit)
VALUES (src.date_id, src.geography_id, src.year, src.commodity, src.instrument, src.metric_name, src.value, src.unit);

MERGE INTO core_fact_market_context AS tgt
USING (
    SELECT
        d.date_id,
        g.geography_id,
        s.year,
        s.commodity,
        s.fuel_source,
        s.metric_name,
        s.value,
        s.unit
    FROM stg_market_context s
    JOIN core_dim_date d ON d.year = s.year AND d.quarter IS NULL
    JOIN core_dim_geography g ON g.geography_code = 'GB'
) src
ON (tgt.year = src.year AND tgt.commodity = src.commodity
    AND coalesce(tgt.fuel_source, '__NULL__') = coalesce(src.fuel_source, '__NULL__')
    AND tgt.metric_name = src.metric_name)
WHEN MATCHED THEN UPDATE SET
    date_id = src.date_id,
    geography_id = src.geography_id,
    value = src.value,
    unit = src.unit
WHEN NOT MATCHED THEN INSERT (date_id, geography_id, year, commodity, fuel_source, metric_name, value, unit)
VALUES (src.date_id, src.geography_id, src.year, src.commodity, src.fuel_source, src.metric_name, src.value, src.unit);

MERGE INTO core_fact_market_share AS tgt
USING (
    SELECT s.year, s.commodity, s.company_name, s.share_pct, s.source_file
    FROM stg_market_share s
) src
ON (tgt.year = src.year AND tgt.commodity = src.commodity AND tgt.company_name = src.company_name)
WHEN MATCHED THEN UPDATE SET share_pct = src.share_pct, source_file = src.source_file
WHEN NOT MATCHED THEN INSERT (year, commodity, company_name, share_pct, source_file)
VALUES (src.year, src.commodity, src.company_name, src.share_pct, src.source_file);

MERGE INTO core_fact_daily_prices AS tgt
USING (
    SELECT
        d.date_id,
        g.geography_id,
        s.period_date,
        s.commodity,
        s.source_name,
        s.metric_name,
        s.value,
        s.unit
    FROM stg_daily_market_prices s
    JOIN core_dim_date d ON d.year = s.year AND d.period_kind = 'annual'
    JOIN core_dim_geography g ON g.geography_code = 'GB'
) src
ON (
    tgt.period_date = src.period_date
    AND tgt.commodity = src.commodity
    AND tgt.source_name = src.source_name
    AND tgt.metric_name = src.metric_name
)
WHEN MATCHED THEN UPDATE SET
    date_id = src.date_id,
    geography_id = src.geography_id,
    value = src.value,
    unit = src.unit
WHEN NOT MATCHED THEN INSERT (
    date_id, geography_id, period_date, commodity, source_name, metric_name, value, unit
)
VALUES (
    src.date_id, src.geography_id, src.period_date, src.commodity, src.source_name, src.metric_name, src.value, src.unit
);

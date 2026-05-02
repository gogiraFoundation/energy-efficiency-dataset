-- Quick pipeline healthcheck: row counts by layer.

WITH counts AS (
    -- raw xlsx layer
    SELECT 'raw_xlsx'::text AS layer, 'raw_xlsx_reliability'::text AS table_name, COUNT(*)::bigint AS row_count FROM raw_xlsx_reliability
    UNION ALL SELECT 'raw_xlsx', 'raw_xlsx_expenditure',           COUNT(*)::bigint FROM raw_xlsx_expenditure
    UNION ALL SELECT 'raw_xlsx', 'raw_xlsx_rore',                  COUNT(*)::bigint FROM raw_xlsx_rore
    UNION ALL SELECT 'raw_xlsx', 'raw_xlsx_customer_satisfaction', COUNT(*)::bigint FROM raw_xlsx_customer_satisfaction
    UNION ALL SELECT 'raw_xlsx', 'raw_xlsx_emissions',             COUNT(*)::bigint FROM raw_xlsx_emissions
    UNION ALL SELECT 'raw_xlsx', 'raw_xlsx_connections',           COUNT(*)::bigint FROM raw_xlsx_connections
    UNION ALL SELECT 'raw_xlsx', 'raw_xlsx_fuel_poor',             COUNT(*)::bigint FROM raw_xlsx_fuel_poor
    UNION ALL SELECT 'raw_xlsx', 'raw_xlsx_undergrounding',        COUNT(*)::bigint FROM raw_xlsx_undergrounding
    UNION ALL SELECT 'raw_xlsx', 'raw_xlsx_network_availability',  COUNT(*)::bigint FROM raw_xlsx_network_availability
    UNION ALL SELECT 'raw_xlsx', 'raw_xlsx_risk_reduction',        COUNT(*)::bigint FROM raw_xlsx_risk_reduction
    UNION ALL SELECT 'raw_xlsx', 'raw_xlsx_market_prices',         COUNT(*)::bigint FROM raw_xlsx_market_prices
    UNION ALL SELECT 'raw_xlsx', 'raw_xlsx_market_volumes',        COUNT(*)::bigint FROM raw_xlsx_market_volumes
    UNION ALL SELECT 'raw_xlsx', 'raw_xlsx_generation_mix',        COUNT(*)::bigint FROM raw_xlsx_generation_mix
    UNION ALL SELECT 'raw_xlsx', 'raw_xlsx_gas_supply',            COUNT(*)::bigint FROM raw_xlsx_gas_supply
    UNION ALL SELECT 'raw_xlsx', 'raw_xlsx_estimated_costs',       COUNT(*)::bigint FROM raw_xlsx_estimated_costs
    UNION ALL SELECT 'raw_xlsx', 'raw_xlsx_generation_share',      COUNT(*)::bigint FROM raw_xlsx_generation_share
    UNION ALL SELECT 'raw_xlsx', 'raw_xlsx_renewables',            COUNT(*)::bigint FROM raw_xlsx_renewables
    UNION ALL SELECT 'raw_xlsx', 'raw_xlsx_whd',                   COUNT(*)::bigint FROM raw_xlsx_whd
    UNION ALL SELECT 'raw_xlsx', 'raw_xlsx_scheme_metric',        COUNT(*)::bigint FROM raw_xlsx_scheme_metric

    -- staging layer
    UNION ALL SELECT 'staging', 'stg_network_reliability',   COUNT(*)::bigint FROM stg_network_reliability
    UNION ALL SELECT 'staging', 'stg_financial_performance', COUNT(*)::bigint FROM stg_financial_performance
    UNION ALL SELECT 'staging', 'stg_customer_metrics',      COUNT(*)::bigint FROM stg_customer_metrics
    UNION ALL SELECT 'staging', 'stg_emissions',             COUNT(*)::bigint FROM stg_emissions
    UNION ALL SELECT 'staging', 'stg_energy_intensity',      COUNT(*)::bigint FROM stg_energy_intensity
    UNION ALL SELECT 'staging', 'stg_sector_fuel_use',       COUNT(*)::bigint FROM stg_sector_fuel_use
    UNION ALL SELECT 'staging', 'stg_regional_gva',          COUNT(*)::bigint FROM stg_regional_gva
    UNION ALL SELECT 'staging', 'stg_lcree',                 COUNT(*)::bigint FROM stg_lcree
    UNION ALL SELECT 'staging', 'stg_market_prices',         COUNT(*)::bigint FROM stg_market_prices
    UNION ALL SELECT 'staging', 'stg_market_context',        COUNT(*)::bigint FROM stg_market_context
    UNION ALL SELECT 'staging', 'stg_market_share',          COUNT(*)::bigint FROM stg_market_share
    UNION ALL SELECT 'staging', 'stg_renewables_capacity',   COUNT(*)::bigint FROM stg_renewables_capacity
    UNION ALL SELECT 'staging', 'stg_renewables_quarterly',  COUNT(*)::bigint FROM stg_renewables_quarterly
    UNION ALL SELECT 'staging', 'stg_renewables_regional',   COUNT(*)::bigint FROM stg_renewables_regional
    UNION ALL SELECT 'staging', 'stg_renewables_obligation', COUNT(*)::bigint FROM stg_renewables_obligation
    UNION ALL SELECT 'staging', 'stg_whd_scheme_year',       COUNT(*)::bigint FROM stg_whd_scheme_year
    UNION ALL SELECT 'staging', 'stg_whd_obligation',        COUNT(*)::bigint FROM stg_whd_obligation
    UNION ALL SELECT 'staging', 'stg_scheme_metric',          COUNT(*)::bigint FROM stg_scheme_metric
    UNION ALL SELECT 'staging', 'stg_dukes_chapter1_sup',      COUNT(*)::bigint FROM stg_dukes_chapter1_sup
    UNION ALL SELECT 'staging', 'stg_dukes_chapter4',          COUNT(*)::bigint FROM stg_dukes_chapter4
    UNION ALL SELECT 'staging', 'stg_dukes_chapter5',          COUNT(*)::bigint FROM stg_dukes_chapter5
    UNION ALL SELECT 'staging', 'stg_dukes_chapter6',          COUNT(*)::bigint FROM stg_dukes_chapter6

    -- core layer
    UNION ALL SELECT 'core', 'core_fact_network_reliability',   COUNT(*)::bigint FROM core_fact_network_reliability
    UNION ALL SELECT 'core', 'core_fact_financial_performance', COUNT(*)::bigint FROM core_fact_financial_performance
    UNION ALL SELECT 'core', 'core_fact_customer_metrics',      COUNT(*)::bigint FROM core_fact_customer_metrics
    UNION ALL SELECT 'core', 'core_fact_emissions',             COUNT(*)::bigint FROM core_fact_emissions
    UNION ALL SELECT 'core', 'core_fact_energy_intensity',      COUNT(*)::bigint FROM core_fact_energy_intensity
    UNION ALL SELECT 'core', 'core_fact_regional_gva',          COUNT(*)::bigint FROM core_fact_regional_gva
    UNION ALL SELECT 'core', 'core_fact_market_prices',         COUNT(*)::bigint FROM core_fact_market_prices
    UNION ALL SELECT 'core', 'core_fact_market_context',        COUNT(*)::bigint FROM core_fact_market_context
    UNION ALL SELECT 'core', 'core_fact_market_share',          COUNT(*)::bigint FROM core_fact_market_share
    UNION ALL SELECT 'core', 'core_dim_company',                COUNT(*)::bigint FROM core_dim_company
    UNION ALL SELECT 'core', 'core_dim_geography',              COUNT(*)::bigint FROM core_dim_geography
    UNION ALL SELECT 'core', 'core_dim_industry',               COUNT(*)::bigint FROM core_dim_industry
    UNION ALL SELECT 'core', 'core_dim_riio_period',            COUNT(*)::bigint FROM core_dim_riio_period
    UNION ALL SELECT 'core', 'core_fact_renewables_obligation', COUNT(*)::bigint FROM core_fact_renewables_obligation
    UNION ALL SELECT 'core', 'core_fact_scheme_metric',        COUNT(*)::bigint FROM core_fact_scheme_metric

    -- mart layer
    UNION ALL SELECT 'mart', 'mart_cost_reliability',          COUNT(*)::bigint FROM mart_cost_reliability
    UNION ALL SELECT 'mart', 'mart_economic_impact',           COUNT(*)::bigint FROM mart_economic_impact
    UNION ALL SELECT 'mart', 'mart_cross_commodity_risk',      COUNT(*)::bigint FROM mart_cross_commodity_risk
    UNION ALL SELECT 'mart', 'mart_regulatory_performance',    COUNT(*)::bigint FROM mart_regulatory_performance
    UNION ALL SELECT 'mart', 'mart_decarbonisation_narrative', COUNT(*)::bigint FROM mart_decarbonisation_narrative
    UNION ALL SELECT 'mart', 'mart_market_context',            COUNT(*)::bigint FROM mart_market_context
    UNION ALL SELECT 'mart', 'mart_renewables_deployment',     COUNT(*)::bigint FROM mart_renewables_deployment
    UNION ALL SELECT 'mart', 'mart_renewables_obligation',    COUNT(*)::bigint FROM mart_renewables_obligation
    UNION ALL SELECT 'mart', 'mart_warm_home_discount',        COUNT(*)::bigint FROM mart_warm_home_discount
    UNION ALL SELECT 'mart', 'mart_scheme_metric',             COUNT(*)::bigint FROM mart_scheme_metric
    UNION ALL SELECT 'mart', 'mart_dukes_official_renewables', COUNT(*)::bigint FROM mart_dukes_official_renewables
)
SELECT layer, table_name, row_count
FROM counts
ORDER BY
    CASE layer
        WHEN 'raw_xlsx' THEN 1
        WHEN 'staging'  THEN 2
        WHEN 'core'     THEN 3
        ELSE 4
    END,
    table_name;

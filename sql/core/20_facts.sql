CREATE TABLE IF NOT EXISTS core_fact_network_reliability (
    reliability_id BIGSERIAL PRIMARY KEY,
    date_id INTEGER NOT NULL REFERENCES core_dim_date(date_id),
    geography_id BIGINT NOT NULL REFERENCES core_dim_geography(geography_id),
    company_id BIGINT NOT NULL REFERENCES core_dim_company(company_id),
    network_sector_id BIGINT NOT NULL REFERENCES core_dim_network_sector(network_sector_id),
    ens_mwh NUMERIC,
    customer_interruptions NUMERIC,
    minutes_lost NUMERIC,
    gas_interruption_volume NUMERIC,
    gas_lost_volume NUMERIC,
    total_demand_mwh NUMERIC,
    total_gas_supply NUMERIC,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (date_id, geography_id, company_id, network_sector_id)
);

CREATE TABLE IF NOT EXISTS core_fact_financial_performance (
    financial_id BIGSERIAL PRIMARY KEY,
    date_id INTEGER NOT NULL REFERENCES core_dim_date(date_id),
    company_id BIGINT NOT NULL REFERENCES core_dim_company(company_id),
    network_sector_id BIGINT NOT NULL REFERENCES core_dim_network_sector(network_sector_id),
    totex_allowance_million_gbp NUMERIC,
    actual_totex_million_gbp NUMERIC,
    rore_pct NUMERIC,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (date_id, company_id, network_sector_id)
);

CREATE TABLE IF NOT EXISTS core_fact_customer_metrics (
    customer_metric_id BIGSERIAL PRIMARY KEY,
    date_id INTEGER NOT NULL REFERENCES core_dim_date(date_id),
    geography_id BIGINT NOT NULL REFERENCES core_dim_geography(geography_id),
    company_id BIGINT REFERENCES core_dim_company(company_id),
    network_sector_id BIGINT REFERENCES core_dim_network_sector(network_sector_id),
    cost_per_customer_gbp NUMERIC,
    satisfaction_score NUMERIC,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (date_id, geography_id, company_id, network_sector_id)
);

CREATE TABLE IF NOT EXISTS core_fact_emissions (
    emissions_id BIGSERIAL PRIMARY KEY,
    date_id INTEGER NOT NULL REFERENCES core_dim_date(date_id),
    company_id BIGINT NOT NULL REFERENCES core_dim_company(company_id),
    network_sector_id BIGINT NOT NULL REFERENCES core_dim_network_sector(network_sector_id),
    sf6_kg NUMERIC,
    carbon_footprint_tco2e NUMERIC,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (date_id, company_id, network_sector_id)
);

CREATE TABLE IF NOT EXISTS core_fact_energy_intensity (
    energy_intensity_id BIGSERIAL PRIMARY KEY,
    date_id INTEGER NOT NULL REFERENCES core_dim_date(date_id),
    industry_id BIGINT NOT NULL REFERENCES core_dim_industry(industry_id),
    kwh_per_gva NUMERIC NOT NULL,
    electricity_pct_of_total_energy NUMERIC,
    gas_pct_of_total_energy NUMERIC,
    energy_intensity_index NUMERIC,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (date_id, industry_id)
);

CREATE TABLE IF NOT EXISTS core_fact_regional_gva (
    regional_gva_id BIGSERIAL PRIMARY KEY,
    date_id INTEGER NOT NULL REFERENCES core_dim_date(date_id),
    geography_id BIGINT NOT NULL REFERENCES core_dim_geography(geography_id),
    industry_id BIGINT NOT NULL REFERENCES core_dim_industry(industry_id),
    gva_million_gbp NUMERIC NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (date_id, geography_id, industry_id)
);

CREATE TABLE IF NOT EXISTS core_fact_input_output (
    input_output_id BIGSERIAL PRIMARY KEY,
    date_id INTEGER NOT NULL REFERENCES core_dim_date(date_id),
    industry_id BIGINT NOT NULL REFERENCES core_dim_industry(industry_id),
    commodity TEXT NOT NULL,
    intermediate_consumption_share NUMERIC,
    intermediate_consumption_value NUMERIC,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (date_id, industry_id, commodity)
);

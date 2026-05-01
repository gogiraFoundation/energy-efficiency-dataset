-- =============================================================================
-- raw_xlsx_* themed typed tables for the 38 Ofgem Data Portal xlsx files.
-- One row per (source_file, period, entity, metric).  Loaded by
-- pipeline/ingest/load_xlsx.py via the metadata/xlsx_registry.yaml registry.
--
-- All UNIQUE constraints use NULLS NOT DISTINCT (PostgreSQL 15+) so MERGE upserts
-- stay idempotent even when an entity column is null (e.g. GB-wide metrics).
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Network / RIIO-shaped tables: annual values by company and sector.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_xlsx_reliability (
    raw_xlsx_id BIGSERIAL PRIMARY KEY,
    year INT,
    company_name TEXT,
    network_sector TEXT,
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT raw_xlsx_reliability_natural_uniq
        UNIQUE NULLS NOT DISTINCT (source_file, year, company_name, network_sector, metric_name)
);

CREATE TABLE IF NOT EXISTS raw_xlsx_expenditure (
    raw_xlsx_id BIGSERIAL PRIMARY KEY,
    year INT,
    company_name TEXT,
    network_sector TEXT,
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT raw_xlsx_expenditure_natural_uniq
        UNIQUE NULLS NOT DISTINCT (source_file, year, company_name, network_sector, metric_name)
);

CREATE TABLE IF NOT EXISTS raw_xlsx_rore (
    raw_xlsx_id BIGSERIAL PRIMARY KEY,
    year INT,
    company_name TEXT,
    network_sector TEXT,
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT raw_xlsx_rore_natural_uniq
        UNIQUE NULLS NOT DISTINCT (source_file, year, company_name, network_sector, metric_name)
);

CREATE TABLE IF NOT EXISTS raw_xlsx_customer_satisfaction (
    raw_xlsx_id BIGSERIAL PRIMARY KEY,
    year INT,
    company_name TEXT,
    network_sector TEXT,
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT raw_xlsx_customer_satisfaction_natural_uniq
        UNIQUE NULLS NOT DISTINCT (source_file, year, company_name, network_sector, metric_name)
);

CREATE TABLE IF NOT EXISTS raw_xlsx_emissions (
    raw_xlsx_id BIGSERIAL PRIMARY KEY,
    year INT,
    company_name TEXT,
    network_sector TEXT,
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT raw_xlsx_emissions_natural_uniq
        UNIQUE NULLS NOT DISTINCT (source_file, year, company_name, network_sector, metric_name)
);

CREATE TABLE IF NOT EXISTS raw_xlsx_connections (
    raw_xlsx_id BIGSERIAL PRIMARY KEY,
    year INT,
    company_name TEXT,
    network_sector TEXT,
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT raw_xlsx_connections_natural_uniq
        UNIQUE NULLS NOT DISTINCT (source_file, year, company_name, network_sector, metric_name)
);

CREATE TABLE IF NOT EXISTS raw_xlsx_fuel_poor (
    raw_xlsx_id BIGSERIAL PRIMARY KEY,
    year INT,
    company_name TEXT,
    network_sector TEXT,
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT raw_xlsx_fuel_poor_natural_uniq
        UNIQUE NULLS NOT DISTINCT (source_file, year, company_name, network_sector, metric_name)
);

CREATE TABLE IF NOT EXISTS raw_xlsx_undergrounding (
    raw_xlsx_id BIGSERIAL PRIMARY KEY,
    year INT,
    company_name TEXT,
    network_sector TEXT,
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT raw_xlsx_undergrounding_natural_uniq
        UNIQUE NULLS NOT DISTINCT (source_file, year, company_name, network_sector, metric_name)
);

CREATE TABLE IF NOT EXISTS raw_xlsx_network_availability (
    raw_xlsx_id BIGSERIAL PRIMARY KEY,
    year INT,
    company_name TEXT,
    network_sector TEXT,
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT raw_xlsx_network_availability_natural_uniq
        UNIQUE NULLS NOT DISTINCT (source_file, year, company_name, network_sector, metric_name)
);

CREATE TABLE IF NOT EXISTS raw_xlsx_risk_reduction (
    raw_xlsx_id BIGSERIAL PRIMARY KEY,
    year INT,
    company_name TEXT,
    network_sector TEXT,
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT raw_xlsx_risk_reduction_natural_uniq
        UNIQUE NULLS NOT DISTINCT (source_file, year, company_name, network_sector, metric_name)
);

-- -----------------------------------------------------------------------------
-- Wholesale market-share snapshot (no period dimension on rows).
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_xlsx_generation_share (
    raw_xlsx_id BIGSERIAL PRIMARY KEY,
    year INT,
    company_name TEXT,
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT raw_xlsx_generation_share_natural_uniq
        UNIQUE NULLS NOT DISTINCT (source_file, year, company_name, metric_name)
);

-- -----------------------------------------------------------------------------
-- Market / time-series shape: dated observations of a (commodity, instrument).
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_xlsx_market_prices (
    raw_xlsx_id BIGSERIAL PRIMARY KEY,
    period_date DATE,
    period_label TEXT,
    year INT,
    commodity TEXT,
    instrument TEXT,
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT raw_xlsx_market_prices_natural_uniq
        UNIQUE NULLS NOT DISTINCT (source_file, period_label, commodity, instrument, metric_name)
);

CREATE TABLE IF NOT EXISTS raw_xlsx_market_volumes (
    raw_xlsx_id BIGSERIAL PRIMARY KEY,
    period_date DATE,
    period_label TEXT,
    year INT,
    commodity TEXT,
    instrument TEXT,
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT raw_xlsx_market_volumes_natural_uniq
        UNIQUE NULLS NOT DISTINCT (source_file, period_label, commodity, instrument, metric_name)
);

CREATE TABLE IF NOT EXISTS raw_xlsx_generation_mix (
    raw_xlsx_id BIGSERIAL PRIMARY KEY,
    period_date DATE,
    period_label TEXT,
    year INT,
    commodity TEXT,
    instrument TEXT,             -- fuel source
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT raw_xlsx_generation_mix_natural_uniq
        UNIQUE NULLS NOT DISTINCT (source_file, period_label, commodity, instrument, metric_name)
);

CREATE TABLE IF NOT EXISTS raw_xlsx_gas_supply (
    raw_xlsx_id BIGSERIAL PRIMARY KEY,
    period_date DATE,
    period_label TEXT,
    year INT,
    commodity TEXT,
    instrument TEXT,             -- supply source
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT raw_xlsx_gas_supply_natural_uniq
        UNIQUE NULLS NOT DISTINCT (source_file, period_label, commodity, instrument, metric_name)
);

CREATE TABLE IF NOT EXISTS raw_xlsx_estimated_costs (
    raw_xlsx_id BIGSERIAL PRIMARY KEY,
    period_date DATE,
    period_label TEXT,
    year INT,
    commodity TEXT,
    instrument TEXT,
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT raw_xlsx_estimated_costs_natural_uniq
        UNIQUE NULLS NOT DISTINCT (source_file, period_label, commodity, instrument, metric_name)
);

-- -----------------------------------------------------------------------------
-- Indexes for staging-layer fan-in queries.
-- -----------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_raw_xlsx_reliability_yc           ON raw_xlsx_reliability (year, company_name, network_sector);
CREATE INDEX IF NOT EXISTS idx_raw_xlsx_expenditure_yc           ON raw_xlsx_expenditure (year, company_name, network_sector);
CREATE INDEX IF NOT EXISTS idx_raw_xlsx_rore_yc                  ON raw_xlsx_rore (year, company_name, network_sector);
CREATE INDEX IF NOT EXISTS idx_raw_xlsx_cust_sat_yc              ON raw_xlsx_customer_satisfaction (year, company_name, network_sector);
CREATE INDEX IF NOT EXISTS idx_raw_xlsx_emissions_yc             ON raw_xlsx_emissions (year, company_name, network_sector);
CREATE INDEX IF NOT EXISTS idx_raw_xlsx_market_prices_period     ON raw_xlsx_market_prices (year, commodity, instrument);
CREATE INDEX IF NOT EXISTS idx_raw_xlsx_market_volumes_period    ON raw_xlsx_market_volumes (year, commodity);
CREATE INDEX IF NOT EXISTS idx_raw_xlsx_generation_mix_period    ON raw_xlsx_generation_mix (year, instrument);
CREATE INDEX IF NOT EXISTS idx_raw_xlsx_gas_supply_period        ON raw_xlsx_gas_supply (year, instrument);

-- -----------------------------------------------------------------------------
-- Extend etl_run_log to capture xlsx-loader error messages.
-- -----------------------------------------------------------------------------

ALTER TABLE etl_run_log
    ADD COLUMN IF NOT EXISTS error_message TEXT;

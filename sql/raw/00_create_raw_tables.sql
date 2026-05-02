CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS stg;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE IF NOT EXISTS audit.etl_run_log (
    run_id BIGSERIAL PRIMARY KEY,
    run_ts TIMESTAMPTZ NOT NULL,
    source_id TEXT NOT NULL,
    target_table TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    null_rate_json JSONB,
    status TEXT NOT NULL,
    details TEXT
);

CREATE TABLE IF NOT EXISTS raw.raw_ofgem_ens (
    natural_key TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    source_id TEXT NOT NULL,
    loaded_at TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS raw.raw_ofgem_expenditure (
    natural_key TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    source_id TEXT NOT NULL,
    loaded_at TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS raw.raw_ofgem_rore (
    natural_key TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    source_id TEXT NOT NULL,
    loaded_at TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS raw.raw_ofgem_customer_metrics (
    natural_key TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    source_id TEXT NOT NULL,
    loaded_at TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS raw.raw_ofgem_emissions (
    natural_key TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    source_id TEXT NOT NULL,
    loaded_at TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS raw.raw_ons_energy_intensity (
    natural_key TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    source_id TEXT NOT NULL,
    loaded_at TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS raw.raw_ons_sector_fuel_use (
    natural_key TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    source_id TEXT NOT NULL,
    loaded_at TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS raw.raw_ons_regional_gva (
    natural_key TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    source_id TEXT NOT NULL,
    loaded_at TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS raw.raw_ons_lcree (
    natural_key TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    source_id TEXT NOT NULL,
    loaded_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS raw.raw_ons_intermediate_consumption (
    natural_key TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    source_id TEXT NOT NULL,
    loaded_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS raw.raw_daily_market_prices (
    natural_key TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    source_id TEXT NOT NULL,
    loaded_at TIMESTAMP NOT NULL
);

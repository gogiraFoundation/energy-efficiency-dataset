-- DUKES macro tables (Digest of UK Energy Statistics — Chapter 1).
-- Rows are loaded by pipeline/ingest/ingest_dukes.py after JSONB ONS/raw ingest.

CREATE TABLE IF NOT EXISTS stg_dukes_primary_consumption (
    year INTEGER PRIMARY KEY,
    primary_energy_mtoe NUMERIC,
    primary_energy_twh NUMERIC,
    gdp_gbp_billion NUMERIC,
    energy_ratio NUMERIC,
    energy_intensity_index_1970_100 NUMERIC,
    source_file TEXT
);

CREATE TABLE IF NOT EXISTS stg_dukes_energy_expenditure (
    year INTEGER NOT NULL,
    sector TEXT NOT NULL,
    expenditure_million_gbp NUMERIC,
    source_file TEXT,
    PRIMARY KEY (year, sector)
);

CREATE TABLE IF NOT EXISTS stg_dukes_final_consumption (
    year INTEGER NOT NULL,
    sector TEXT NOT NULL,
    fuel_type TEXT NOT NULL,
    energy_ktoe NUMERIC,
    energy_twh NUMERIC,
    source_file TEXT,
    PRIMARY KEY (year, sector, fuel_type)
);

-- Inland primary fuels (1.1.1.B — million tonnes of oil equivalent)
CREATE TABLE IF NOT EXISTS stg_dukes_primary_fuels (
    year INTEGER NOT NULL,
    fuel_type TEXT NOT NULL,
    consumption_mtoe NUMERIC,
    source_file TEXT,
    PRIMARY KEY (year, fuel_type)
);

CREATE INDEX IF NOT EXISTS idx_stg_dukes_expenditure_year ON stg_dukes_energy_expenditure (year);
CREATE INDEX IF NOT EXISTS idx_stg_dukes_final_year_sector ON stg_dukes_final_consumption (year, sector);
CREATE INDEX IF NOT EXISTS idx_stg_dukes_fuels_year ON stg_dukes_primary_fuels (year);

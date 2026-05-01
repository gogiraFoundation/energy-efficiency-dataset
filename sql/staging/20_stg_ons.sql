CREATE TABLE IF NOT EXISTS stg_energy_intensity (
    year int,
    sic_code text,
    kwh_per_gva numeric,
    energy_intensity_index numeric,
    industry_name text
);
TRUNCATE TABLE stg_energy_intensity;
INSERT INTO stg_energy_intensity
SELECT
    (payload->>'year')::numeric::int AS year,
    nullif(payload->>'sic_code', '') AS sic_code,
    (payload->>'kwh_per_gva')::numeric AS kwh_per_gva,
    (payload->>'energy_intensity_index')::numeric AS energy_intensity_index,
    nullif(payload->>'industry_name', '') AS industry_name
FROM raw_ons_energy_intensity;
CREATE UNIQUE INDEX IF NOT EXISTS idx_stg_energy_intensity_uniq ON stg_energy_intensity(year, sic_code);

CREATE TABLE IF NOT EXISTS stg_sector_fuel_use (
    year int,
    sic_code text,
    electricity_pct numeric,
    gas_pct numeric
);
TRUNCATE TABLE stg_sector_fuel_use;
INSERT INTO stg_sector_fuel_use
SELECT
    (payload->>'year')::numeric::int AS year,
    nullif(payload->>'sic_code', '') AS sic_code,
    (payload->>'electricity_pct')::numeric AS electricity_pct,
    (payload->>'gas_pct')::numeric AS gas_pct
FROM raw_ons_sector_fuel_use;
CREATE UNIQUE INDEX IF NOT EXISTS idx_stg_sector_fuel_use_uniq ON stg_sector_fuel_use(year, sic_code);

CREATE TABLE IF NOT EXISTS stg_regional_gva (
    year int,
    region_code text,
    sic_code text,
    gva_million_gbp numeric
);
TRUNCATE TABLE stg_regional_gva;
INSERT INTO stg_regional_gva
SELECT
    (payload->>'year')::numeric::int AS year,
    nullif(payload->>'region_code', '') AS region_code,
    nullif(payload->>'sic_code', '') AS sic_code,
    (payload->>'gva_million_gbp')::numeric AS gva_million_gbp
FROM raw_ons_regional_gva;
CREATE UNIQUE INDEX IF NOT EXISTS idx_stg_regional_gva_uniq ON stg_regional_gva(year, region_code, sic_code);

CREATE TABLE IF NOT EXISTS stg_lcree (
    year int,
    lcree_turnover_million_gbp numeric
);
TRUNCATE TABLE stg_lcree;
INSERT INTO stg_lcree
SELECT
    (payload->>'year')::numeric::int AS year,
    (payload->>'lcree_turnover_million_gbp')::numeric AS lcree_turnover_million_gbp
FROM raw_ons_lcree;
CREATE UNIQUE INDEX IF NOT EXISTS idx_stg_lcree_uniq ON stg_lcree(year);

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
    year,
    sic_code,
    AVG(kwh_per_gva) AS kwh_per_gva,
    AVG(energy_intensity_index) AS energy_intensity_index,
    MAX(industry_name) AS industry_name
FROM (
    SELECT
        (payload->>'year')::numeric::int AS year,
        nullif(payload->>'sic_code', '') AS sic_code,
        (payload->>'kwh_per_gva')::numeric AS kwh_per_gva,
        (payload->>'energy_intensity_index')::numeric AS energy_intensity_index,
        nullif(payload->>'industry_name', '') AS industry_name
    FROM raw.raw_ons_energy_intensity
) src
WHERE src.year IS NOT NULL
GROUP BY year, sic_code;
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
FROM raw.raw_ons_sector_fuel_use;
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
FROM raw.raw_ons_regional_gva;
CREATE UNIQUE INDEX IF NOT EXISTS idx_stg_regional_gva_uniq ON stg_regional_gva(year, region_code, sic_code);

CREATE TABLE IF NOT EXISTS stg_lcree (
    year int,
    lcree_turnover_million_gbp numeric
);
TRUNCATE TABLE stg_lcree;
INSERT INTO stg_lcree
SELECT
    (payload->>'year')::numeric::int AS year,
    COALESCE(
        (payload->>'lcree_turnover_million_gbp')::numeric,
        (payload->>'turnover_million_gbp')::numeric,
        (payload->>'turnover_current_prices_million_gbp')::numeric
    ) AS lcree_turnover_million_gbp
FROM raw.raw_ons_lcree;
CREATE UNIQUE INDEX IF NOT EXISTS idx_stg_lcree_uniq ON stg_lcree(year);

CREATE TABLE IF NOT EXISTS stg_intermediate_consumption (
    year int,
    sic_code text,
    industry_name text,
    commodity text,
    intermediate_consumption_share numeric,
    intermediate_consumption_value numeric
);
TRUNCATE TABLE stg_intermediate_consumption;
INSERT INTO stg_intermediate_consumption
SELECT
    (payload->>'year')::numeric::int AS year,
    nullif(payload->>'sic_code', '') AS sic_code,
    nullif(payload->>'industry_name', '') AS industry_name,
    lower(trim(nullif(payload->>'commodity', ''))) AS commodity,
    COALESCE(
        (payload->>'intermediate_consumption_share')::numeric,
        (payload->>'intermediate_share')::numeric
    ) AS intermediate_consumption_share,
    (payload->>'intermediate_consumption_value')::numeric AS intermediate_consumption_value
FROM raw.raw_ons_intermediate_consumption;
CREATE UNIQUE INDEX IF NOT EXISTS idx_stg_intermediate_consumption_uniq
    ON stg_intermediate_consumption(year, sic_code, commodity);

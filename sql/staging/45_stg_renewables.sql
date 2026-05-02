-- =============================================================================
-- Staging tables for renewables (MCS-style) deployment.
--
-- Reads from raw_xlsx_renewables (loaded by pipeline/ingest/load_xlsx.py via
-- the RENEWABLES section of metadata/xlsx_registry.yaml) and produces three
-- typed staging tables:
--
--   stg_renewables_capacity   : annual GB-wide capacity_kw / installations
--   stg_renewables_quarterly  : quarterly GB-wide capacity_kw / installations
--   stg_renewables_regional   : annual region x technology rows (capacity / shares)
--   stg_renewables_installation_type : annual domestic/non-domestic (etc.) splits
--
-- All three are TRUNCATE-and-rebuild on each staging run to mirror the
-- existing market staging script.
--
-- Requires raw_xlsx_renewables from sql/raw/07_create_raw_xlsx_renewables_whd.sql
-- (applied by the xlsx loader and by orchestrate before staging).
-- =============================================================================

DROP TABLE IF EXISTS stg_renewables_capacity CASCADE;
DROP TABLE IF EXISTS stg_renewables_quarterly CASCADE;
DROP TABLE IF EXISTS stg_renewables_regional CASCADE;
DROP TABLE IF EXISTS stg_renewables_installation_type CASCADE;

-- -----------------------------------------------------------------------------
-- Annual GB totals (region IS NULL, installation_type IS NULL, quarter IS NULL).
-- One row per (year, technology, metric_name).
-- -----------------------------------------------------------------------------

CREATE TABLE stg_renewables_capacity AS
SELECT
    year,
    technology,
    metric_name,
    AVG(value)::numeric AS value,
    MAX(unit)           AS unit,
    MAX(source_file)    AS source_file
FROM raw_xlsx_renewables
WHERE year IS NOT NULL
  AND quarter IS NULL
  AND region IS NULL
  AND installation_type IS NULL
  AND technology IS NOT NULL
  AND metric_name IN ('capacity_kw', 'installations')
GROUP BY year, technology, metric_name;

CREATE INDEX IF NOT EXISTS idx_stg_renewables_capacity_yt
    ON stg_renewables_capacity (year, technology);

-- -----------------------------------------------------------------------------
-- Quarterly GB totals (region IS NULL, installation_type IS NULL).
-- One row per (year, quarter, technology, metric_name).
-- -----------------------------------------------------------------------------

CREATE TABLE stg_renewables_quarterly AS
SELECT
    period_date,
    period_label,
    year,
    quarter,
    technology,
    metric_name,
    AVG(value)::numeric AS value,
    MAX(unit)           AS unit,
    MAX(source_file)    AS source_file
FROM raw_xlsx_renewables
WHERE year IS NOT NULL
  AND quarter IS NOT NULL
  AND region IS NULL
  AND installation_type IS NULL
  AND technology IS NOT NULL
  AND metric_name IN ('capacity_kw', 'installations')
GROUP BY period_date, period_label, year, quarter, technology, metric_name;

CREATE INDEX IF NOT EXISTS idx_stg_renewables_quarterly_yqt
    ON stg_renewables_quarterly (year, quarter, technology);

-- -----------------------------------------------------------------------------
-- Regional rows (region NOT NULL).  Includes share_pct rows from the regional
-- breakdown sheet plus any capacity_kw / installations rows that came tagged
-- with a region. installation_type rows are ignored here (handled separately
-- in the mart).
-- -----------------------------------------------------------------------------

CREATE TABLE stg_renewables_regional AS
SELECT
    year,
    region,
    technology,
    metric_name,
    AVG(value)::numeric AS value,
    MAX(unit)           AS unit,
    MAX(source_file)    AS source_file
FROM raw_xlsx_renewables
WHERE year IS NOT NULL
  AND region IS NOT NULL
  AND installation_type IS NULL
  AND technology IS NOT NULL
GROUP BY year, region, technology, metric_name;

CREATE INDEX IF NOT EXISTS idx_stg_renewables_regional_yrt
    ON stg_renewables_regional (year, region, technology);

-- -----------------------------------------------------------------------------
-- Installation-type splits (domestic / non-domestic / … from MCS workbook).
-- -----------------------------------------------------------------------------

CREATE TABLE stg_renewables_installation_type AS
SELECT
    year,
    installation_type,
    technology,
    metric_name,
    AVG(value)::numeric AS value,
    MAX(unit)           AS unit,
    MAX(source_file)    AS source_file
FROM raw_xlsx_renewables
WHERE year IS NOT NULL
  AND quarter IS NULL
  AND region IS NULL
  AND installation_type IS NOT NULL
  AND technology IS NOT NULL
  AND metric_name IN ('capacity_kw', 'installations')
GROUP BY year, installation_type, technology, metric_name;

CREATE INDEX IF NOT EXISTS idx_stg_renewables_install_type_yit
    ON stg_renewables_installation_type (year, installation_type, technology);

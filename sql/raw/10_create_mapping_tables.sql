-- Mapping tables loaded from metadata/*.csv via pipeline/ingest/load_xlsx.py.
-- They sit at the raw/staging boundary: source-system text values get
-- translated to canonical company / geography / industry codes before the
-- typed stg_* tables and core_dim_* tables are populated.

CREATE TABLE IF NOT EXISTS stg_company_alias (
    source_system        TEXT,
    source_company_name  TEXT,
    ofgem_company_id     TEXT,
    company_name         TEXT,
    network_sector_code  TEXT,
    owner_group          TEXT
);
CREATE INDEX IF NOT EXISTS idx_stg_company_alias_src ON stg_company_alias (source_company_name);
CREATE INDEX IF NOT EXISTS idx_stg_company_alias_canon ON stg_company_alias (company_name);

CREATE TABLE IF NOT EXISTS stg_geography_alias (
    source_system           TEXT,
    source_geography_code   TEXT,
    geography_code          TEXT,
    geography_name          TEXT,
    geography_type          TEXT,
    parent_geography_code   TEXT
);
CREATE INDEX IF NOT EXISTS idx_stg_geography_alias_src ON stg_geography_alias (source_geography_code);

CREATE TABLE IF NOT EXISTS stg_sic_alias (
    sic_code                    TEXT,
    sic_section                 TEXT,
    sic_group                   TEXT,
    industry_name               TEXT,
    high_energy_intensity_flag  BOOLEAN
);

CREATE TABLE IF NOT EXISTS stg_supplier_alias (
    source_supplier_name TEXT,
    supplier_name        TEXT,
    supplier_group       TEXT,
    supplier_size        TEXT,
    ofgem_supplier_id    TEXT,
    exited_quarter       TEXT
);
CREATE INDEX IF NOT EXISTS idx_stg_supplier_alias_src ON stg_supplier_alias (source_supplier_name);
CREATE INDEX IF NOT EXISTS idx_stg_supplier_alias_canon ON stg_supplier_alias (supplier_name);

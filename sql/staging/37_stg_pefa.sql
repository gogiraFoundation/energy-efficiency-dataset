-- ONS Physical energy flow accounts (PEFA), staging from official xlsx.
-- Values are terajoules (TJ) per ONS workbook notes.

CREATE TABLE IF NOT EXISTS stg_pefa_matrix (
    id BIGSERIAL PRIMARY KEY,
    reference_year INTEGER NOT NULL,
    table_id TEXT NOT NULL,
    row_no INTEGER,
    row_level INTEGER,
    row_code TEXT,
    row_label TEXT,
    industry_column_index INTEGER NOT NULL,
    industry_code TEXT,
    energy_tj DOUBLE PRECISION,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stg_pefa_matrix_year_table
    ON stg_pefa_matrix (reference_year, table_id);

CREATE INDEX IF NOT EXISTS idx_stg_pefa_matrix_industry
    ON stg_pefa_matrix (industry_code);

COMMENT ON TABLE stg_pefa_matrix IS 'PEFA Tables A–D: long-format TJ by product/indicator row and ISIC industry column.';

CREATE TABLE IF NOT EXISTS stg_pefa_bridge (
    id BIGSERIAL PRIMARY KEY,
    reference_year INTEGER NOT NULL,
    bridge_code TEXT NOT NULL,
    bridge_label TEXT,
    energy_tj DOUBLE PRECISION,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stg_pefa_bridge_year
    ON stg_pefa_bridge (reference_year);

COMMENT ON TABLE stg_pefa_bridge IS 'PEFA Table E: residence vs territory bridge indicators (TJ).';

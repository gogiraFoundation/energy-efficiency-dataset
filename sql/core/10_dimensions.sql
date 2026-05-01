CREATE TABLE IF NOT EXISTS core_dim_date (
    date_id INTEGER PRIMARY KEY,
    year INTEGER NOT NULL,
    quarter INTEGER,
    month INTEGER,
    period_label TEXT NOT NULL,
    UNIQUE (year, quarter, month)
);

INSERT INTO core_dim_date (date_id, year, quarter, month, period_label)
SELECT (y * 10 + 1), y, 1, NULL, y::text || '-annual'
FROM generate_series(2013, 2035) y
ON CONFLICT (date_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS core_dim_geography (
    geography_id BIGSERIAL PRIMARY KEY,
    geography_code TEXT UNIQUE NOT NULL,
    geography_name TEXT NOT NULL,
    geography_type TEXT NOT NULL,
    parent_geography_code TEXT
);

CREATE TABLE IF NOT EXISTS core_dim_network_sector (
    network_sector_id BIGSERIAL PRIMARY KEY,
    sector_code TEXT UNIQUE NOT NULL,
    sector_name TEXT NOT NULL,
    commodity TEXT NOT NULL
);

INSERT INTO core_dim_network_sector (sector_code, sector_name, commodity)
VALUES
('ET', 'Electricity Transmission', 'electricity'),
('ED', 'Electricity Distribution', 'electricity'),
('GT', 'Gas Transmission', 'gas'),
('GD', 'Gas Distribution', 'gas')
ON CONFLICT (sector_code) DO NOTHING;

CREATE TABLE IF NOT EXISTS core_dim_company (
    company_id BIGSERIAL PRIMARY KEY,
    ofgem_company_id TEXT UNIQUE,
    company_name TEXT UNIQUE NOT NULL,
    owner_group TEXT,
    network_sector_id BIGINT REFERENCES core_dim_network_sector(network_sector_id)
);

CREATE TABLE IF NOT EXISTS core_dim_industry (
    industry_id BIGSERIAL PRIMARY KEY,
    sic_code TEXT UNIQUE NOT NULL,
    sic_section TEXT,
    sic_group TEXT,
    industry_name TEXT NOT NULL,
    high_energy_intensity_flag BOOLEAN DEFAULT FALSE
);

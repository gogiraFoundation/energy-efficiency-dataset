CREATE TABLE IF NOT EXISTS core_dim_date (
    date_id INTEGER PRIMARY KEY,
    year INTEGER NOT NULL,
    quarter INTEGER,
    month INTEGER,
    period_label TEXT NOT NULL,
    UNIQUE (year, quarter, month)
);

-- Extension columns added for retail / quarterly grain support.
ALTER TABLE core_dim_date ADD COLUMN IF NOT EXISTS period_kind       TEXT;
ALTER TABLE core_dim_date ADD COLUMN IF NOT EXISTS period_start_date DATE;

-- Legacy annual rows (date_id = y * 10 + 1) historically had quarter = 1 to avoid
-- a NULL collision in the UNIQUE constraint.  Now that we add quarterly rows
-- (date_id = y * 100 + q), reset legacy annual rows so they identify cleanly as
-- (year, NULL, NULL) with period_kind = 'annual'.
UPDATE core_dim_date
SET quarter = NULL,
    period_kind = 'annual',
    period_start_date = make_date(year, 1, 1)
WHERE period_label LIKE '%-annual'
  AND (period_kind IS NULL OR period_kind = 'annual');

-- Annual rows (id = y * 10 + 1).  Range widened to cover retail series that
-- pre-date 2013 (e.g. household energy spend back to 1993).
INSERT INTO core_dim_date (date_id, year, quarter, month, period_label, period_kind, period_start_date)
SELECT (y * 10 + 1), y, NULL, NULL, y::text || '-annual', 'annual', make_date(y, 1, 1)
FROM generate_series(1990, 2035) y
ON CONFLICT (date_id) DO UPDATE
    SET period_kind = EXCLUDED.period_kind,
        period_start_date = EXCLUDED.period_start_date;

-- Quarterly rows (id = y * 100 + q).  Used by the retail facts.
INSERT INTO core_dim_date (date_id, year, quarter, month, period_label, period_kind, period_start_date)
SELECT (y * 100 + q),
       y,
       q,
       NULL,
       y::text || ' Q' || q::text,
       'quarterly',
       make_date(y, ((q - 1) * 3) + 1, 1)
FROM generate_series(1990, 2035) y CROSS JOIN generate_series(1, 4) q
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

-- core_dim_riio_period: explicit windows for the three RIIO price-control
-- schemes covered by the Ofgem source set. Used by marts to filter and to
-- align Year-N tokens to calendar years.

CREATE TABLE IF NOT EXISTS core_dim_riio_period (
    riio_period_id SERIAL PRIMARY KEY,
    scheme TEXT NOT NULL UNIQUE,
    long_name TEXT,
    network_sectors TEXT[],
    start_year INTEGER NOT NULL,
    end_year INTEGER NOT NULL,
    duration_years INTEGER GENERATED ALWAYS AS (end_year - start_year + 1) STORED
);

INSERT INTO core_dim_riio_period (scheme, long_name, network_sectors, start_year, end_year)
VALUES
    ('T1',  'RIIO-T1 (Electricity & Gas Transmission)', ARRAY['Electricity Transmission','Gas Transmission'], 2014, 2021),
    ('ED1', 'RIIO-ED1 (Electricity Distribution)',      ARRAY['Electricity Distribution'],                    2016, 2023),
    ('GD1', 'RIIO-GD1 (Gas Distribution)',              ARRAY['Gas Distribution'],                            2014, 2021)
ON CONFLICT (scheme) DO UPDATE
    SET long_name = EXCLUDED.long_name,
        network_sectors = EXCLUDED.network_sectors,
        start_year = EXCLUDED.start_year,
        end_year = EXCLUDED.end_year;

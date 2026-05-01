INSERT INTO core_dim_geography (geography_code, geography_name, geography_type, parent_geography_code)
VALUES
('GB', 'Great Britain', 'country', NULL),
('E12000001', 'North East', 'region', 'GB'),
('E12000002', 'North West', 'region', 'GB'),
('E12000003', 'Yorkshire and The Humber', 'region', 'GB'),
('E12000004', 'East Midlands', 'region', 'GB'),
('E12000005', 'West Midlands', 'region', 'GB'),
('E12000006', 'East of England', 'region', 'GB'),
('E12000007', 'London', 'region', 'GB'),
('E12000008', 'South East', 'region', 'GB'),
('E12000009', 'South West', 'region', 'GB'),
('S92000003', 'Scotland', 'region', 'GB'),
('W92000004', 'Wales', 'region', 'GB')
ON CONFLICT (geography_code) DO NOTHING;

-- Seed canonical companies from the alias CSV (loaded by pipeline/ingest/load_xlsx.py).
-- This subsumes the original hard-coded list and adds every ED1 DNO and GD1 GDN
-- referenced by the 38 Ofgem xlsx files plus the 2024 wholesale generators.
INSERT INTO core_dim_company (ofgem_company_id, company_name, owner_group, network_sector_id)
SELECT
    a.ofgem_company_id,
    a.company_name,
    a.owner_group,
    ns.network_sector_id
FROM (
    -- One core row per ofgem_company_id (aliases may list several source names).
    SELECT DISTINCT ON (ofgem_company_id)
        ofgem_company_id,
        company_name,
        owner_group,
        network_sector_code
    FROM stg_company_alias
    WHERE company_name IS NOT NULL
      AND ofgem_company_id IS NOT NULL
    ORDER BY ofgem_company_id, company_name
) a
LEFT JOIN core_dim_network_sector ns ON ns.sector_code = a.network_sector_code
ON CONFLICT (company_name) DO UPDATE
    SET owner_group = EXCLUDED.owner_group,
        network_sector_id = EXCLUDED.network_sector_id;

-- Generation owners do not map to ED/ET/GD/GT.  Insert with NULL sector_id.
-- NULL must be typed: otherwise PostgreSQL treats it as text vs bigint network_sector_id.
INSERT INTO core_dim_company (ofgem_company_id, company_name, owner_group, network_sector_id)
SELECT DISTINCT a.ofgem_company_id, a.company_name, a.owner_group, NULL::bigint
FROM stg_company_alias a
WHERE a.network_sector_code = 'GEN'
  AND a.company_name IS NOT NULL
ON CONFLICT (company_name) DO NOTHING;

INSERT INTO core_dim_industry (sic_code, sic_section, sic_group, industry_name, high_energy_intensity_flag)
SELECT DISTINCT
    e.sic_code,
    LEFT(e.sic_code, 1),
    e.sic_code,
    COALESCE(MAX(e.industry_name), e.sic_code),
    CASE WHEN LEFT(e.sic_code, 1) IN ('B', 'C', 'D', 'E', 'H') THEN TRUE ELSE FALSE END
FROM stg_energy_intensity e
GROUP BY e.sic_code
ON CONFLICT (sic_code) DO NOTHING;

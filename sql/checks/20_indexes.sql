CREATE INDEX IF NOT EXISTS idx_fact_reliability_year_company ON core_fact_network_reliability(date_id, company_id);
CREATE INDEX IF NOT EXISTS idx_fact_financial_year_company ON core_fact_financial_performance(date_id, company_id);
CREATE INDEX IF NOT EXISTS idx_fact_energy_intensity_industry_year ON core_fact_energy_intensity(industry_id, date_id);
CREATE INDEX IF NOT EXISTS idx_fact_regional_gva_industry_year ON core_fact_regional_gva(industry_id, geography_id, date_id);

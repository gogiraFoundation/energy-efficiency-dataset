-- Synonym views that expose the existing core_dim_* / core_fact_* tables under
-- the dim_* / fact_* names used in the project specification and example
-- queries.  Pure pass-through: marts and ad-hoc analysts can use either name.

CREATE OR REPLACE VIEW dim_date              AS SELECT * FROM core_dim_date;
CREATE OR REPLACE VIEW dim_company           AS SELECT * FROM core_dim_company;
CREATE OR REPLACE VIEW dim_geography         AS SELECT * FROM core_dim_geography;
CREATE OR REPLACE VIEW dim_industry          AS SELECT * FROM core_dim_industry;
CREATE OR REPLACE VIEW dim_network_sector    AS SELECT * FROM core_dim_network_sector;
CREATE OR REPLACE VIEW dim_riio_period       AS SELECT * FROM core_dim_riio_period;

CREATE OR REPLACE VIEW fact_reliability      AS SELECT * FROM core_fact_network_reliability;
CREATE OR REPLACE VIEW fact_financial        AS SELECT * FROM core_fact_financial_performance;
CREATE OR REPLACE VIEW fact_customer         AS SELECT * FROM core_fact_customer_metrics;
CREATE OR REPLACE VIEW fact_emissions        AS SELECT * FROM core_fact_emissions;
CREATE OR REPLACE VIEW fact_energy_intensity AS SELECT * FROM core_fact_energy_intensity;
CREATE OR REPLACE VIEW fact_regional_gva     AS SELECT * FROM core_fact_regional_gva;
CREATE OR REPLACE VIEW fact_market_prices    AS SELECT * FROM core_fact_market_prices;
CREATE OR REPLACE VIEW fact_market_context   AS SELECT * FROM core_fact_market_context;

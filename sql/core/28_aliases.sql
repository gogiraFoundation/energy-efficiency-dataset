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
CREATE OR REPLACE VIEW fact_input_output     AS SELECT * FROM core_fact_input_output;
CREATE OR REPLACE VIEW fact_market_prices    AS SELECT * FROM core_fact_market_prices;
CREATE OR REPLACE VIEW fact_market_context   AS SELECT * FROM core_fact_market_context;
CREATE OR REPLACE VIEW fact_daily_prices     AS SELECT * FROM core_fact_daily_prices;

-- Retail layer synonyms (sql/core/13_dim_supplier.sql, 22_facts_retail.sql).
CREATE OR REPLACE VIEW dim_supplier              AS SELECT * FROM core_dim_supplier;
CREATE OR REPLACE VIEW dim_payment_method        AS SELECT * FROM core_dim_payment_method;
CREATE OR REPLACE VIEW dim_supplier_size         AS SELECT * FROM core_dim_supplier_size;

CREATE OR REPLACE VIEW fact_supplier_financial      AS SELECT * FROM core_fact_supplier_financial;
CREATE OR REPLACE VIEW fact_consumer_debt           AS SELECT * FROM core_fact_consumer_debt;
CREATE OR REPLACE VIEW fact_consumer_disconnections AS SELECT * FROM core_fact_consumer_disconnections;
CREATE OR REPLACE VIEW fact_switching_activity      AS SELECT * FROM core_fact_switching_activity;
CREATE OR REPLACE VIEW fact_tariff_benchmarks       AS SELECT * FROM core_fact_tariff_benchmarks;
CREATE OR REPLACE VIEW fact_bill_breakdown          AS SELECT * FROM core_fact_bill_breakdown;
CREATE OR REPLACE VIEW fact_complaints_resolution   AS SELECT * FROM core_fact_complaints_resolution;
CREATE OR REPLACE VIEW fact_satisfaction_scores     AS SELECT * FROM core_fact_satisfaction_scores;
CREATE OR REPLACE VIEW fact_market_structure        AS SELECT * FROM core_fact_market_structure;
CREATE OR REPLACE VIEW fact_market_share_retail     AS SELECT * FROM core_fact_market_share_retail;
CREATE OR REPLACE VIEW fact_household_spend         AS SELECT * FROM core_fact_household_spend;
CREATE OR REPLACE VIEW fact_customer_accounts_retail AS SELECT * FROM core_fact_customer_accounts_retail;
CREATE OR REPLACE VIEW fact_heating_systems         AS SELECT * FROM core_fact_heating_systems;
CREATE OR REPLACE VIEW fact_renewables_obligation   AS SELECT * FROM core_fact_renewables_obligation;

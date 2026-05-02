-- =============================================================================
-- Retail / consumer fact tables.
--
-- All tables share the same access pattern as the existing core_fact_market_*
-- tables: dimension keys (date_id, supplier_id, payment_method_id) where the
-- grain is supplier-or-method-aware, and a (metric_name, value, unit) tail
-- where the source data spans many heterogeneous metrics.
-- =============================================================================

CREATE TABLE IF NOT EXISTS core_fact_supplier_financial (
    supplier_financial_id BIGSERIAL PRIMARY KEY,
    date_id INTEGER NOT NULL REFERENCES core_dim_date(date_id),
    supplier_id BIGINT REFERENCES core_dim_supplier(supplier_id),
    segment TEXT NOT NULL,                  -- domestic | non_domestic | generation | supply_aggregate
    metric_name TEXT NOT NULL,              -- profit_million_gbp | pretax_margin_pct | ...
    value NUMERIC,
    unit TEXT,
    source_file TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT core_fact_supplier_financial_uniq
        UNIQUE NULLS NOT DISTINCT (date_id, supplier_id, segment, metric_name)
);
CREATE INDEX IF NOT EXISTS idx_core_fact_supplier_financial_supplier
    ON core_fact_supplier_financial (supplier_id, metric_name);

CREATE TABLE IF NOT EXISTS core_fact_consumer_debt (
    consumer_debt_id BIGSERIAL PRIMARY KEY,
    date_id INTEGER NOT NULL REFERENCES core_dim_date(date_id),
    commodity TEXT,                         -- electricity | gas | dual_fuel
    payment_method_id BIGINT REFERENCES core_dim_payment_method(payment_method_id),
    supplier_id BIGINT REFERENCES core_dim_supplier(supplier_id),
    component TEXT,                         -- debt | arrears | debt_plus_arrears
    metric_name TEXT NOT NULL,
    value NUMERIC,
    unit TEXT,
    source_file TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT core_fact_consumer_debt_uniq
        UNIQUE NULLS NOT DISTINCT (date_id, commodity, payment_method_id, supplier_id, component, metric_name)
);
CREATE INDEX IF NOT EXISTS idx_core_fact_consumer_debt_yc
    ON core_fact_consumer_debt (date_id, commodity, metric_name);

CREATE TABLE IF NOT EXISTS core_fact_consumer_disconnections (
    consumer_disconnections_id BIGSERIAL PRIMARY KEY,
    date_id INTEGER NOT NULL REFERENCES core_dim_date(date_id),
    commodity TEXT,
    payment_method_id BIGINT REFERENCES core_dim_payment_method(payment_method_id),
    supplier_id BIGINT REFERENCES core_dim_supplier(supplier_id),
    metric_name TEXT NOT NULL,
    value NUMERIC,
    unit TEXT,
    source_file TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT core_fact_consumer_disconnections_uniq
        UNIQUE NULLS NOT DISTINCT (date_id, commodity, payment_method_id, supplier_id, metric_name)
);
CREATE INDEX IF NOT EXISTS idx_core_fact_consumer_disconnections_yc
    ON core_fact_consumer_disconnections (date_id, commodity, metric_name);

CREATE TABLE IF NOT EXISTS core_fact_switching_activity (
    switching_activity_id BIGSERIAL PRIMARY KEY,
    date_id INTEGER NOT NULL REFERENCES core_dim_date(date_id),
    commodity TEXT,
    supplier_size_id BIGINT REFERENCES core_dim_supplier_size(supplier_size_id),
    metric_name TEXT NOT NULL,              -- avg_switching_time_days | total_switches | switching_rate_internal_total_pct ...
    value NUMERIC,
    unit TEXT,
    source_file TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT core_fact_switching_activity_uniq
        UNIQUE NULLS NOT DISTINCT (date_id, commodity, supplier_size_id, metric_name)
);
CREATE INDEX IF NOT EXISTS idx_core_fact_switching_activity_yc
    ON core_fact_switching_activity (date_id, commodity, metric_name);

CREATE TABLE IF NOT EXISTS core_fact_tariff_benchmarks (
    tariff_benchmark_id BIGSERIAL PRIMARY KEY,
    date_id INTEGER NOT NULL REFERENCES core_dim_date(date_id),
    commodity TEXT,
    supplier_group TEXT,                    -- large_legacy | market | other | by_supplier
    supplier_id BIGINT REFERENCES core_dim_supplier(supplier_id),
    payment_method_id BIGINT REFERENCES core_dim_payment_method(payment_method_id),
    tariff_type TEXT,                       -- cheapest | svt_average | svt_supplier | fixed_average | default_cap | day_ahead_baseload | forward_delivery
    metric_name TEXT NOT NULL,
    value NUMERIC,
    unit TEXT,
    source_file TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT core_fact_tariff_benchmarks_uniq
        UNIQUE NULLS NOT DISTINCT (date_id, commodity, supplier_group, supplier_id, payment_method_id, tariff_type, metric_name)
);
CREATE INDEX IF NOT EXISTS idx_core_fact_tariff_benchmarks_yc
    ON core_fact_tariff_benchmarks (date_id, commodity, tariff_type);

CREATE TABLE IF NOT EXISTS core_fact_bill_breakdown (
    bill_breakdown_id BIGSERIAL PRIMARY KEY,
    date_id INTEGER NOT NULL REFERENCES core_dim_date(date_id),
    commodity TEXT,
    payment_method_id BIGINT REFERENCES core_dim_payment_method(payment_method_id),
    supplier_group TEXT,
    component TEXT NOT NULL,                -- wholesale | network | policy | operating | vat | ebit | headroom | debt_related | adjustment | levelisation | total_bill | direct_costs | environmental_social
    metric_name TEXT NOT NULL,              -- bill_component_gbp | bill_breakdown_pct | price_cap_component_gbp
    value NUMERIC,
    unit TEXT,
    source_file TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT core_fact_bill_breakdown_uniq
        UNIQUE NULLS NOT DISTINCT (date_id, commodity, payment_method_id, supplier_group, component, metric_name)
);
CREATE INDEX IF NOT EXISTS idx_core_fact_bill_breakdown_yc
    ON core_fact_bill_breakdown (date_id, commodity, component);

CREATE TABLE IF NOT EXISTS core_fact_complaints_resolution (
    complaints_resolution_id BIGSERIAL PRIMARY KEY,
    date_id INTEGER NOT NULL REFERENCES core_dim_date(date_id),
    supplier_id BIGINT REFERENCES core_dim_supplier(supplier_id),
    supplier_size_id BIGINT REFERENCES core_dim_supplier_size(supplier_size_id),
    metric_name TEXT NOT NULL,              -- complaints_received_per_100k | complaints_resolved_next_day_pct | complaints_resolved_8w_pct | minor_incidents_* | major_incidents_*
    value NUMERIC,
    unit TEXT,
    source_file TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT core_fact_complaints_resolution_uniq
        UNIQUE NULLS NOT DISTINCT (date_id, supplier_id, supplier_size_id, metric_name)
);
CREATE INDEX IF NOT EXISTS idx_core_fact_complaints_resolution_supplier
    ON core_fact_complaints_resolution (supplier_id, metric_name);

CREATE TABLE IF NOT EXISTS core_fact_satisfaction_scores (
    satisfaction_score_id BIGSERIAL PRIMARY KEY,
    date_id INTEGER NOT NULL REFERENCES core_dim_date(date_id),
    supplier_id BIGINT REFERENCES core_dim_supplier(supplier_id),
    supplier_size_id BIGINT REFERENCES core_dim_supplier_size(supplier_size_id),
    commodity TEXT,
    aspect TEXT,                            -- billing_understanding | billing_accuracy | contact_easy | switching_ease | overall | recommend | nps | ...
    metric_name TEXT NOT NULL,
    value NUMERIC,
    unit TEXT,
    source_file TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT core_fact_satisfaction_scores_uniq
        UNIQUE NULLS NOT DISTINCT (date_id, supplier_id, supplier_size_id, commodity, aspect, metric_name)
);
CREATE INDEX IF NOT EXISTS idx_core_fact_satisfaction_scores_supplier
    ON core_fact_satisfaction_scores (supplier_id, metric_name);

CREATE TABLE IF NOT EXISTS core_fact_market_structure (
    market_structure_id BIGSERIAL PRIMARY KEY,
    date_id INTEGER NOT NULL REFERENCES core_dim_date(date_id),
    commodity TEXT,
    metric_name TEXT NOT NULL,              -- active_suppliers | supplier_entries | supplier_exits | continuing_active
    value NUMERIC,
    unit TEXT,
    source_file TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT core_fact_market_structure_uniq
        UNIQUE NULLS NOT DISTINCT (date_id, commodity, metric_name)
);
CREATE INDEX IF NOT EXISTS idx_core_fact_market_structure_yc
    ON core_fact_market_structure (date_id, metric_name);

CREATE TABLE IF NOT EXISTS core_fact_market_share_retail (
    market_share_retail_id BIGSERIAL PRIMARY KEY,
    date_id INTEGER NOT NULL REFERENCES core_dim_date(date_id),
    commodity TEXT NOT NULL,
    supplier_id BIGINT NOT NULL REFERENCES core_dim_supplier(supplier_id),
    segment TEXT,
    share_pct NUMERIC,
    source_file TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT core_fact_market_share_retail_uniq
        UNIQUE (date_id, commodity, supplier_id, segment)
);
CREATE INDEX IF NOT EXISTS idx_core_fact_market_share_retail_dq
    ON core_fact_market_share_retail (date_id, commodity);

CREATE TABLE IF NOT EXISTS core_fact_household_spend (
    household_spend_id BIGSERIAL PRIMARY KEY,
    date_id INTEGER NOT NULL REFERENCES core_dim_date(date_id),
    segment TEXT NOT NULL,                  -- lowest_decile | highest_decile | all_households
    value_pct NUMERIC,
    source_file TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT core_fact_household_spend_uniq
        UNIQUE (date_id, segment)
);

-- Customer accounts by supplier x tariff_type (snapshot grain).
CREATE TABLE IF NOT EXISTS core_fact_customer_accounts_retail (
    customer_accounts_retail_id BIGSERIAL PRIMARY KEY,
    date_id INTEGER NOT NULL REFERENCES core_dim_date(date_id),
    supplier_id BIGINT REFERENCES core_dim_supplier(supplier_id),
    commodity TEXT,
    segment TEXT,                           -- domestic_excl_prepayment | non_price_protected
    tariff_type TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT core_fact_customer_accounts_retail_uniq
        UNIQUE NULLS NOT DISTINCT (date_id, supplier_id, commodity, segment, tariff_type)
);
CREATE INDEX IF NOT EXISTS idx_core_fact_customer_accounts_retail_supplier
    ON core_fact_customer_accounts_retail (supplier_id, commodity);

-- Heating-system overlay (RSL approvals time-series, decarbonisation context).
CREATE TABLE IF NOT EXISTS core_fact_heating_systems (
    heating_systems_id BIGSERIAL PRIMARY KEY,
    date_id INTEGER NOT NULL REFERENCES core_dim_date(date_id),
    component TEXT NOT NULL,                -- air_source_heat_pump | biomass | ground_source_heat_pump | solar_thermal
    value NUMERIC,
    unit TEXT,
    source_file TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT core_fact_heating_systems_uniq
        UNIQUE (date_id, component)
);

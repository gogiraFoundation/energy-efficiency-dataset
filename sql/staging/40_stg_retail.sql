-- =============================================================================
-- Staging tables for the retail / consumer layer.
--
-- Reads from raw_xlsx_supplier_metric, raw_xlsx_retail_timeseries, and
-- raw_xlsx_retail_snapshot (loaded by pipeline/ingest/load_xlsx.py via the
-- RETAIL & CONSUMER section of metadata/xlsx_registry.yaml), normalises
-- supplier names via stg_supplier_alias, and produces typed staging tables
-- ready for sql/core/45_load_facts_retail.sql.
--
-- Re-running drops and rebuilds, mirroring sql/staging/30_stg_market.sql.
-- =============================================================================

-- Defensive shells: stage layer must run cleanly even after a partial xlsx run.
CREATE TABLE IF NOT EXISTS raw_xlsx_supplier_metric (
    period_date DATE, period_label TEXT, year INT, quarter INT,
    supplier_name TEXT, segment TEXT, commodity TEXT, metric_name TEXT,
    value NUMERIC, unit TEXT, source_file TEXT
);
CREATE TABLE IF NOT EXISTS raw_xlsx_retail_timeseries (
    period_date DATE, period_label TEXT, year INT, quarter INT,
    commodity TEXT, payment_method TEXT, supplier_group TEXT, supplier_size TEXT,
    segment TEXT, tariff_type TEXT, component TEXT,
    metric_name TEXT, value NUMERIC, unit TEXT, source_file TEXT
);
CREATE TABLE IF NOT EXISTS raw_xlsx_retail_snapshot (
    year INT, category TEXT, supplier_name TEXT, segment TEXT, commodity TEXT,
    payment_method TEXT, supplier_size TEXT, aspect TEXT, component TEXT,
    tariff_type TEXT, metric_name TEXT, value NUMERIC, unit TEXT, source_file TEXT
);
CREATE TABLE IF NOT EXISTS stg_supplier_alias (
    source_supplier_name TEXT, supplier_name TEXT, supplier_group TEXT,
    supplier_size TEXT, ofgem_supplier_id TEXT, exited_quarter TEXT
);

DROP TABLE IF EXISTS stg_supplier_metric_resolved CASCADE;
DROP TABLE IF EXISTS stg_retail_snapshot_resolved CASCADE;
DROP TABLE IF EXISTS stg_supplier_profits CASCADE;
DROP TABLE IF EXISTS stg_consumer_debt CASCADE;
DROP TABLE IF EXISTS stg_consumer_disconnections CASCADE;
DROP TABLE IF EXISTS stg_switching CASCADE;
DROP TABLE IF EXISTS stg_tariffs_price_cap CASCADE;
DROP TABLE IF EXISTS stg_bill_breakdown CASCADE;
DROP TABLE IF EXISTS stg_complaints CASCADE;
DROP TABLE IF EXISTS stg_satisfaction CASCADE;
DROP TABLE IF EXISTS stg_market_structure CASCADE;
DROP TABLE IF EXISTS stg_market_share_retail CASCADE;
DROP TABLE IF EXISTS stg_smart_selfdisconnect CASCADE;
DROP TABLE IF EXISTS stg_household_spend CASCADE;
DROP TABLE IF EXISTS stg_customer_accounts_retail CASCADE;
DROP TABLE IF EXISTS stg_heating_systems CASCADE;

-- =============================================================================
-- Helper view: alias-resolve raw supplier-grain rows.
-- =============================================================================

CREATE TABLE stg_supplier_metric_resolved AS
SELECT
    r.period_date,
    r.period_label,
    r.year,
    r.quarter,
    COALESCE(a.supplier_name, r.supplier_name) AS supplier_name,
    r.segment,
    r.commodity,
    r.metric_name,
    r.value,
    r.unit,
    r.source_file
FROM raw_xlsx_supplier_metric r
LEFT JOIN stg_supplier_alias a
    ON a.source_supplier_name = r.supplier_name
WHERE r.value IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_stg_supplier_metric_resolved_supplier
    ON stg_supplier_metric_resolved (supplier_name, metric_name, year);

CREATE TABLE stg_retail_snapshot_resolved AS
SELECT
    r.year,
    r.category,
    COALESCE(a.supplier_name, r.supplier_name) AS supplier_name,
    r.segment,
    r.commodity,
    r.payment_method,
    r.supplier_size,
    r.aspect,
    r.component,
    r.tariff_type,
    r.metric_name,
    r.value,
    r.unit,
    r.source_file
FROM raw_xlsx_retail_snapshot r
LEFT JOIN stg_supplier_alias a
    ON a.source_supplier_name = r.supplier_name
WHERE r.value IS NOT NULL;

-- =============================================================================
-- stg_supplier_profits : supplier-level financial metrics
-- (profits by segment, margins, large-legacy aggregates)
-- =============================================================================

CREATE TABLE stg_supplier_profits (
    year INT,
    quarter INT,
    supplier_name TEXT,
    segment TEXT,
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT
);

INSERT INTO stg_supplier_profits
SELECT year, quarter, supplier_name, segment, metric_name, value, unit, source_file
FROM stg_supplier_metric_resolved
WHERE metric_name IN ('profit_million_gbp', 'pretax_domestic_margin_pct')
  AND year IS NOT NULL;

-- Aggregate (segment-level, no supplier identity) from retail timeseries.
INSERT INTO stg_supplier_profits
SELECT year, quarter, NULL AS supplier_name, segment,
       metric_name, value, unit, source_file
FROM raw_xlsx_retail_timeseries
WHERE metric_name IN ('aggregate_profit_billion_gbp',
                      'large_legacy_aggregate_profit_million_gbp')
  AND year IS NOT NULL;

-- =============================================================================
-- stg_consumer_debt : debt levels, accounts in arrears, repayment plans
-- =============================================================================

CREATE TABLE stg_consumer_debt (
    year INT,
    quarter INT,
    commodity TEXT,
    payment_method TEXT,
    supplier_name TEXT,
    component TEXT,
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT
);

INSERT INTO stg_consumer_debt
SELECT year, quarter, commodity, payment_method, NULL::text, component,
       metric_name, value, unit, source_file
FROM raw_xlsx_retail_timeseries
WHERE metric_name IN (
    'avg_debt_no_arrangement_gbp',
    'avg_debt_with_arrangement_gbp',
    'accounts_in_arrears_no_arrangement',
    'accounts_repaying_debt',
    'ppm_debt_repayment_share_pct',
    'debt_value_gt91_days_billion_gbp'
)
AND year IS NOT NULL;

-- Domestic fixed-DD credit balances (everviz / portal extracts).
INSERT INTO stg_consumer_debt
SELECT year, quarter, commodity, payment_method, NULL::text, component,
       metric_name, value, unit, source_file
FROM raw_xlsx_retail_timeseries
WHERE component = 'credit_balance'
  AND metric_name IN (
    'credit_balance_total_bn_gbp',
    'credit_balance_total_rolling12_bn_gbp',
    'credit_balance_household_quarter_avg_gbp',
    'credit_balance_household_rolling12_avg_gbp',
    'credit_balance_quartile_lower_gbp',
    'credit_balance_quartile_median_gbp',
    'credit_balance_quartile_upper_gbp'
  )
  AND year IS NOT NULL;

-- Per-supplier repayment plan length / weekly rate (snapshot facts).
INSERT INTO stg_consumer_debt
SELECT year, NULL::int, commodity, payment_method,
       supplier_name, NULL::text, metric_name, value, unit, source_file
FROM stg_retail_snapshot_resolved
WHERE metric_name IN ('avg_repayment_plan_weeks', 'avg_weekly_repayment_gbp');

-- =============================================================================
-- stg_consumer_disconnections : disconnections for debt + smart self-disconnect
-- =============================================================================

CREATE TABLE stg_consumer_disconnections (
    year INT,
    quarter INT,
    commodity TEXT,
    payment_method TEXT,
    supplier_name TEXT,
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT
);

INSERT INTO stg_consumer_disconnections
SELECT year, quarter, commodity, payment_method,
       NULL::text, metric_name, value, unit, source_file
FROM raw_xlsx_retail_timeseries
WHERE metric_name IN (
    'disconnections_for_debt',
    'smart_ppm_self_disconnect_events',
    'smart_ppm_self_disconnect_customers',
    'smart_ppm_self_disconnect_customers_gt3h'
)
AND year IS NOT NULL;

-- Per-supplier disconnection counts (snapshot).
INSERT INTO stg_consumer_disconnections
SELECT year, NULL::int, commodity, NULL::text,
       supplier_name, metric_name, value, unit, source_file
FROM stg_retail_snapshot_resolved
WHERE metric_name = 'disconnections_for_debt';

-- =============================================================================
-- stg_switching : switching activity, rates, time
-- =============================================================================

CREATE TABLE stg_switching (
    year INT,
    quarter INT,
    commodity TEXT,
    supplier_size TEXT,
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT
);

INSERT INTO stg_switching
SELECT year, quarter, commodity, supplier_size, metric_name, value, unit, source_file
FROM raw_xlsx_retail_timeseries
WHERE metric_name IN (
    'avg_switching_time_days',
    'total_switches',
    'switches_to_other_suppliers',
    'net_gains_other_suppliers',
    'switching_rate_internal_total_pct',
    'switching_rate_external_total_pct',
    'switching_rate_internal_by_tariff_pct',
    'active_suppliers',
    'supplier_entries',
    'supplier_exits',
    'continuing_active'
)
AND year IS NOT NULL;

-- =============================================================================
-- stg_tariffs_price_cap : tariff benchmarks + price cap components
-- =============================================================================

CREATE TABLE stg_tariffs_price_cap (
    year INT,
    quarter INT,
    commodity TEXT,
    payment_method TEXT,
    supplier_group TEXT,
    supplier_name TEXT,
    tariff_type TEXT,
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT
);

INSERT INTO stg_tariffs_price_cap
SELECT year, quarter, commodity, payment_method, supplier_group,
       NULL::text, tariff_type, metric_name, value, unit, source_file
FROM raw_xlsx_retail_timeseries
WHERE metric_name IN (
    'cheapest_tariff_gbp_per_year',
    'tariff_price_gbp_per_year',
    'power_price_day_ahead_baseload',
    'power_price_forward_delivery',
    'gas_price_forward_delivery'
)
AND year IS NOT NULL;

-- Per-supplier tariff snapshot.
INSERT INTO stg_tariffs_price_cap
SELECT year, NULL::int, commodity, NULL::text, NULL::text,
       supplier_name, tariff_type, metric_name, value, unit, source_file
FROM stg_retail_snapshot_resolved
WHERE metric_name = 'tariff_price_gbp_per_year';

-- =============================================================================
-- stg_bill_breakdown : fixed-period bill component breakdowns
-- (price cap components + bill breakdown over time + snapshot bill mix)
-- =============================================================================

CREATE TABLE stg_bill_breakdown (
    year INT,
    quarter INT,
    commodity TEXT,
    payment_method TEXT,
    supplier_group TEXT,
    component TEXT,
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT
);

INSERT INTO stg_bill_breakdown
SELECT year, quarter, commodity, payment_method, supplier_group,
       component, metric_name, value, unit, source_file
FROM raw_xlsx_retail_timeseries
WHERE metric_name IN ('price_cap_component_gbp', 'bill_component_gbp')
  AND year IS NOT NULL
  AND component IS NOT NULL;

-- Snapshot bill breakdown (dual fuel / gas / electricity, % shares).
INSERT INTO stg_bill_breakdown
SELECT year, NULL::int, commodity, NULL::text, NULL::text,
       component, metric_name, value, unit, source_file
FROM stg_retail_snapshot_resolved
WHERE metric_name IN ('bill_breakdown_pct', 'cost_index_yoy_impact_pct');

-- =============================================================================
-- stg_complaints : per-supplier and per-size complaint metrics
-- =============================================================================

CREATE TABLE stg_complaints (
    year INT,
    quarter INT,
    supplier_name TEXT,
    supplier_size TEXT,
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT
);

INSERT INTO stg_complaints
SELECT year, quarter, supplier_name, NULL::text, metric_name, value, unit, source_file
FROM stg_supplier_metric_resolved
WHERE metric_name IN (
    'complaints_received_per_100k',
    'complaints_received_per_10k_small',
    'complaints_resolved_next_day_pct',
    'complaints_resolved_8w_pct'
)
AND year IS NOT NULL;

INSERT INTO stg_complaints
SELECT year, quarter, NULL::text, supplier_size, metric_name, value, unit, source_file
FROM raw_xlsx_retail_timeseries
WHERE metric_name = 'complaints_received_per_100k'
  AND supplier_size IS NOT NULL
  AND year IS NOT NULL;

INSERT INTO stg_complaints
SELECT year, quarter, supplier_name, NULL::text, metric_name, value, unit, source_file
FROM raw_xlsx_supplier_metric
WHERE metric_name = 'fit_complaints_per_1000_accounts'
  AND year IS NOT NULL;

-- Minor & major incidents (snapshot per supplier).
INSERT INTO stg_complaints
SELECT year, NULL::int, supplier_name, NULL::text, metric_name, value, unit, source_file
FROM stg_retail_snapshot_resolved
WHERE metric_name IN (
    'minor_incidents_historical',
    'minor_incidents_current',
    'major_incidents_historical',
    'major_incidents_current'
);

-- =============================================================================
-- stg_satisfaction : satisfaction by aspect and supplier
-- =============================================================================

CREATE TABLE stg_satisfaction (
    year INT,
    quarter INT,
    supplier_name TEXT,
    supplier_size TEXT,
    commodity TEXT,
    aspect TEXT,
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT
);

-- Time-series satisfaction (aspect-named metrics).
INSERT INTO stg_satisfaction
SELECT year, quarter, NULL::text, supplier_size, commodity,
       NULL::text AS aspect, metric_name, value, unit, source_file
FROM raw_xlsx_retail_timeseries
WHERE metric_name LIKE 'satisfaction_%' AND year IS NOT NULL;

-- Six-large supplier snapshot satisfaction (aspect = entity row).
INSERT INTO stg_satisfaction
SELECT year, NULL::int, supplier_name, NULL::text, commodity,
       aspect, metric_name, value, unit, source_file
FROM stg_retail_snapshot_resolved
WHERE metric_name = 'satisfaction_pct';

-- Likelihood-to-recommend / NPS (supplier_size = first column entity).
INSERT INTO stg_satisfaction
SELECT year, NULL::int, NULL::text, supplier_size, NULL::text,
       NULL::text, metric_name, value, unit, source_file
FROM stg_retail_snapshot_resolved
WHERE metric_name IN (
    'nps_detractor_pct', 'nps_passive_pct', 'nps_promoter_pct',
    'nps_score', 'satisfaction_overall_pct'
);

-- =============================================================================
-- stg_market_structure : active suppliers, entries, exits
-- =============================================================================

CREATE TABLE stg_market_structure (
    year INT,
    quarter INT,
    commodity TEXT,
    metric_name TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT
);

INSERT INTO stg_market_structure
SELECT year, quarter, COALESCE(commodity, 'all') AS commodity,
       metric_name, value, unit, source_file
FROM raw_xlsx_retail_timeseries
WHERE metric_name IN ('active_suppliers', 'supplier_entries', 'supplier_exits', 'continuing_active')
  AND year IS NOT NULL;

-- =============================================================================
-- stg_market_share_retail : domestic electricity / gas market shares per quarter
-- =============================================================================

CREATE TABLE stg_market_share_retail (
    year INT,
    quarter INT,
    commodity TEXT,
    supplier_name TEXT,
    segment TEXT,
    share_pct NUMERIC,
    source_file TEXT
);

INSERT INTO stg_market_share_retail
SELECT year, quarter, commodity, supplier_name, segment, value, source_file
FROM stg_supplier_metric_resolved
WHERE metric_name = 'market_share_pct' AND year IS NOT NULL;

-- =============================================================================
-- stg_smart_selfdisconnect : smart-PPM customer self-disconnection metrics
-- (Q2 2022 onwards; covered in stg_consumer_disconnections; this table is a
--  convenience view kept only for symmetry with the dashboard module.)
-- =============================================================================

CREATE TABLE stg_smart_selfdisconnect AS
SELECT year, quarter, commodity, payment_method, metric_name,
       value, unit, source_file
FROM raw_xlsx_retail_timeseries
WHERE metric_name IN (
    'smart_ppm_self_disconnect_events',
    'smart_ppm_self_disconnect_customers',
    'smart_ppm_self_disconnect_customers_gt3h'
);

-- =============================================================================
-- stg_household_spend : energy spend as % of household expenditure
-- =============================================================================

CREATE TABLE stg_household_spend (
    year INT,
    segment TEXT,
    value_pct NUMERIC,
    source_file TEXT
);

INSERT INTO stg_household_spend
SELECT year, segment, value, source_file
FROM raw_xlsx_retail_timeseries
WHERE metric_name = 'household_energy_spend_pct'
  AND year IS NOT NULL;

-- =============================================================================
-- stg_customer_accounts_retail : domestic accounts by supplier x tariff_type
-- =============================================================================

CREATE TABLE stg_customer_accounts_retail (
    year INT,
    supplier_name TEXT,
    commodity TEXT,
    segment TEXT,
    tariff_type TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT
);

INSERT INTO stg_customer_accounts_retail
SELECT year, supplier_name, commodity, segment, tariff_type, value, unit, source_file
FROM stg_retail_snapshot_resolved
WHERE metric_name = 'customer_accounts';

-- =============================================================================
-- stg_heating_systems : RSL heat-pump / biomass approvals over time
-- =============================================================================

CREATE TABLE stg_heating_systems (
    year INT,
    quarter INT,
    component TEXT,
    value NUMERIC,
    unit TEXT,
    source_file TEXT
);

INSERT INTO stg_heating_systems
SELECT year, quarter, component, value, unit, source_file
FROM raw_xlsx_retail_timeseries
WHERE metric_name = 'heating_systems_approved_count'
  AND year IS NOT NULL;

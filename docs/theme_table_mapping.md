# Theme ↔ physical tables (quick reference)

This maps analytical themes to the **actual** `core_*`, `stg_*`, `mart_*`, and `raw.*` objects in the repo. Naming in product docs may use a shorter `fact_*` style; the physical table is what the pipeline and dashboard query.

## Dashboard: object existence checks

Use **`dashboard.db.object_exists`** (not `dashboard.utils`) to test whether a table, view, or materialized view exists. It unions `information_schema.tables`, `information_schema.views`, and `pg_matviews`. When `schema_name` is omitted, it searches **`public`**, then **`raw`**, then **`audit`** so objects moved by `sql/migrations/20260501_schema_qualify_raw_tables.sql` are still found.

## Network & wholesale

| Concept | Physical objects |
|--------|-------------------|
| Reliability, ENS, CML, gas lost | `core_fact_network_reliability`, `stg_network_reliability`, `mart_cost_reliability` |
| Totex, RoRE | `core_fact_financial_performance`, `mart_cost_reliability` |
| Emissions (e.g. SF6) | `core_fact_emissions`, `raw_xlsx_emissions` (fallback) |
| Customer / satisfaction (network) | `core_fact_customer_metrics` |
| Generation mix / market context | `core_fact_market_context`, `mart_market_context`, `raw_xlsx_generation_mix` |
| Prices, volatility, spreads, volumes | `core_fact_market_prices`, `raw_xlsx_market_prices` |
| Wholesale / generation shares & HHI | `core_fact_market_share`, `mart_market_context` |
| Daily auction / spot | `core_fact_daily_prices`, `mart_daily_market_monitoring` |
| Cross-fuel risk | `mart_cross_commodity_risk` |
| Regulatory / allowed return views | `mart_regulatory_performance` |

## Retail & consumer

| Concept | Physical objects |
|--------|-------------------|
| Supplier profit, margins | `core_fact_supplier_financial`, `mart_retail_supplier_health` |
| Debt, arrears, credit balance | `core_fact_consumer_debt`, `mart_retail_consumer_vulnerability` |
| Disconnections, self-disconnect | `core_fact_consumer_disconnections`, `mart_retail_consumer_vulnerability` |
| Switching, active suppliers | `core_fact_switching_activity`, `core_fact_market_structure`, `mart_retail_competition` |
| Tariffs, price cap | `core_fact_tariff_benchmarks`, `core_fact_bill_breakdown`, `mart_retail_affordability` |
| Complaints | `core_fact_complaints_resolution`, `mart_retail_complaints` |
| Satisfaction / NPS | `core_fact_satisfaction_scores`, `mart_retail_satisfaction` |
| Retail HHI / shares | `core_fact_market_share_retail` |
| Customer accounts (annual) | `core_fact_customer_accounts_retail` |
| Heating approvals (RHI-style) | `core_fact_heating_systems` |

## Social & policy schemes

| Concept | Physical objects |
|--------|-------------------|
| Warm Home Discount | `stg_whd_*`, `mart_warm_home_discount` |
| ECO, BUS, admin queues, scheme KPIs | `core_fact_scheme_metric`, `mart_scheme_metric`, `raw_xlsx_scheme_metric` |

## Macro & decarbonisation

| Concept | Physical objects |
|--------|-------------------|
| DUKES primary energy, GDP ratio | `stg_dukes_primary_consumption`, `stg_dukes_*` (other chapters) |
| Renewables deployment / capacity | `mart_renewables_deployment`, `mart_dukes_official_renewables` |
| ROCs / obligation | `core_fact_renewables_obligation`, `mart_renewables_obligation` |
| ENS vs LCREE narrative | `mart_decarbonisation_narrative`, `stg_lcree`, `core_fact_network_reliability` |

## Cross-layer

| Concept | Physical objects |
|--------|-------------------|
| Bill stack vs wholesale | `mart_cross_layer_cost_to_consumer` |
| Volatility vs complaints | `mart_cross_layer_volatility_complaints` |
| Supplier quality bridge | `mart_cross_layer_supplier_quality` |

## Economic impact

| Concept | Physical objects |
|--------|-------------------|
| Regional GVA, ENS allocation, output-at-risk | `mart_economic_impact` |
| Inputs | `core_fact_regional_gva`, `core_fact_energy_intensity`, `core_fact_input_output`, `core_fact_network_reliability` |

## Raw JSON ingest (Ofgem / ONS)

Typed tables live in schema **`raw`** (see `sql/raw/00_create_raw_tables.sql`): e.g. `raw.raw_ofgem_ens`, `raw.raw_ons_regional_gva`, `raw.raw_daily_market_prices`. Excel workbook extracts use **`raw_xlsx_*`** in **`public`** unless you standardise them later.

## Compatibility views

`sql/core/28_aliases.sql` defines `fact_*` **views** over `core_fact_*`. The Streamlit app queries **`core_*`** directly; aliases are optional for ad hoc SQL.

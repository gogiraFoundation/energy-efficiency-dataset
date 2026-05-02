# Data sources audit (Ofgem & related additions)

Audit of the 24 datasets evaluated alongside the 38-file Ofgem Data Portal set
and the retail facet (`data/ofgem_data_portal_xlsx_facet_1609_supply_retail/`).
Each entry resolves to one of three statuses:

- **Ingested** — already loaded by the pipeline; cites the actual table the
  loader writes. Typed XLSX rows live in `public.raw_xlsx_*`; CSV/JSONB rows
  live in `raw.raw_ofgem_*` / `raw.raw_ons_*`. See
  `docs/platform_design.md` for the two parallel paths.
- **To add** — included in the renewables/WHD/major-incidents PR; backed by
  new registry entries in `metadata/xlsx_registry.yaml` and new typed raw
  tables in `sql/raw/07_create_raw_xlsx_renewables_whd.sql`.
- **Skip** — duplicates of the Ingested rows or out-of-scope.

## RIIO network performance

| Dataset | Status | Where it lands |
|---------|--------|----------------|
| Return on regulatory equity — Gas distribution (RIIO-GD1) | Ingested | `raw_xlsx_rore` (xlsx path) and `raw.raw_ofgem_rore` (CSV path); `Return_on_regulatory_equity_Gas_distribution_RIIO-GD1.xlsx` registered in `metadata/xlsx_registry.yaml` |
| Expenditure vs allowance — Gas distribution (RIIO-GD1) | Ingested | `raw_xlsx_expenditure` (xlsx) and `raw.raw_ofgem_expenditure` (CSV) |
| Volume of gas lost from the distribution network (RIIO-GD1) | Ingested | `raw_xlsx_reliability`, `metric_name = gas_lost_volume`; `Volume_of_gas_lost_from_the_distribution_network_RIIO-GD1.xlsx` |

## Wholesale market context

| Dataset | Status | Where it lands |
|---------|--------|----------------|
| Electricity generation mix by quarter and fuel source (GB) | Ingested | `raw_xlsx_generation_mix` (parser `time_series_long`) |
| Gas bid-offer spreads by contract type (GB) | Ingested | `raw_xlsx_market_prices`, `commodity = gas`, `metric_name = bid_offer_spread` |
| Electricity bid-offer spreads by contract type (GB) | Ingested | `raw_xlsx_market_prices`, `commodity = electricity`, `metric_name = bid_offer_spread` |
| Gas trading volumes and monthly churn ratio by platform (GB) | Ingested | `raw_xlsx_market_volumes`, `commodity = gas` |
| Electricity trading volumes (per platform/month) | Ingested | `raw_xlsx_market_volumes`, `commodity = electricity` |

## Retail / consumer

| Dataset | Status | Where it lands |
|---------|--------|----------------|
| Average switching time for domestic customers (GB) | Ingested | `raw_xlsx_retail_timeseries` → `stg_switching` → `core_fact_switching_activity` → `mart_retail_competition` |
| Number of domestic electricity / gas customer accounts by supplier (excl. prepayment) | Ingested | `raw_xlsx_retail_timeseries` (and snapshot variants) → `stg_customer_accounts_retail` |
| Domestic complaints received by small-sized suppliers per 10 000 accounts | Ingested | `raw_xlsx_supplier_metric`, `metric_name = complaints_received_per_10k_small` |
| Minor incidents | Ingested | `raw_xlsx_retail_snapshot`, metrics `minor_incidents_historical` / `minor_incidents_current` |
| Major incidents | **To add** | New registry entry mirroring `Minor_incidents.xlsx` (parser `category_aspect_snapshot`); same `raw_xlsx_retail_snapshot` table; metrics `major_incidents_historical` / `major_incidents_current`; staging filter extended in `sql/staging/40_stg_retail.sql`. |

## Renewables (MCS-style deployment)

| Dataset | Status | Where it lands |
|---------|--------|----------------|
| Total installed capacity (kW) by technology type | **To add** | `raw_xlsx_renewables`, `metric_name = capacity_kw` |
| Installations by technology type | **To add** | `raw_xlsx_renewables`, `metric_name = installations` |
| Installations by technology per quarter (non-cumulative) | **To add** | `raw_xlsx_renewables`, `quarter NOT NULL`, `metric_name = installations` |
| Capacity (kW) by technology per quarter | **To add** | `raw_xlsx_renewables`, `quarter NOT NULL`, `metric_name = capacity_kw` |
| Regional breakdown of % share of installations and TIC | **To add** | `raw_xlsx_renewables`, `region NOT NULL`, `metric_name IN (capacity_kw, installations, share_pct)` |
| Total installed capacity (kW) by installation type | **To add** | `raw_xlsx_renewables`, `installation_type NOT NULL`, `metric_name = capacity_kw` |

Downstream: `sql/staging/45_stg_renewables.sql` →
`sql/marts/55_mart_renewables_deployment.sql` → dashboard page
**Networks > Renewables deployment**.

### DUKES Chapter 6 (official renewables statistics)

DESNZ [renewable sources of energy — Chapter 6](https://www.gov.uk/government/statistics/renewable-sources-of-energy-chapter-6-digest-of-united-kingdom-energy-statistics-dukes)
Excel tables are registered in `metadata/dukes_registry.yaml` under `chapter6`, downloaded during **`pipeline/ingest/load_dukes`** into `raw/<dukes_dir>/`, parsed into **`stg_dukes_chapter6`**, and surfaced via **`mart_dukes_official_renewables`** (`sql/marts/56_mart_dukes_official_renewables.sql`) on the same dashboard page.

## Warm Home Discount (WHD)

| Dataset | Status | Where it lands |
|---------|--------|----------------|
| Distribution of expenditure by year (%) — England & Wales | **To add** | `raw_xlsx_whd`, `nation = 'England and Wales'`, `metric_name = expenditure_pct` |
| Distribution of expenditure by year (%) — Scotland | **To add** | `raw_xlsx_whd`, `nation = 'Scotland'`, `metric_name = expenditure_pct` |
| Scheme value since 2002 | **To add** | `raw_xlsx_whd`, `metric_name = scheme_value_mgbp` |
| How suppliers met total obligations since 2002 | **To add** | `raw_xlsx_whd`, `obligation_method NOT NULL`, `metric_name = obligation_amount_mgbp` |
| Funds redistributed to suppliers since 2002 | **To add** | `raw_xlsx_whd`, `supplier_name NOT NULL`, `metric_name = redistributed_mgbp` |

Downstream: `sql/staging/46_stg_warm_home_discount.sql` →
`sql/marts/66_mart_warm_home_discount.sql` → dashboard page
**Retail > Warm Home Discount**.

## Skip

- Any RIIO-GD1 file already enumerated above (avoid duplicate registration).
- Generation mix / bid-offer / trading volumes — already in the pipeline.
- Power-specific files already covered by the 38-file ingest set.

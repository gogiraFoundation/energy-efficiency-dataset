# Data-Contract Checklist (Manual/Placeholder Source Files)

Use this checklist before placing files into `raw/override/` (or before running `python -m pipeline.dry_run_execution --execute`).

> **Scope note.** This checklist covers the **CSV/JSONB ingest path** (`pipeline/ingest/load_raw.py`), which writes into the `raw.raw_ofgem_*` and `raw.raw_ons_*` tables defined in `sql/raw/00_create_raw_tables.sql`. The **38-file Ofgem Data Portal XLSX path** (`pipeline/ingest/load_xlsx.py`) and the **retail facet XLSX path** instead write into typed `raw_xlsx_*` tables in the `public` schema (e.g. `raw_xlsx_generation_mix`, `raw_xlsx_market_prices`, `raw_xlsx_reliability`, `raw_xlsx_retail_snapshot`). Those flows are registry-driven via `metadata/xlsx_registry.yaml` and are not subject to the column contracts below. See `docs/data_sources_audit.md` for the dataset-by-dataset map.

## Analytics conventions (marts / dashboard)

- **HHI (Herfindahl–Hirschman Index):** classic **0–10,000** scale, \( \sum s_i^2 \) where \( s_i \) are percentage shares (0–100). Do not mix with normalized 0–1 HHI in charts.
- **`mart_economic_impact`:** ENS is **allocated** from a single national yearly total; summed `ens_mwh_in_region_industry` reconciles to core reliability ENS by year.
- **Cross-layer marts:** interpret as correlation / narrative support unless lagged columns are explicitly used in analysis.

## Global contract rules

- File format: `.csv` (for dry-run path)
- Header convention: `snake_case`
- Grain: mixed (annual ONS/Ofgem + daily market monitoring)
- Numeric domains: non-negative for ENS, spend, emissions, intensity, GVA, LCREE turnover
- Primary uniqueness expectations:
  - Network series: `(year, company_name, network_sector)`
  - Industry series: `(year, sic_code)`
  - Regional GVA: `(year, region_code, sic_code)`
  - Input-output shares: `(year, sic_code, commodity)`
  - Daily prices: `(date, commodity, source_name, metric_name)`

## Source-by-source contracts

### `ofgem_ens_et.csv` -> `raw_ofgem_ens`
- Required columns:
  - `year`
  - `company_name`
  - `network_sector` (`ET`/`ED`/`GT`/`GD`)
  - `ens_mwh`
- Optional but recommended:
  - `customer_interruptions`
  - `minutes_lost`
  - `gas_interruption_volume`
  - `gas_lost_volume`

### `ofgem_expenditure_allowance.csv` -> `raw_ofgem_expenditure`
- Required columns:
  - `year`
  - `company_name`
  - `network_sector`
  - `actual_totex_million_gbp` (> 0)
  - `totex_allowance_million_gbp` (> 0)
- Optional:
  - `rore_pct`

### `ofgem_rore.csv` -> `raw_ofgem_rore`
- Required columns:
  - `year`
  - `company_name`
  - `network_sector`
  - `rore_pct`

### `ofgem_customer_metrics.csv` -> `raw_ofgem_customer_metrics`
- Required columns:
  - `year`
  - `company_name`
  - `network_sector`
  - `cost_per_customer_gbp`
  - `satisfaction_score`
- Optional:
  - `geography_code` (defaults to `GB` in staging if absent)

### `ofgem_emissions.csv` -> `raw_ofgem_emissions`
- Required columns:
  - `year`
  - `company_name`
  - `network_sector`
  - `sf6_kg`
  - `carbon_footprint_tco2e`

### `ons_energy_intensity.csv` -> `raw_ons_energy_intensity`
- Required columns:
  - `year`
  - `sic_code`
  - `kwh_per_gva`
  - `energy_intensity_index`
- Optional:
  - `industry_name`

### `ons_sector_fuel_use.csv` -> `raw_ons_sector_fuel_use`
- Required columns:
  - `year`
  - `sic_code`
  - `electricity_pct`
  - `gas_pct`
- Validation note:
  - Recommended `electricity_pct + gas_pct <= 1.0` (if these represent total shares)
- Source note:
  - Derived from ONS **Energy use: total** workbook (direct/reallocated energy use by SIC). Pre-transform the workbook into the contract above before placing it in `raw/override/ons_sector_fuel_use.csv`.

### `ons_regional_gva.csv` -> `raw_ons_regional_gva`
- Required columns:
  - `year`
  - `region_code` (must map to `core_dim_geography.geography_code`)
  - `sic_code`
  - `gva_million_gbp`

### `ons_lcree.csv` -> `raw_ons_lcree`
- Required columns:
  - `year`
  - `lcree_turnover_million_gbp`

### `ons_intermediate_consumption.csv` -> `raw_ons_intermediate_consumption`
- Required columns:
  - `year`
  - `sic_code`
  - `commodity`
  - `intermediate_consumption_share`
- Optional:
  - `industry_name`
  - `intermediate_consumption_value`

### `ons_gas_sap_daily.csv` / `elexon_system_price_daily.csv` -> `raw_daily_market_prices`
- Required columns:
  - `date` (ISO `YYYY-MM-DD`)
  - `commodity` (`gas` or `electricity`)
  - `metric_name`
  - `value`
- Optional:
  - `source_name`
  - `unit`

## Quick dry-run commands

- Generate placeholder files and validate required contracts only:
  - `python -m pipeline.dry_run_execution`
- Generate placeholders and execute full stage sequence:
  - `python -m pipeline.dry_run_execution --execute`

## Operational note

- The `--execute` path requires DB connectivity and the password env var configured in `pipeline/config/settings.yaml` (`UK_ENERGY_DB_PASSWORD` by default).

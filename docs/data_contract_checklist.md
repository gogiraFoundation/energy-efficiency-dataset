# Data-Contract Checklist (Manual/Placeholder Source Files)

Use this checklist before placing files into `raw/override/` (or before running `python -m pipeline.dry_run_execution --execute`).

## Global contract rules

- File format: `.csv` (for dry-run path)
- Header convention: `snake_case`
- Grain: annual records (`year`)
- Numeric domains: non-negative for ENS, spend, emissions, intensity, GVA, LCREE turnover
- Primary uniqueness expectations:
  - Network series: `(year, company_name, network_sector)`
  - Industry series: `(year, sic_code)`
  - Regional GVA: `(year, region_code, sic_code)`

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

## Quick dry-run commands

- Generate placeholder files and validate required contracts only:
  - `python -m pipeline.dry_run_execution`
- Generate placeholders and execute full stage sequence:
  - `python -m pipeline.dry_run_execution --execute`

## Operational note

- The `--execute` path requires DB connectivity and the password env var configured in `pipeline/config/settings.yaml` (`UK_ENERGY_DB_PASSWORD` by default).

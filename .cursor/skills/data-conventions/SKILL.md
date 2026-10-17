---
name: data-conventions
description: >
  Data pipeline and dashboard conventions for the UK energy warehouse. Covers
  raw → staging → core → marts layers, pinned Ofgem/ONS/DUKES sources with SHA-256
  and meta/provenance, Open Government Licence attribution, SQL/schema checks
  before advancing layers, idempotent orchestrated loads, no raw data or secrets
  in git, Streamlit pages reading marts only, and pytest/dry-run checks. Use when
  adding or changing ingestion, SQL transforms, marts, dashboard queries, or
  reviewing data code.
---

# Data conventions (uk-energy-eff)

Follow these rules on every change that touches data ingestion, transforms, storage, charts or dashboard pages. If the README or code clearly contradicts a rule, do what the repo does and point out the mismatch. Do not "fix" it on your own.

Never open, read, print or grep `.env*`, `*.key` or `.streamlit/secrets.toml`.

## 1. Pipeline layers

Data moves forward one layer at a time. Never skip a layer, and never write back into an earlier one.

**raw → staging → core → marts** (PostgreSQL schemas / SQL folders)

| Layer | Role | Location |
| --- | --- | --- |
| raw | Files/tables exactly as downloaded or land as JSONB / `raw_*` / `raw_xlsx_*`. Never edited ad hoc. | `raw/` downloads; DB via ingest; SQL under `sql/raw/` |
| staging | Typed, renamed (`stg_*`), no business logic | `sql/staging/` |
| core | Conformed dims/facts (`core_dim_*` / `core_fact_*`) with stable keys | `sql/core/` (+ `sql/checks/`) |
| marts | Aggregates for the app (`mart_*` materialized views) | `sql/marts/` |

Streamlit (`dashboard/`) reads **marts only** (via `dashboard/queries*.py`), not raw/staging.

Orchestration (from README):

```bash
python -m pipeline.orchestrate ingest
python -m pipeline.orchestrate xlsx
python -m pipeline.orchestrate staging
python -m pipeline.orchestrate core
python -m pipeline.orchestrate marts
# or
python -m pipeline.orchestrate full_refresh
```

Column names are snake_case. Units go in the name when not obvious. Dates ISO 8601 / timezone-aware where time matters. Geography codes stay strings.

## 2. Pinned sources and provenance

Pinned sources live in the ingest registry / `pipeline/config/` (see `settings.yaml` and ingest modules). Prefer fixed release URLs over floating "latest".

After download, record SHA-256 and provenance. Prefer a `meta.json` (or the repo's existing metadata under `metadata/`) with at least: `source_name`, `publisher`, `source_url`, `release`, `retrieved_at`, `sha256`, `licence`, `attribution`, `produced_by`, `inputs`, `row_count`.

Only change a pin in a dedicated commit that explains why.

## 3. Licensing and attribution

ONS / OGL-backed pages and charts must show Open Government Licence attribution (publisher line + OGL notice where required). Extra notices (OS/Royal Mail) belong in metadata and the UI. Do not add a source whose licence is unclear — report it.

## 4. Schema contracts and validation before load

This repo uses **SQL checks** under `sql/checks/` and `sql/validation/`, plus dry-runs (`python -m pipeline.dry_run_execution`, `pipeline.dry_run_retail`). **pandera is not a dependency** — do not add it without asking. Use the existing SQL/validation scripts and plain Python checks.

Validate before writing the next layer. Failed checks write nothing and name the dataset/column.

## 5. Idempotent loads

Re-running orchestrate steps with the same inputs must not duplicate rows. Prefer replace/refresh of the target layer (materialized-view refresh for marts). Wall-clock timestamps belong in provenance metadata, not fact rows.

## 6. What never goes into git

Never commit raw downloads, caches, or DB dumps. Keep `raw/` downloads and secrets out of git. Never commit secrets. Small fixtures only under an agreed tests path if/when tests exist.

## 7. Streamlit and chart conventions

App root: `dashboard/` (`streamlit run dashboard/app.py`).

**Gaps vs shared template:** there is **no** `chart_theme.py` / `ST_WIDTH` yet. Prefer extracting shared colours/widths into a theme module when touching charts; until then, keep styles consistent with existing `dashboard/styles.py` / `plots.py` and cite sources in captions.

Pages read marts only; use `st.cache_data` on loaders. Missing data is missing, not zero. Axis labels include units.

## 8. Tests

There is **no** `tests/` tree yet. Use dry-runs and SQL checks before finishing. When adding tests, put them under `tests/` and run `pytest`. Prefer fixtures over network.

## Agent working rules

Read README + `pipeline/` + `sql/` before changing anything. Small reviewable changes. Ask before new dependencies, pin changes, or published schema changes.

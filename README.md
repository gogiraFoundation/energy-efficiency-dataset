# UK Energy Analytics Dataset

End-to-end analytics pipeline and dashboard for **UK energy** themes: **network cost vs reliability**, **economic exposure**, **wholesale / retail market context**, **consumer and supplier retail health**, and **cross-layer** views. Source data comes primarily from **Ofgem** (CSV/JSON and Data Portal XLSX), **ONS**-style extracts, **DUKES** (macro energy statistics), and related curated mappings.

The stack is **PostgreSQL** (raw → staging → core dimensions/facts → materialized-view marts) plus a **Streamlit** dashboard that reads the same database.

---

## Features

- **Layered warehouse**: `raw_*` → `stg_*` → `core_dim_*` / `core_fact_*` → `mart_*` materialized views.
- **Orchestrated loads**: fetch/registry-driven ingest, typed XLSX loads, SQL folders executed in numeric order (`10_*.sql`, …).
- **Analytics marts** (examples): `mart_cost_reliability`, `mart_economic_impact`, `mart_market_context`, retail marts (`mart_retail_*`), cross-layer marts (`mart_cross_layer_*`), `mart_daily_market_monitoring`.
- **Streamlit UI**: exploratory charts and themed sections wired to marts (`dashboard/`).
- **Quality tooling**: SQL checks under `sql/checks/`, validation scripts under `sql/validation/`, optional health scripts.

---

## Requirements

- **PostgreSQL 15+** (SQL uses `MERGE`; Postgres 16 is used in Docker Compose).
- **Python 3** with dependencies needed by `pipeline/` and `dashboard/` (install via your environment; use a `venv` locally).
- Network access when running **`ingest`** / **`full_refresh`** to fetch configured sources.

---

## Quick start

### 1. Clone and configure environment

```bash
cp .env.example .env
# Edit .env: set UK_ENERGY_DB_PASSWORD (and optionally UK_ENERGY_DB_* overrides).
```

`.env` is loaded by Docker Compose, the pipeline (`pipeline/config/loader.py`), and the dashboard (`dashboard/config.py`). For Streamlit you can set **`DATABASE_URL`** **or** **`UK_ENERGY_DB_PASSWORD`** with **`UK_ENERGY_DB_HOST`** / **`UK_ENERGY_DB_PORT`** / **`UK_ENERGY_DB_NAME`** / **`UK_ENERGY_DB_USER`** (see `.env.example`).

Defaults align with `pipeline/config/settings.yaml` (`dbname`: `uk_energy`, user: `uk_energy_user`, password from `UK_ENERGY_DB_PASSWORD`).

### 2. Start PostgreSQL (recommended)

From the repo root:

```bash
docker compose up -d
```

Ensure the **host port** in `.env` matches `UK_ENERGY_DB_PORT` if you map a non-default port (e.g. `55432:5432`).

### 3. Run the pipeline

```bash
python -m pipeline.orchestrate full_refresh
```

Stages can be run individually:

| Command | Purpose |
|--------|---------|
| `python -m pipeline.orchestrate ingest` | Fetch sources, load JSONB raw tables, DUKES staging |
| `python -m pipeline.orchestrate xlsx` | Load Ofgem Data Portal XLSX into typed `raw_xlsx_*` tables |
| `python -m pipeline.orchestrate staging` | Run `sql/staging/*.sql` |
| `python -m pipeline.orchestrate core` | Run `sql/core/*.sql` and `sql/checks/*.sql` |
| `python -m pipeline.orchestrate marts` | Run `sql/marts/*.sql` (refresh materialized views) |

Order matters: **`full_refresh`** chains **ingest → xlsx → staging → core → marts**.

### 4. Run the dashboard

From the **repository root** (required for imports):

```bash
./scripts/run_dashboard.sh
# Optional:
./scripts/run_dashboard.sh --server.port 8502
```

The app entrypoint is `dashboard/app.py`.

---

## Repository layout

| Path | Purpose |
|------|---------|
| `pipeline/` | Orchestrator, ingest, config (`pipeline/config/settings.yaml`), logging |
| `metadata/` | Source registry (`source_registry.yaml`), XLSX/registry YAML, entity mappings (company, geography, SIC, supplier) |
| `sql/raw/` | Raw DDL |
| `sql/staging/` | Staging transforms (`stg_*`) |
| `sql/core/` | Dimensions, facts, loads, aliases |
| `sql/checks/` | Data-quality SQL |
| `sql/marts/` | Materialized-view marts (`mart_*`) |
| `sql/migrations/` | Schema migrations |
| `dashboard/` | Streamlit app, queries, plots, filters |
| `docs/` | Design notes (`platform_design.md`), data contracts (`data_contract_checklist.md`) |
| `docker-compose.yml` | Local Postgres 16 service |
| `scripts/` | Dashboard launcher and helpers |

---

## Configuration

- **`pipeline/config/settings.yaml`**: DB connection template, paths (`raw_dir`, `log_dir`, …), pipeline window (`start_year` / `end_year`), `fail_fast`.
- **Secrets**: never commit `.env`; use `.env.example` as a template.
- **Sources**: driven by `metadata/source_registry.yaml` and related ingest code under `pipeline/ingest/`.

---

## Documentation

- **`docs/platform_design.md`** — architecture (raw → marts), ENS/economic impact joins, daily market module, DUKES macro context, dry-run commands.
- **`docs/data_contract_checklist.md`** — expected columns and contracts per source.

**Convention note:** Some dashboards use **HHI on the classic 0–10,000 scale** (percent shares squared); the retail supplier-health mart uses **normalized 0–1** HHI. See `docs/platform_design.md` and mart definitions under `sql/marts/`.

---

## Operations & troubleshooting

- **Logs**: `log/pipeline/` (see `paths.log_dir` in settings).
- **Dry runs / smoke tests** (see `docs/platform_design.md`): `python -m pipeline.dry_run_execution`, optional `--execute`, retail dry-run, etc.
- **Database client**: `psql` or any Postgres client; numbered SQL files are applied in sorted order by the orchestrator.
- **Health**: `sql/checks/healthcheck.sql` exists for row-count style checks; `health_check.sh` in repo targets Streamlit uptime monitoring (adjust URLs/ports for your deployment).

---

## License / attribution

If you publish this repo, add your preferred license and cite **Ofgem**, **ONS**, **DESNZ/DUKES**, and other data providers per their terms.

---

## Contributing

Use focused PRs; match existing SQL naming (`NN_topic.sql`), pipeline patterns, and dashboard query modules under `dashboard/`.

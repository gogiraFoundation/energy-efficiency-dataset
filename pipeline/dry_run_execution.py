from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
from pathlib import Path

from pipeline.config.loader import load_settings
from pipeline.ingest.load_raw import RAW_TABLE_EXPECTED_COLUMNS


SAMPLE_ROWS_BY_SOURCE = {
    "ofgem_ens_et": [
        {
            "year": 2021,
            "company_name": "National Grid Electricity Transmission",
            "network_sector": "ET",
            "ens_mwh": 120.5,
            "customer_interruptions": 42,
            "minutes_lost": 3.7,
            "gas_interruption_volume": 0,
            "gas_lost_volume": 0,
        }
    ],
    "ofgem_expenditure_allowance": [
        {
            "year": 2021,
            "company_name": "National Grid Electricity Transmission",
            "network_sector": "ET",
            "actual_totex_million_gbp": 1450.3,
            "totex_allowance_million_gbp": 1500.0,
            "rore_pct": 10.7,
        }
    ],
    "ofgem_rore": [
        {
            "year": 2021,
            "company_name": "National Grid Electricity Transmission",
            "network_sector": "ET",
            "rore_pct": 10.7,
        }
    ],
    "ofgem_customer_metrics": [
        {
            "year": 2021,
            "company_name": "National Grid Electricity Transmission",
            "network_sector": "ET",
            "geography_code": "GB",
            "cost_per_customer_gbp": 126.2,
            "satisfaction_score": 8.4,
        }
    ],
    "ofgem_emissions": [
        {
            "year": 2021,
            "company_name": "National Grid Electricity Transmission",
            "network_sector": "ET",
            "sf6_kg": 52.2,
            "carbon_footprint_tco2e": 10300.0,
        }
    ],
    "ons_energy_intensity": [
        {
            "year": 2021,
            "sic_code": "C",
            "kwh_per_gva": 0.84,
            "energy_intensity_index": 116.0,
            "industry_name": "Manufacturing",
        }
    ],
    "ons_sector_fuel_use": [
        {
            "year": 2021,
            "sic_code": "C",
            "electricity_pct": 0.63,
            "gas_pct": 0.31,
        }
    ],
    "ons_regional_gva": [
        {
            "year": 2021,
            "region_code": "E12000007",
            "sic_code": "C",
            "gva_million_gbp": 52000.0,
        }
    ],
    "ons_lcree": [
        {
            "year": 2021,
            "lcree_turnover_million_gbp": 48000.0,
        }
    ],
}


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"No sample rows provided for {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def run_command(command: list[str]) -> None:
    print(f"[dry-run] executing: {' '.join(command)}")
    result = subprocess.run(command, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout)
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr)
        raise RuntimeError(f"Command failed: {' '.join(command)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dry-run helper for full UK energy pipeline flow.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run ingest -> staging -> core -> marts after creating placeholder files.",
    )
    args = parser.parse_args()

    settings = load_settings()
    registry_path = Path(settings["sources"]["registry_file"])
    override_dir = Path(settings["paths"]["override_dir"])

    import yaml

    with registry_path.open("r", encoding="utf-8") as f:
        registry = yaml.safe_load(f)["sources"]

    print("[dry-run] creating placeholder manual source files in raw/override")
    for source in registry:
        source_id = source["source_id"]
        rows = SAMPLE_ROWS_BY_SOURCE.get(source_id)
        if rows is None:
            print(f"[dry-run] warning: no sample row configured for {source_id}, skipping")
            continue

        file_path = override_dir / f"{source_id}.csv"
        write_csv(file_path, rows)

        expected = RAW_TABLE_EXPECTED_COLUMNS[source["raw_table"]]
        missing = [col for col in expected if col not in rows[0]]
        if missing:
            raise ValueError(f"{source_id}: sample file missing required columns: {missing}")
        print(f"[dry-run] ok contract seed: {file_path}")

    print("[dry-run] placeholder data contracts satisfied for required columns")

    if not args.execute:
        print("[dry-run] execution skipped. Re-run with --execute to run full pipeline stages.")
        return

    db_password_env = settings["database"]["password_env_var"]
    if not os.getenv(db_password_env):
        raise EnvironmentError(
            f"Missing required DB env var '{db_password_env}'. Set it before running --execute."
        )

    stages = ["ingest", "xlsx", "staging", "core", "marts"]
    for stage in stages:
        run_command([sys.executable, "-m", "pipeline.orchestrate", stage])
    print("[dry-run] completed ingest -> xlsx -> staging -> core -> marts")


if __name__ == "__main__":
    main()

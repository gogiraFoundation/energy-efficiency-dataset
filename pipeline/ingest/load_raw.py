from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from pipeline.utils.validators import check_non_negative, null_rate, require_columns, standardize_columns


RAW_TABLE_EXPECTED_COLUMNS = {
    "raw_ofgem_ens": ["year", "company_name", "network_sector", "ens_mwh"],
    "raw_ofgem_expenditure": ["year", "company_name", "network_sector", "actual_totex_million_gbp", "totex_allowance_million_gbp"],
    "raw_ofgem_rore": ["year", "company_name", "network_sector", "rore_pct"],
    "raw_ofgem_customer_metrics": ["year", "company_name", "network_sector", "cost_per_customer_gbp", "satisfaction_score"],
    "raw_ofgem_emissions": ["year", "company_name", "network_sector", "sf6_kg", "carbon_footprint_tco2e"],
    "raw_ons_energy_intensity": ["year", "sic_code", "kwh_per_gva", "energy_intensity_index"],
    "raw_ons_sector_fuel_use": ["year", "sic_code", "electricity_pct", "gas_pct"],
    "raw_ons_regional_gva": ["year", "region_code", "sic_code", "gva_million_gbp"],
    "raw_ons_lcree": ["year", "lcree_turnover_million_gbp"],
}


def _load_registry(settings: dict) -> list[dict]:
    registry_path = Path(settings["sources"]["registry_file"])
    with registry_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("sources", [])


def _read_tabular(file_path: Path) -> pd.DataFrame:
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(file_path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(file_path)
    if suffix == ".parquet":
        return pd.read_parquet(file_path)
    raise ValueError(f"Unsupported file format: {suffix}")


def _upsert_raw(client, table_name: str, df: pd.DataFrame, source_id: str, logger) -> None:
    stage_table = f"{table_name}_stage"
    client.execute(f"DROP TABLE IF EXISTS {stage_table};")
    columns_sql = ", ".join([f"{col} text" for col in df.columns])
    client.execute(f"CREATE TEMP TABLE {stage_table} ({columns_sql});")

    with client._conn.cursor() as cur:
        rows = [tuple(None if pd.isna(v) else str(v) for v in row) for row in df.to_numpy()]
        placeholders = ",".join(["%s"] * len(df.columns))
        insert_sql = f"INSERT INTO {stage_table} ({','.join(df.columns)}) VALUES ({placeholders})"
        cur.executemany(insert_sql, rows)

    key_cols = [c for c in ["year", "company_name", "network_sector", "sic_code", "region_code"] if c in df.columns]
    if key_cols:
        key_expr = ", ".join([f"coalesce(src.{c}, '')" for c in key_cols])
    else:
        key_expr = "''"

    merge_sql = f"""
        MERGE INTO {table_name} AS tgt
        USING (
            SELECT *, now()::timestamp AS loaded_at,
                   %s::text AS source_id,
                   to_jsonb(src1.*) AS source_payload
            FROM {stage_table} src1
        ) AS src
        ON tgt.natural_key = md5(concat_ws('||', {key_expr}))
        WHEN MATCHED THEN UPDATE SET
            payload = src.source_payload,
            loaded_at = src.loaded_at,
            source_id = src.source_id
        WHEN NOT MATCHED THEN INSERT (natural_key, payload, loaded_at, source_id)
        VALUES (md5(concat_ws('||', {key_expr})), src.source_payload, src.loaded_at, src.source_id);
    """

    client.execute(merge_sql, (source_id,))
    logger.info("Upserted raw table %s (%s rows)", table_name, len(df))


def load_all_raw_tables(settings: dict, client, logger) -> None:
    client.execute_file("sql/raw/00_create_raw_tables.sql")
    registry = _load_registry(settings)
    raw_download_dir = Path(settings["paths"]["raw_dir"]) / "downloads"
    override_dir = Path(settings["paths"]["override_dir"])

    for source in registry:
        source_id = source["source_id"]
        table_name = source["raw_table"]
        candidate_files = list(raw_download_dir.glob(f"{source_id}.*"))
        override_files = list(override_dir.glob(f"{source_id}.*"))
        selected_file = override_files[0] if override_files else (candidate_files[0] if candidate_files else None)

        if not selected_file:
            logger.warning("Skipping %s: no file available", source_id)
            continue

        df = standardize_columns(_read_tabular(selected_file))
        expected = RAW_TABLE_EXPECTED_COLUMNS.get(table_name)
        if expected:
            require_columns(df, expected, table_name)

        numeric_non_negative = [
            c for c in [
                "ens_mwh",
                "actual_totex_million_gbp",
                "totex_allowance_million_gbp",
                "cost_per_customer_gbp",
                "sf6_kg",
                "carbon_footprint_tco2e",
                "kwh_per_gva",
                "energy_intensity_index",
                "electricity_pct",
                "gas_pct",
                "gva_million_gbp",
                "lcree_turnover_million_gbp",
            ] if c in df.columns
        ]
        for column in numeric_non_negative:
            df[column] = pd.to_numeric(df[column], errors="coerce")
        check_non_negative(df, numeric_non_negative, table_name)

        _upsert_raw(client, table_name, df, source_id, logger)
        client.execute(
            """
            INSERT INTO etl_run_log (run_ts, source_id, target_table, row_count, null_rate_json, status)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            """,
            (
                datetime.now(timezone.utc),
                source_id,
                table_name,
                int(len(df)),
                null_rate(df).to_json(),
                "loaded",
            ),
        )

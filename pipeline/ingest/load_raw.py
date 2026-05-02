from __future__ import annotations

import re
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
    "raw_ons_intermediate_consumption": ["year", "sic_code", "commodity", "intermediate_consumption_share"],
    "raw_daily_market_prices": ["date", "commodity", "metric_name", "value"],
}

COLUMN_ALIASES_BY_TABLE = {
    "raw_ons_lcree": {
        "turnover_million_gbp": "lcree_turnover_million_gbp",
        "turnover_current_prices_million_gbp": "lcree_turnover_million_gbp",
    },
    "raw_ons_intermediate_consumption": {
        "intermediate_share": "intermediate_consumption_share",
    },
}


def _canonical_raw_table_name(table_name: str) -> str:
    return table_name.split(".")[-1]


def _qualify_raw_table(table_name: str, default_schema: str = "raw") -> str:
    return table_name if "." in table_name else f"{default_schema}.{table_name}"


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


_INT_CON_SHEET = re.compile(r"Table 2 - Int Con (\d{4})\s*$")


def _parse_ons_intermediate_consumption_xlsx(path: Path) -> pd.DataFrame:
    """Expand ONS supply-use workbook sheets into long-form intermediate consumption.

    Each ``Table 2 - Int Con {year}`` sheet is a product × industry matrix (£ million)
    with column totals in the ``Total intermediate consumption at purchasers' prices`` row.
    """
    xl = pd.ExcelFile(path)
    rows: list[dict] = []
    product_rows_stop = 109  # exclusive upper bound for CPA product rows (indices 5..108)

    for sheet_name in xl.sheet_names:
        m = _INT_CON_SHEET.match(str(sheet_name).strip())
        if not m:
            continue
        year = int(m.group(1))
        df = pd.read_excel(path, sheet_name=sheet_name, header=None)
        if df.shape[0] < 110 or df.shape[1] < 4:
            continue

        total_row_idx = None
        for r in range(100, min(df.shape[0], 115)):
            cell = df.iloc[r, 1]
            if pd.notna(cell) and "Total intermediate consumption" in str(cell):
                total_row_idx = r
                break
        if total_row_idx is None:
            continue

        for j in range(2, df.shape[1]):
            sic_raw = df.iloc[3, j]
            if pd.isna(sic_raw) or str(sic_raw).strip() == "":
                continue
            sic_code = str(sic_raw).strip()
            ind_cell = df.iloc[4, j]
            industry_name = None if pd.isna(ind_cell) else str(ind_cell).strip()

            total_ic = pd.to_numeric(df.iloc[total_row_idx, j], errors="coerce")

            for i in range(5, product_rows_stop):
                prod_cell = df.iloc[i, 0]
                if pd.isna(prod_cell):
                    continue
                prod_s = str(prod_cell).strip()
                if not prod_s.startswith("CPA"):
                    continue
                val = pd.to_numeric(df.iloc[i, j], errors="coerce")
                if pd.isna(val):
                    val = 0.0
                if pd.notna(total_ic) and float(total_ic) > 0:
                    share = float(val) / float(total_ic)
                else:
                    share = float("nan")

                rows.append(
                    {
                        "year": year,
                        "sic_code": sic_code,
                        "industry_name": industry_name,
                        "commodity": prod_s,
                        "intermediate_consumption_share": share,
                        "intermediate_consumption_value": float(val),
                    }
                )

    if not rows:
        raise ValueError(
            f"{path.name}: no 'Table 2 - Int Con YYYY' sheets parsed; "
            "expected ONS supply & use publication workbook."
        )
    return pd.DataFrame(rows)


def _clean_ons_sap_numeric(val) -> float | None:
    if pd.isna(val):
        return None
    s = str(val).strip()
    if not s or "[x]" in s.lower():
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_ons_gas_sap_daily_xlsx(path: Path) -> pd.DataFrame:
    """Parse ONS ``1.Daily SAP Gas`` table into long-form daily price rows."""
    sheet = "1.Daily SAP Gas"
    df_raw = pd.read_excel(path, sheet_name=sheet, header=None)
    header_row = None
    for i in range(min(30, len(df_raw))):
        if str(df_raw.iloc[i, 0]).strip().lower() == "date":
            header_row = i
            break
    if header_row is None:
        raise ValueError(f"{path.name}: could not find Date header row in sheet {sheet!r}")

    rows_out: list[dict] = []
    for i in range(header_row + 1, len(df_raw)):
        dcell = df_raw.iloc[i, 0]
        if pd.isna(dcell):
            continue
        ts = pd.to_datetime(dcell, errors="coerce")
        if pd.isna(ts):
            continue
        date_str = ts.date().isoformat()

        v_day = _clean_ons_sap_numeric(df_raw.iloc[i, 1])
        if v_day is not None:
            rows_out.append(
                {
                    "date": date_str,
                    "commodity": "gas",
                    "source_name": "ons_sap_ocm",
                    "metric_name": "system_average_price",
                    "value": v_day,
                    "unit": "pence_per_kwh",
                }
            )
        if df_raw.shape[1] > 2:
            v_roll = _clean_ons_sap_numeric(df_raw.iloc[i, 2])
            if v_roll is not None:
                rows_out.append(
                    {
                        "date": date_str,
                        "commodity": "gas",
                        "source_name": "ons_sap_ocm",
                        "metric_name": "sap_seven_day_rolling_average",
                        "value": v_roll,
                        "unit": "pence_per_kwh",
                    }
                )

    if not rows_out:
        raise ValueError(f"{path.name}: no numeric SAP rows parsed from sheet {sheet!r}")
    return pd.DataFrame(rows_out)


def _upsert_raw(client, table_name: str, df: pd.DataFrame, source_id: str, logger) -> None:
    stage_table = f"{table_name.replace('.', '_')}_stage"
    client.execute(f"DROP TABLE IF EXISTS {stage_table};")
    columns_sql = ", ".join([f"{col} text" for col in df.columns])
    client.execute(f"CREATE TEMP TABLE {stage_table} ({columns_sql});")

    with client._conn.cursor() as cur:
        rows = [tuple(None if pd.isna(v) else str(v) for v in row) for row in df.to_numpy()]
        placeholders = ",".join(["%s"] * len(df.columns))
        insert_sql = f"INSERT INTO {stage_table} ({','.join(df.columns)}) VALUES ({placeholders})"
        cur.executemany(insert_sql, rows)

    key_cols = [
        c
        for c in [
            "year",
            "date",
            "company_name",
            "network_sector",
            "sic_code",
            "industry_name",
            "region_code",
            "commodity",
            "metric_name",
            "source_name",
        ]
        if c in df.columns
    ]
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
        source_table_name = source["raw_table"]
        table_name = _qualify_raw_table(source_table_name)
        canonical_table_name = _canonical_raw_table_name(source_table_name)
        candidate_files = list(raw_download_dir.glob(f"{source_id}.*"))
        override_files = list(override_dir.glob(f"{source_id}.*"))
        selected_file = override_files[0] if override_files else (candidate_files[0] if candidate_files else None)

        if not selected_file:
            logger.warning("Skipping %s: no file available", source_id)
            continue

        if canonical_table_name == "raw_ons_intermediate_consumption" and selected_file.suffix.lower() in {
            ".xlsx",
            ".xls",
        }:
            df = _parse_ons_intermediate_consumption_xlsx(selected_file)
        elif (
            canonical_table_name == "raw_daily_market_prices"
            and source_id == "ons_gas_sap_daily"
            and selected_file.suffix.lower() in {".xlsx", ".xls"}
        ):
            df = _parse_ons_gas_sap_daily_xlsx(selected_file)
        else:
            df = standardize_columns(_read_tabular(selected_file))
        alias_map = COLUMN_ALIASES_BY_TABLE.get(canonical_table_name, {})
        if alias_map:
            df = df.rename(columns={k: v for k, v in alias_map.items() if k in df.columns and v not in df.columns})

        expected = RAW_TABLE_EXPECTED_COLUMNS.get(canonical_table_name)
        if expected:
            require_columns(df, expected, canonical_table_name)

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
                "intermediate_consumption_share",
                "intermediate_consumption_value",
                "value",
            ] if c in df.columns
        ]
        for column in numeric_non_negative:
            df[column] = pd.to_numeric(df[column], errors="coerce")
        check_non_negative(df, numeric_non_negative, canonical_table_name)

        _upsert_raw(client, table_name, df, source_id, logger)
        client.execute(
            """
            INSERT INTO audit.etl_run_log (run_ts, source_id, target_table, row_count, null_rate_json, status)
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

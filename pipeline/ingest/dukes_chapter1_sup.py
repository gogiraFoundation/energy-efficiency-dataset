"""DUKES Chapter 1 supplementary tables — balances, sales, availability (DESNZ xlsx)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from pipeline.ingest.dukes_chapter6 import (
    RowTuple,
    _clean_numeric,
    _norm_label,
    parse_commodity_year_sheets,
)

def _year_token(val: Any) -> int | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    v = _clean_numeric(val)
    if v is None:
        return None
    y = int(round(float(v)))
    if 1950 <= y <= 2100:
        return y
    return None


def _unique_headers(raw: list[Any]) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for h in raw:
        if h is None or (isinstance(h, float) and pd.isna(h)):
            s = ""
        else:
            s = _norm_label(h)
        if not s:
            s = "unnamed"
        base = s
        n = seen.get(base, 0)
        seen[base] = n + 1
        if n:
            s = f"{base}__{n}"
        out.append(s)
    return out


def parse_1_1_alternative_units(
    path: Path,
    dukes_table: str,
    source_file: str,
    cfg: dict[str, Any],
) -> list[RowTuple]:
    """Two side-by-side blocks per year sheet: TWh (cols 1–10) and ktoe (cols 17–26)."""
    block1 = cfg.get("block1_col_range") or [1, 11]
    block2 = cfg.get("block2_col_range") or [17, 27]
    fuel_row = int(cfg.get("fuel_header_row_0indexed", 2))
    data_start = int(cfg.get("data_start_row_0indexed", 4))
    xl = pd.ExcelFile(path)
    pat = re.compile(cfg.get("sheet_name_regex", r"^\d{4}$"))
    out: list[RowTuple] = []
    for sheet in xl.sheet_names:
        if not pat.match(sheet):
            continue
        year = int(sheet)
        df = pd.read_excel(path, sheet_name=sheet, header=None)
        if fuel_row >= len(df):
            continue
        fuels1 = [
            _norm_label(df.iloc[fuel_row, c])
            for c in range(block1[0], block1[1])
        ]
        fuels2 = [
            _norm_label(df.iloc[fuel_row, c])
            for c in range(block2[0], block2[1])
        ]
        for ri in range(data_start, len(df)):
            flow = _norm_label(df.iloc[ri, 0])
            if not flow or flow.lower() == "column1":
                continue
            ll = flow.lower()
            if any(x in ll for x in ("this worksheet", "freeze panes", "some cells")):
                continue
            for i, c in enumerate(range(block1[0], block1[1])):
                if c >= df.shape[1]:
                    break
                fuel = fuels1[i] if i < len(fuels1) else f"col_{i}"
                v = _clean_numeric(df.iloc[ri, c])
                if v is None:
                    continue
                out.append(
                    (
                        dukes_table,
                        year,
                        None,
                        flow,
                        fuel,
                        "aggregate_balance_twh",
                        v,
                        "TWh",
                        source_file,
                    )
                )
            for i, c in enumerate(range(block2[0], block2[1])):
                if c >= df.shape[1]:
                    break
                fuel = fuels2[i] if i < len(fuels2) else f"col_{i}"
                v = _clean_numeric(df.iloc[ri, c])
                if v is None:
                    continue
                out.append(
                    (
                        dukes_table,
                        year,
                        None,
                        flow,
                        fuel,
                        "aggregate_balance_ktoe",
                        v,
                        "ktoe",
                        source_file,
                    )
                )
    return out


def parse_year_in_columns_sheet(
    path: Path,
    sheet_name: str,
    dukes_table: str,
    source_file: str,
    header_row: int,
    data_start: int,
    metric_name: str,
    unit: str,
    column_suffix: str | None = None,
) -> list[RowTuple]:
    """First column = row label; top row = years (Table 1.3 style)."""
    df = pd.read_excel(path, sheet_name=sheet_name, header=None)
    if header_row >= len(df):
        return []
    year_cols: list[tuple[int, int]] = []
    for c in range(1, df.shape[1]):
        y = _year_token(df.iloc[header_row, c])
        if y:
            year_cols.append((c, y))
    out: list[RowTuple] = []
    col_lab = column_suffix or sheet_name.replace(".", "_")
    for ri in range(data_start, len(df)):
        row_label = _norm_label(df.iloc[ri, 0])
        if not row_label:
            continue
        rl = row_label.lower()
        if any(s in rl for s in ("this worksheet", "freeze panes", "column1")):
            continue
        for c, yr in year_cols:
            v = _clean_numeric(df.iloc[ri, c])
            if v is None:
                continue
            out.append(
                (
                    dukes_table,
                    yr,
                    None,
                    row_label,
                    col_lab,
                    metric_name,
                    v,
                    unit,
                    source_file,
                )
            )
    return out


def parse_simple_year_metrics_table(
    path: Path,
    sheet_name: str,
    dukes_table: str,
    source_file: str,
    header_row: int,
    data_start: int,
    metric_prefix: str,
) -> list[RowTuple]:
    """Year in column 0; each other column is a metric series (Table 1.1.3 style)."""
    df = pd.read_excel(path, sheet_name=sheet_name, header=None)
    if header_row >= len(df):
        return []
    headers = [_norm_label(df.iloc[header_row, c]) for c in range(1, df.shape[1])]
    out: list[RowTuple] = []
    for ri in range(data_start, len(df)):
        y = _year_token(df.iloc[ri, 0])
        if y is None:
            continue
        for ci, h in enumerate(headers, 1):
            if not h:
                continue
            v = _clean_numeric(df.iloc[ri, ci])
            if v is None:
                continue
            metric = f"{metric_prefix}_{re.sub(r'[^a-zA-Z0-9]+', '_', h.lower()).strip('_')[:80]}"
            unit = "percent" if "percentage" in h.lower() else "mtoe"
            out.append((dukes_table, y, None, h, None, metric, v, unit, source_file))
    return out


def parse_wide_first_col_year(
    path: Path,
    sheet_name: str,
    dukes_table: str,
    source_file: str,
    header_row: int,
    data_start: int,
    metric_name: str,
    unit: str,
) -> list[RowTuple]:
    """Wide table: Year + many columns (Table 1.1.2)."""
    df = pd.read_excel(path, sheet_name=sheet_name, header=None)
    if header_row >= len(df):
        return []
    raw_h = [df.iloc[header_row, c] for c in range(df.shape[1])]
    headers = _unique_headers(raw_h)
    out: list[RowTuple] = []
    for ri in range(data_start, len(df)):
        y = _year_token(df.iloc[ri, 0])
        if y is None:
            continue
        for ci in range(1, len(headers)):
            col_h = headers[ci]
            if col_h.lower() in ("year", "unnamed"):
                continue
            v = _clean_numeric(df.iloc[ri, ci])
            if v is None:
                continue
            out.append(
                (dukes_table, y, None, col_h, None, metric_name, v, unit, source_file)
            )
    return out


def parse_fuel_row_year_columns(
    path: Path,
    sheet_name: str,
    dukes_table: str,
    source_file: str,
    header_row: int,
    data_start: int,
    metric_name: str,
    unit: str,
) -> list[RowTuple]:
    """Rows = fuels/metrics; columns = years (Tables 1.1.1.A / 1.1.1.C)."""
    df = pd.read_excel(path, sheet_name=sheet_name, header=None)
    if header_row >= len(df):
        return []
    year_cols: list[tuple[int, int]] = []
    for c in range(1, df.shape[1]):
        y = _year_token(df.iloc[header_row, c])
        if y:
            year_cols.append((c, y))
    out: list[RowTuple] = []
    for ri in range(data_start, len(df)):
        row_label = _norm_label(df.iloc[ri, 0])
        if not row_label:
            continue
        rl = row_label.lower()
        if rl.startswith("column1") or "table 1.1.1" in rl:
            continue
        if any(x in rl for x in ("this worksheet", "freeze panes")):
            continue
        for c, yr in year_cols:
            v = _clean_numeric(df.iloc[ri, c])
            if v is None:
                continue
            out.append(
                (
                    dukes_table,
                    yr,
                    None,
                    row_label,
                    sheet_name.replace(".", "_"),
                    metric_name,
                    v,
                    unit,
                    source_file,
                )
            )
    return out


def load_chapter1_supplementary_tables(
    settings: dict[str, Any],
    client: Any,
    logger: Any,
    reg: dict[str, Any],
    ddir: Path,
    timeout: int,
) -> None:
    import pipeline.ingest.ingest_dukes as ingest_dukes_mod

    _download = ingest_dukes_mod._download

    ch = reg.get("chapter1_sup") or {}
    tables_cfg = ch.get("tables") or {}
    if not tables_cfg:
        logger.info("DUKES Chapter 1 supplementary: no tables in registry, skipping")
        return

    all_rows: list[RowTuple] = []

    for _key, cfg in tables_cfg.items():
        parser = cfg.get("parser")
        fn = cfg["filename"]
        dest = ddir / fn
        if not dest.exists():
            logger.info("Downloading DUKES Chapter 1 sup %s", fn)
            _download(cfg["url"], dest, timeout)
        dukes_table = str(cfg.get("table_id", ""))
        source_file = fn

        if parser == "commodity_year_sheets":
            pat = re.compile(cfg.get("sheet_name_regex", r"^\d{4}$"))
            rows = parse_commodity_year_sheets(dest, cfg, dukes_table, source_file, pat)
            all_rows.extend(rows)
            logger.info("DUKES %s commodity_year_sheets: %s rows", dukes_table, len(rows))
            continue

        if parser == "aggregate_balance_alternative_units":
            rows = parse_1_1_alternative_units(dest, dukes_table, source_file, cfg)
            all_rows.extend(rows)
            logger.info("DUKES %s alternative_units: %s rows", dukes_table, len(rows))
            continue

        if parser == "sales_year_columns":
            n_sales = 0
            for entry in cfg.get("sheets", []):
                if isinstance(entry, dict):
                    sh = str(entry["sheet"])
                    met = str(entry.get("metric_name", cfg.get("metric_name", "sales_million_gbp")))
                    unt = str(entry.get("unit", cfg.get("unit", "million_gbp")))
                else:
                    sh = str(entry)
                    met = str(cfg.get("metric_name", "sales_million_gbp"))
                    unt = str(cfg.get("unit", "million_gbp"))
                rows = parse_year_in_columns_sheet(
                    dest,
                    sh,
                    dukes_table,
                    source_file,
                    int(cfg["header_row_0indexed"]),
                    int(cfg["data_start_row_0indexed"]),
                    met,
                    unt,
                    column_suffix=sh.replace(".", "_"),
                )
                all_rows.extend(rows)
                n_sales += len(rows)
            logger.info("DUKES %s sales_year_columns: %s rows", dukes_table, n_sales)
            continue

        if parser == "simple_year_metrics":
            sh = cfg["sheet"]
            rows = parse_simple_year_metrics_table(
                dest,
                sh,
                dukes_table,
                source_file,
                int(cfg["header_row_0indexed"]),
                int(cfg["data_start_row_0indexed"]),
                str(cfg.get("metric_prefix", "metric")),
            )
            all_rows.extend(rows)
            logger.info("DUKES %s simple_year_metrics: %s rows", dukes_table, len(rows))
            continue

        if parser == "wide_year_rows":
            sh = cfg["sheet"]
            rows = parse_wide_first_col_year(
                dest,
                sh,
                dukes_table,
                source_file,
                int(cfg["header_row_0indexed"]),
                int(cfg["data_start_row_0indexed"]),
                str(cfg.get("metric_name", "availability_ktoe")),
                str(cfg.get("unit", "ktoe")),
            )
            all_rows.extend(rows)
            logger.info("DUKES %s wide_year_rows: %s rows", dukes_table, len(rows))
            continue

        if parser == "fuel_by_year_matrix":
            n_fuel = 0
            for sh in cfg.get("sheets", []):
                rows = parse_fuel_row_year_columns(
                    dest,
                    sh,
                    dukes_table,
                    source_file,
                    int(cfg["header_row_0indexed"]),
                    int(cfg["data_start_row_0indexed"]),
                    str(cfg.get("metric_name", "value")),
                    str(cfg.get("unit", "mixed")),
                )
                all_rows.extend(rows)
                n_fuel += len(rows)
            logger.info("DUKES %s fuel_by_year_matrix: %s rows", dukes_table, n_fuel)
            continue

        logger.warning("Unknown Chapter 1 sup parser %s for %s", parser, fn)

    if not all_rows:
        logger.warning("DUKES Chapter 1 supplementary: no rows parsed")
        return

    with client._conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO stg_dukes_chapter1_sup (
                dukes_table, period_year, period_label, row_label, column_label,
                metric_name, value, unit, source_file
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            all_rows,
        )
    logger.info("stg_dukes_chapter1_sup: inserted %s rows", len(all_rows))

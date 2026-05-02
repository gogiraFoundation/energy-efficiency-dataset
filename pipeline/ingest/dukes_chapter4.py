"""DUKES Chapter 4 — natural gas (DESNZ official statistics).

https://www.gov.uk/government/statistics/natural-gas-chapter-4-digest-of-united-kingdom-energy-statistics-dukes
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from pipeline.ingest.dukes_chapter1_sup import parse_wide_first_col_year, parse_year_in_columns_sheet
from pipeline.ingest.dukes_chapter5 import (
    RowCh5,
    parse_carryforward_year_sections,
    parse_station_register_sheet,
    _year_token_hist,
)
from pipeline.ingest.dukes_chapter6 import _clean_numeric, _norm_label

DEFAULT_CH4_TITLE = r"^(?:Table|Annex)\s+(?:4\.|E\.|F\.)"


def parse_wide_label_total_and_years(
    path: Path,
    sheet_name: str,
    dukes_table: str,
    source_file: str,
    header_row: int,
    data_start: int,
    metric_name: str,
    unit: str,
    cumulative_metric_suffix: str = "cumulative_series",
) -> list[RowCh5]:
    """Row labels in col 0; optional non-calendar columns before first calendar-year column (e.g. F.2)."""
    df = pd.read_excel(path, sheet_name=sheet_name, header=None)
    if header_row >= len(df):
        return []
    headers = [_norm_label(df.iloc[header_row, c]) for c in range(df.shape[1])]
    first_year_col: int | None = None
    year_positions: list[tuple[int, int]] = []
    for c in range(1, df.shape[1]):
        y = _year_token_hist(df.iloc[header_row, c])
        if y:
            year_positions.append((c, y))
            if first_year_col is None:
                first_year_col = c
    if first_year_col is None or len(year_positions) < 2:
        return []
    out: list[RowCh5] = []
    for ri in range(data_start, len(df)):
        row_label = _norm_label(df.iloc[ri, 0])
        if not row_label:
            continue
        rl = row_label.lower()
        if any(x in rl for x in ("this worksheet", "freeze panes")):
            continue
        if re.search(r"^table\s+\d", rl):
            continue
        for c in range(1, first_year_col):
            h = headers[c] if c < len(headers) else ""
            if not h:
                continue
            v = _clean_numeric(df.iloc[ri, c])
            if v is None:
                continue
            mm = f"{metric_name}_{cumulative_metric_suffix}"
            out.append((dukes_table, None, h, row_label, h, mm, v, unit, source_file, None))
        for c, yr in year_positions:
            if c >= df.shape[1]:
                break
            v = _clean_numeric(df.iloc[ri, c])
            if v is None:
                continue
            out.append((dukes_table, yr, None, row_label, None, metric_name, v, unit, source_file, None))
    return out


def load_chapter4_tables(
    settings: dict[str, Any],
    client: Any,
    logger: Any,
    reg: dict[str, Any],
    ddir: Path,
    timeout: int,
) -> None:
    import pipeline.ingest.ingest_dukes as ingest_dukes_mod

    _download = ingest_dukes_mod._download

    ch = reg.get("chapter4") or {}
    tables_cfg = ch.get("tables") or {}
    if not tables_cfg:
        logger.info("DUKES Chapter 4: no tables in registry, skipping")
        return

    all_rows: list[RowCh5] = []

    for _key, cfg in tables_cfg.items():
        parser = cfg.get("parser")
        fn = cfg["filename"]
        dest = ddir / fn
        if not dest.exists():
            logger.info("Downloading DUKES Chapter 4 %s", fn)
            _download(cfg["url"], dest, timeout)
        dukes_table = str(cfg.get("table_id", ""))
        source_file = fn

        if parser == "ch4_carryforward":
            min_yc = int(cfg.get("min_year_columns", 2))
            title_pat = cfg.get("title_pattern") or DEFAULT_CH4_TITLE
            n_cf = 0
            for sh in cfg.get("sheets", []):
                df = pd.read_excel(dest, sheet_name=sh, header=None)
                rows = parse_carryforward_year_sections(
                    df,
                    dukes_table,
                    source_file,
                    str(cfg.get("metric_name", "value")),
                    str(cfg.get("unit", "mixed")),
                    min_year_cols=min_yc,
                    title_pattern=title_pat,
                )
                all_rows.extend(rows)
                n_cf += len(rows)
            logger.info("DUKES %s ch4_carryforward: %s rows", dukes_table, n_cf)
            continue

        if parser == "ch4_year_in_columns":
            sh = cfg["sheet"]
            rows9 = parse_year_in_columns_sheet(
                dest,
                sh,
                dukes_table,
                source_file,
                int(cfg["header_row_0indexed"]),
                int(cfg["data_start_row_0indexed"]),
                str(cfg.get("metric_name", "value")),
                str(cfg.get("unit", "mixed")),
                column_suffix=sh.replace(".", "_"),
            )
            all_rows.extend([(*t, None) for t in rows9])
            logger.info("DUKES %s ch4_year_in_columns: %s rows", dukes_table, len(rows9))
            continue

        if parser == "ch4_wide_year_rows":
            sheet_list = cfg.get("sheets") or ([cfg["sheet"]] if cfg.get("sheet") else [])
            nwide = 0
            for sh in sheet_list:
                rows9 = parse_wide_first_col_year(
                    dest,
                    sh,
                    dukes_table,
                    source_file,
                    int(cfg["header_row_0indexed"]),
                    int(cfg["data_start_row_0indexed"]),
                    str(cfg.get("metric_name", "value")),
                    str(cfg.get("unit", "mixed")),
                )
                all_rows.extend([(*t, None) for t in rows9])
                nwide += len(rows9)
            logger.info("DUKES %s ch4_wide_year_rows: %s rows", dukes_table, nwide)
            continue

        if parser == "ch4_wide_total_years":
            rows = parse_wide_label_total_and_years(
                dest,
                cfg["sheet"],
                dukes_table,
                source_file,
                int(cfg["header_row_0indexed"]),
                int(cfg["data_start_row_0indexed"]),
                str(cfg.get("metric_name", "gas_production_mcm")),
                str(cfg.get("unit", "million_cubic_metres")),
                cumulative_metric_suffix=str(cfg.get("cumulative_metric_suffix", "cumulative_series")),
            )
            all_rows.extend(rows)
            logger.info("DUKES %s ch4_wide_total_years: %s rows", dukes_table, len(rows))
            continue

        if parser == "ch4_station_register":
            n0 = len(all_rows)
            xl = pd.ExcelFile(dest)
            pat = re.compile(cfg.get("sheet_name_regex", "$^"))
            reg_defaults = cfg.get("regex_sheet_defaults") or {}
            for spec in cfg.get("sheet_configs", []):
                sh = spec["sheet"]
                if sh not in xl.sheet_names:
                    continue
                df = pd.read_excel(dest, sheet_name=sh, header=None)
                snap = spec.get("snapshot_year")
                if snap is None and spec.get("year_from_sheet_name"):
                    m = re.search(r"(\d{4})", sh)
                    snap = int(m.group(1)) if m else None
                rows = parse_station_register_sheet(
                    df,
                    dukes_table,
                    source_file,
                    sh,
                    int(spec["header_row_0indexed"]),
                    int(spec["data_start_row_0indexed"]),
                    snap,
                    str(cfg.get("metric_name", "facility_register")),
                    str(cfg.get("unit", "mixed")),
                    list(spec.get("row_label_cols", [0, 1])),
                    bool(spec.get("text_columns", True)),
                )
                all_rows.extend(rows)
            if cfg.get("sheet_name_regex"):
                for sh in xl.sheet_names:
                    if not pat.match(sh):
                        continue
                    df = pd.read_excel(dest, sheet_name=sh, header=None)
                    m = re.search(r"(\d{4})", sh)
                    snap = int(m.group(1)) if m else None
                    rows = parse_station_register_sheet(
                        df,
                        dukes_table,
                        source_file,
                        sh,
                        int(reg_defaults["header_row_0indexed"]),
                        int(reg_defaults["data_start_row_0indexed"]),
                        snap,
                        str(cfg.get("metric_name", "facility_register")),
                        str(cfg.get("unit", "mixed")),
                        list(reg_defaults.get("row_label_cols", [0, 1])),
                        bool(reg_defaults.get("text_columns", True)),
                    )
                    all_rows.extend(rows)
            logger.info("DUKES %s ch4_station_register: %s rows", dukes_table, len(all_rows) - n0)
            continue

        logger.warning("Unknown Chapter 4 parser %s for %s", parser, fn)

    if not all_rows:
        logger.warning("DUKES Chapter 4: no rows parsed")
        return

    with client._conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO stg_dukes_chapter4 (
                dukes_table, period_year, period_label, row_label, column_label,
                metric_name, value, unit, source_file, value_text
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            all_rows,
        )
    logger.info("stg_dukes_chapter4: inserted %s rows", len(all_rows))

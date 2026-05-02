"""DUKES Chapter 5 — electricity (DESNZ official statistics).

https://www.gov.uk/government/statistics/electricity-chapter-5-digest-of-united-kingdom-energy-statistics-dukes
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from pipeline.ingest.dukes_chapter1_sup import (
    parse_wide_first_col_year,
    parse_year_in_columns_sheet,
)
from pipeline.ingest.dukes_chapter6 import _clean_numeric, _norm_label

RowCh5 = tuple[Any, ...]


def _year_token_hist(val: Any) -> int | None:
    """Calendar years for long time series (cf. chapter6 _year_token which starts at 1990)."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    v = _clean_numeric(val)
    if v is None:
        return None
    y = int(round(float(v)))
    if 1950 <= y <= 2100:
        return y
    return None


def _collect_year_cols(df: pd.DataFrame, r: int, min_years: int = 2) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for c in range(1, df.shape[1]):
        y = _year_token_hist(df.iloc[r, c])
        if y:
            out.append((c, y))
    return out if len(out) >= min_years else []


def parse_carryforward_year_sections(
    df: pd.DataFrame,
    dukes_table: str,
    source_file: str,
    metric_name: str,
    unit: str,
    min_year_cols: int = 2,
    title_pattern: str | None = None,
) -> list[RowCh5]:
    """Sheets with one or more DUKES table blocks; each followed by a year-header row.

    ``title_pattern`` defaults to Chapter 5 ``Table 5.x``; Chapter 4 passes a ``Table 4.x`` / ``Annex`` pattern.
    """
    out: list[RowCh5] = []
    n = len(df)
    r = 0
    section = ""
    pat = title_pattern or r"^Table\s+5\.[\d\.A-Za-z]+"
    title_re = re.compile(pat, re.I)
    while r < n:
        c0 = _norm_label(df.iloc[r, 0])
        if title_re.match(c0):
            section = c0[:500]
            r += 1
            continue
        ycols = _collect_year_cols(df, r, min_year_cols)
        if not ycols:
            r += 1
            continue
        first_y_col = ycols[0][0]
        r += 1
        while r < n:
            c0b = _norm_label(df.iloc[r, 0])
            if title_re.match(c0b):
                break
            ycols_head = _collect_year_cols(df, r, min_year_cols)
            if ycols_head and ycols_head[0][0] == first_y_col:
                break
            parts = [_norm_label(df.iloc[r, i]) for i in range(first_y_col)]
            row_label = " | ".join(p for p in parts if p)
            rl = row_label.lower()
            if not row_label or rl == "category":
                r += 1
                continue
            if title_re.match(row_label):
                break
            for c, yr in ycols:
                if c >= df.shape[1]:
                    break
                v = _clean_numeric(df.iloc[r, c])
                if v is None:
                    continue
                lab = section[:400] if section else None
                out.append((dukes_table, yr, section or None, row_label, lab, metric_name, v, unit, source_file, None))
            r += 1
    return out


def parse_embedded_year_column_headers(
    df: pd.DataFrame,
    dukes_table: str,
    source_file: str,
    header_row: int,
    data_start: int,
    metric_name: str,
    unit: str,
) -> list[RowCh5]:
    """Columns like 'Public distribution system (1998)' — year inside header text."""
    yr_pat = re.compile(r"\((\d{4})\)\s*$")
    out: list[RowCh5] = []
    if header_row >= len(df):
        return out
    col_meta: list[tuple[int, int, str]] = []
    for c in range(1, df.shape[1]):
        h = _norm_label(df.iloc[header_row, c])
        m = yr_pat.search(h)
        if not m:
            continue
        yr = int(m.group(1))
        if yr < 1950 or yr > 2100:
            continue
        base = yr_pat.sub("", h).strip()
        col_meta.append((c, yr, base))
    for ri in range(data_start, len(df)):
        flow = _norm_label(df.iloc[ri, 0])
        if not flow:
            continue
        fl = flow.lower()
        if any(x in fl for x in ("this worksheet", "freeze panes")):
            continue
        if re.search(r"^table\s+\d", fl):
            continue
        for c, yr, base in col_meta:
            if c >= df.shape[1]:
                break
            v = _clean_numeric(df.iloc[ri, c])
            if v is None:
                continue
            col_lab = base if base else None
            out.append((dukes_table, yr, None, flow, col_lab, metric_name, v, unit, source_file, None))
    return out


def parse_station_register_sheet(
    df: pd.DataFrame,
    dukes_table: str,
    source_file: str,
    sheet_name: str,
    header_row: int,
    data_start: int,
    snapshot_year: int | None,
    metric_name: str,
    unit: str,
    row_label_cols: list[int],
    text_columns: bool,
) -> list[RowCh5]:
    """Power station listing: long rows with numeric value and/or value_text."""
    out: list[RowCh5] = []
    if header_row >= len(df):
        return out
    headers = [_norm_label(df.iloc[header_row, c]) for c in range(df.shape[1])]
    for ri in range(data_start, len(df)):
        parts = [_norm_label(df.iloc[ri, c]) for c in row_label_cols if c < df.shape[1]]
        row_label = " | ".join(p for p in parts if p)
        if not row_label:
            continue
        for ci in range(max(row_label_cols) + 1, len(headers)):
            h = headers[ci]
            if not h:
                continue
            raw = df.iloc[ri, ci]
            vnum = _clean_numeric(raw)
            vtxt: str | None = None
            if vnum is not None:
                out.append(
                    (dukes_table, snapshot_year, sheet_name, row_label, h, metric_name, vnum, unit, source_file, None)
                )
            elif text_columns and raw is not None and not (isinstance(raw, float) and pd.isna(raw)):
                vtxt = _norm_label(raw)
                if vtxt:
                    out.append(
                        (
                            dukes_table,
                            snapshot_year,
                            sheet_name,
                            row_label,
                            h,
                            metric_name,
                            None,
                            "text",
                            source_file,
                            vtxt,
                        )
                    )
    return out


def load_chapter5_tables(
    settings: dict[str, Any],
    client: Any,
    logger: Any,
    reg: dict[str, Any],
    ddir: Path,
    timeout: int,
) -> None:
    import pipeline.ingest.ingest_dukes as ingest_dukes_mod

    _download = ingest_dukes_mod._download

    ch = reg.get("chapter5") or {}
    tables_cfg = ch.get("tables") or {}
    if not tables_cfg:
        logger.info("DUKES Chapter 5: no tables in registry, skipping")
        return

    all_rows: list[RowCh5] = []

    for _key, cfg in tables_cfg.items():
        parser = cfg.get("parser")
        fn = cfg["filename"]
        dest = ddir / fn
        if not dest.exists():
            logger.info("Downloading DUKES Chapter 5 %s", fn)
            _download(cfg["url"], dest, timeout)
        dukes_table = str(cfg.get("table_id", ""))
        source_file = fn

        if parser == "ch5_year_in_columns":
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
            fixed = [(*t, None) for t in rows9]
            all_rows.extend(fixed)
            logger.info("DUKES %s ch5_year_in_columns: %s rows", dukes_table, len(fixed))
            continue

        if parser == "ch5_wide_year_rows":
            sh = cfg["sheet"]
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
            logger.info("DUKES %s ch5_wide_year_rows: %s rows", dukes_table, len(rows9))
            continue

        if parser == "ch5_carryforward":
            min_yc = int(cfg.get("min_year_columns", 2))
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
                    title_pattern=cfg.get("title_pattern"),
                )
                all_rows.extend(rows)
                n_cf += len(rows)
            logger.info("DUKES %s ch5_carryforward: %s rows", dukes_table, n_cf)
            continue

        if parser == "ch5_embedded_year_headers":
            sh = cfg["sheet"]
            df = pd.read_excel(dest, sheet_name=sh, header=None)
            rows = parse_embedded_year_column_headers(
                df,
                dukes_table,
                source_file,
                int(cfg["header_row_0indexed"]),
                int(cfg["data_start_row_0indexed"]),
                str(cfg.get("metric_name", "value")),
                str(cfg.get("unit", "mixed")),
            )
            all_rows.extend(rows)
            logger.info("DUKES %s ch5_embedded_year_headers: %s rows", dukes_table, len(rows))
            continue

        if parser == "ch5_station_register":
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
                    str(cfg.get("metric_name", "mpp_station")),
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
                        str(cfg.get("metric_name", "mpp_station")),
                        str(cfg.get("unit", "mixed")),
                        list(reg_defaults.get("row_label_cols", [0, 1])),
                        bool(reg_defaults.get("text_columns", True)),
                    )
                    all_rows.extend(rows)
            logger.info("DUKES %s ch5_station_register: %s rows", dukes_table, len(all_rows) - n0)
            continue

        logger.warning("Unknown Chapter 5 parser %s for %s", parser, fn)

    if not all_rows:
        logger.warning("DUKES Chapter 5: no rows parsed")
        return

    with client._conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO stg_dukes_chapter5 (
                dukes_table, period_year, period_label, row_label, column_label,
                metric_name, value, unit, source_file, value_text
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            all_rows,
        )
    logger.info("stg_dukes_chapter5: inserted %s rows", len(all_rows))

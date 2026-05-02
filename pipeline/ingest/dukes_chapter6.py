"""DUKES Chapter 6 — renewable sources of energy (DESNZ official statistics).

https://www.gov.uk/government/statistics/renewable-sources-of-energy-chapter-6-digest-of-united-kingdom-energy-statistics-dukes
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

import pandas as pd


RowTuple = tuple[Any, ...]


def _clean_numeric(val: Any) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    if not s or s.lower() in {"[x]", "x", "nan", ""}:
        return None
    s = re.sub(r"\[.*?\]", "", s).strip()
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _year_token(val: Any) -> int | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    v = _clean_numeric(val)
    if v is None:
        return None
    y = int(round(float(v)))
    if 1990 <= y <= 2035:
        return y
    return None


def _is_year_header_row(df: pd.DataFrame, r: int, min_years: int = 3) -> bool:
    ys: list[int] = []
    for c in range(1, min(df.shape[1], 12)):
        y = _year_token(df.iloc[r, c])
        if y:
            ys.append(y)
    return len(ys) >= min_years


def _norm_label(x: Any) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    return re.sub(r"\s+", " ", str(x).strip())


def parse_multi_section_year_columns(
    df: pd.DataFrame,
    dukes_table: str,
    source_file: str,
    section_metric: Callable[[str], tuple[str, str] | None],
    column_label_fn: Callable[[dict[str, Any], str], str | None] | None = None,
    section_state_hook: Callable[[str, dict[str, Any]], None] | None = None,
) -> list[RowTuple]:
    """Find rows where cols 1+ contain calendar years; unpivot until next such header."""
    state: dict[str, Any] = {"sub": ""}
    out: list[RowTuple] = []
    r = 0
    n = len(df)
    while r < n:
        if not _is_year_header_row(df, r):
            r += 1
            continue
        title = _norm_label(df.iloc[r, 0])
        spec = section_metric(title)
        if spec is None:
            r += 1
            continue
        metric_name, unit = spec
        if section_state_hook:
            section_state_hook(title, state)
        year_cols: list[tuple[int, int]] = []
        for c in range(1, df.shape[1]):
            y = _year_token(df.iloc[r, c])
            if y:
                year_cols.append((c, y))
        if not year_cols:
            r += 1
            continue
        r += 1
        while r < n:
            if _is_year_header_row(df, r):
                break
            row_label = _norm_label(df.iloc[r, 0])
            if not row_label:
                r += 1
                continue
            if column_label_fn:
                col_extra = column_label_fn(state, row_label)
            else:
                col_extra = None
            for c, yr in year_cols:
                v = _clean_numeric(df.iloc[r, c])
                if v is None:
                    continue
                out.append(
                    (dukes_table, yr, None, row_label, col_extra, metric_name, v, unit, source_file)
                )
            r += 1
    return out


def _section_6_2(title: str) -> tuple[str, str] | None:
    t = title.lower()
    if "installed capacity" in t and "mw" in t:
        return "installed_capacity_mw", "MW"
    if "generation (gwh)" in t:
        return "generation_gwh", "GWh"
    if "shares of total electricity generation" in t:
        return "generation_share_pct", "percent"
    return None


def _section_6_3(title: str) -> tuple[str, str] | None:
    t = title.lower()
    if "based on average of beginning and end of year capacity" in t:
        return "load_factor_avg_capacity_pct", "percent"
    if "unchanged configuration" in t:
        return "load_factor_unchanged_config_pct", "percent"
    return None


def _hook_6_4(title: str, state: dict[str, Any]) -> None:
    t = title.lower()
    if "used to generate electricity" in t:
        state["sub"] = "electricity"
    elif "used to generate heat" in t:
        state["sub"] = "heat"
    elif "total use of renewable" in t:
        state["sub"] = "combined"
    elif "renewable sources used as transport" in t:
        state["sub"] = "transport"


def _col_label_6_4(state: dict[str, Any], row_label: str) -> str | None:
    rl = row_label.lower()
    if "renewable sources used as transport" in rl:
        state["sub"] = "transport"
    sub = state.get("sub") or "electricity"
    return str(sub)


def _section_6_4(title: str) -> tuple[str, str] | None:
    t = title.lower()
    if "used to generate electricity" in t:
        return "renewable_use_ktoe", "ktoe"
    if "used to generate heat" in t:
        return "renewable_use_ktoe", "ktoe"
    if "total use of renewable" in t:
        return "renewable_use_ktoe", "ktoe"
    if "renewable sources used as transport" in t:
        return "renewable_use_ktoe", "ktoe"
    return None


def parse_6_4_custom(df: pd.DataFrame, dukes_table: str, source_file: str) -> list[RowTuple]:
    """6.4 has shared year bands; subsection labels applied via column_label."""
    state: dict[str, Any] = {"sub": "electricity"}
    return parse_multi_section_year_columns(
        df,
        dukes_table,
        source_file,
        _section_6_4,
        lambda st, rl: _col_label_6_4(st, rl),
        section_state_hook=_hook_6_4,
    )


def _section_6_5_summary(title: str) -> tuple[str, str] | None:
    t = title.lower().strip()
    # Table 6.5a — Gross Final Consumption lens
    if "electricity generation (ktoe)" in t:
        return "gfc_electricity_generation_ktoe", "ktoe"
    if "electricity net imports (ktoe)" in t:
        return "gfc_electricity_net_imports_ktoe", "ktoe"
    if "electricity supplied (ktoe)" in t:
        return "gfc_electricity_supplied_ktoe", "ktoe"
    if "gross final consumption - electricity" in t:
        return "gfc_electricity_gfc_ktoe", "ktoe"
    if "renewable share of gross final electricity" in t:
        return "gfc_electricity_renewable_share_pct", "percent"
    if "heat generation (ktoe)" in t:
        return "gfc_heat_generation_ktoe", "ktoe"
    if t == "transport (ktoe)" or ("transport" in t and "ktoe" in t and "final" not in t):
        return "gfc_transport_ktoe", "ktoe"
    if "overall consumption (ktoe)" in t:
        return "gfc_overall_consumption_ktoe", "ktoe"
    # Table 6.5b — aggregated balances summary
    if t == "production":
        return "gfc_balance_production_ktoe", "ktoe"
    if t == "imports":
        return "gfc_balance_imports_ktoe", "ktoe"
    if t == "exports":
        return "gfc_balance_exports_ktoe", "ktoe"
    if t == "demand":
        return "gfc_balance_demand_ktoe", "ktoe"
    if "final consumption - industry" in t:
        return "gfc_balance_final_industry_ktoe", "ktoe"
    if "final consumption - transport" in t:
        return "gfc_balance_final_transport_ktoe", "ktoe"
    if "final consumption - domestic" in t:
        return "gfc_balance_final_domestic_ktoe", "ktoe"
    if "final consumption - other" in t:
        return "gfc_balance_final_other_ktoe", "ktoe"
    if "total final energy consumption" in t:
        return "gfc_balance_total_final_energy_ktoe", "ktoe"
    if "non-energy use" in t:
        return "gfc_balance_non_energy_use_ktoe", "ktoe"
    if "total final consumption (incl" in t:
        return "gfc_balance_total_final_incl_non_energy_ktoe", "ktoe"
    return None


def parse_commodity_year_sheets(
    path: Path,
    cfg: dict[str, Any],
    dukes_table: str,
    source_file: str,
    sheet_regex: re.Pattern[str],
) -> list[RowTuple]:
    xl = pd.ExcelFile(path)
    metric = cfg.get("metric_name", "commodity_balance_ktoe")
    unit = cfg.get("unit", "ktoe")
    hdr = int(cfg["header_row_0indexed"])
    d0 = int(cfg["data_start_row_0indexed"])
    out: list[RowTuple] = []
    for sheet in xl.sheet_names:
        if not sheet_regex.match(sheet):
            continue
        year = int(sheet)
        df = pd.read_excel(path, sheet_name=sheet, header=None)
        if hdr >= len(df):
            continue
        fuels: list[str] = []
        for c in range(1, df.shape[1]):
            h = df.iloc[hdr, c]
            if pd.isna(h):
                continue
            fuels.append(_norm_label(h))
        for ri in range(d0, len(df)):
            flow = _norm_label(df.iloc[ri, 0])
            if not flow:
                continue
            for ci, fuel in enumerate(fuels, 1):
                if ci >= df.shape[1]:
                    break
                v = _clean_numeric(df.iloc[ri, ci])
                if v is None:
                    continue
                out.append(
                    (dukes_table, year, None, flow, fuel, metric, v, unit, source_file)
                )
    return out


def parse_dukes_6_5_detail_sheet(
    df: pd.DataFrame,
    dukes_table: str,
    source_file: str,
    sheet_year: int,
    header_row: int,
    data_start: int,
) -> list[RowTuple]:
    """Sheets named by year: wide matrix flows x fuels."""
    out: list[RowTuple] = []
    if header_row >= len(df):
        return out
    fuels: list[str] = []
    for c in range(1, df.shape[1]):
        h = df.iloc[header_row, c]
        if pd.isna(h):
            continue
        fuels.append(_norm_label(h))
    for ri in range(data_start, len(df)):
        flow = _norm_label(df.iloc[ri, 0])
        if not flow:
            continue
        for ci, fuel in enumerate(fuels, 1):
            if ci >= df.shape[1]:
                break
            raw = df.iloc[ri, ci]
            fl = fuel.lower()
            if "share of renewables" in fl:
                metric = "gfc_renewables_share_pct"
                unit = "percent"
            elif "of which renewables" in fl:
                metric = "gfc_renewables_component_ktoe"
                unit = "ktoe"
            else:
                metric = "gfc_balance_ktoe"
                unit = "ktoe"
            v = _clean_numeric(raw)
            if v is None:
                continue
            out.append(
                (
                    dukes_table,
                    sheet_year,
                    None,
                    flow,
                    fuel,
                    metric,
                    v,
                    unit,
                    source_file,
                )
            )
    return out


def parse_overseas_trade_sheet(df: pd.DataFrame, dukes_table: str, source_file: str, sheet_tag: str) -> list[RowTuple]:
    """6.6.x: Imports / Exports blocks; years on same row as Imports/Exports label."""
    out: list[RowTuple] = []
    r = 0
    n = len(df)

    def year_cols_from_row(ri: int) -> list[tuple[int, int]]:
        cols: list[tuple[int, int]] = []
        for c in range(1, df.shape[1]):
            y = _year_token(df.iloc[ri, c])
            if y:
                cols.append((c, y))
        return cols

    while r < n:
        cell = _norm_label(df.iloc[r, 0]).lower()
        if "imports (tonnes)" in cell:
            trade = "imports"
            ycols = year_cols_from_row(r)
            r += 1
            while r < n:
                cl = _norm_label(df.iloc[r, 0]).lower()
                if "exports (tonnes)" in cl:
                    break
                row_lab = _norm_label(df.iloc[r, 0])
                if not row_lab:
                    r += 1
                    continue
                for c, yr in ycols:
                    v = _clean_numeric(df.iloc[r, c])
                    if v is None:
                        continue
                    out.append(
                        (
                            dukes_table,
                            yr,
                            None,
                            row_lab,
                            f"{sheet_tag}|{trade}",
                            "trade_tonnes",
                            v,
                            "tonnes",
                            source_file,
                        )
                    )
                r += 1
            continue
        if "exports (tonnes)" in cell:
            trade = "exports"
            ycols = year_cols_from_row(r)
            r += 1
            while r < n:
                row_lab = _norm_label(df.iloc[r, 0])
                ll = row_lab.lower()
                if not row_lab:
                    r += 1
                    continue
                if ll.startswith("source") or ll.startswith("©"):
                    break
                for c, yr in ycols:
                    v = _clean_numeric(df.iloc[r, c])
                    if v is None:
                        continue
                    out.append(
                        (
                            dukes_table,
                            yr,
                            None,
                            row_lab,
                            f"{sheet_tag}|{trade}",
                            "trade_tonnes",
                            v,
                            "tonnes",
                            source_file,
                        )
                    )
                r += 1
            continue
        r += 1
    return out


def parse_station_counts(
    path: Path,
    cfg: dict[str, Any],
    dukes_table: str,
    source_file: str,
) -> list[RowTuple]:
    sheet = cfg["sheet"]
    hr = int(cfg["header_row_0indexed"])
    d0 = int(cfg["data_start_row_0indexed"])
    snap = int(cfg.get("snapshot_year") or 2024)
    metric = cfg.get("metric_name", "station_count")
    unit = cfg.get("unit", "count")
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    headers = [ _norm_label(df.iloc[hr, c]) for c in range(1, df.shape[1]) ]
    out: list[RowTuple] = []
    for ri in range(d0, len(df)):
        tech = _norm_label(df.iloc[ri, 0])
        if not tech or tech.lower().startswith("total"):
            # keep Total row — optional
            pass
        if not tech:
            continue
        for ci, h in enumerate(headers, 1):
            if ci >= df.shape[1]:
                break
            v = _clean_numeric(df.iloc[ri, ci])
            if v is None:
                continue
            col = h if h else f"col_{ci}"
            out.append(
                (
                    dukes_table,
                    snap,
                    None,
                    tech,
                    col,
                    metric,
                    v,
                    unit,
                    source_file,
                )
            )
    return out


def load_chapter6_tables(
    settings: dict[str, Any],
    client: Any,
    logger: Any,
    reg: dict[str, Any],
    ddir: Path,
    timeout: int,
) -> None:
    import pipeline.ingest.ingest_dukes as ingest_dukes_mod

    _download = ingest_dukes_mod._download

    ch6 = reg.get("chapter6") or {}
    tables_cfg = ch6.get("tables") or {}
    if not tables_cfg:
        logger.info("DUKES Chapter 6: no tables in registry, skipping")
        return

    all_rows: list[RowTuple] = []

    for _key, cfg in tables_cfg.items():
        parser = cfg.get("parser")
        fn = cfg["filename"]
        dest = ddir / fn
        if not dest.exists():
            logger.info("Downloading DUKES Chapter 6 %s", fn)
            _download(cfg["url"], dest, timeout)
        dukes_table = str(cfg.get("table_id", "")).replace("DUKES_", "")
        source_file = fn

        if parser == "commodity_year_sheets":
            pat = re.compile(cfg.get("sheet_name_regex", r"^\d{4}$"))
            rows = parse_commodity_year_sheets(dest, cfg, dukes_table, source_file, pat)
            all_rows.extend(rows)
            logger.info("DUKES %s commodity_year_sheets: %s rows", dukes_table, len(rows))
            continue

        if parser == "multi_section_year_columns":
            sheet = cfg["sheet"]
            df = pd.read_excel(dest, sheet_name=sheet, header=None)
            if dukes_table == "6.2":
                rows = parse_multi_section_year_columns(df, dukes_table, source_file, _section_6_2)
            elif dukes_table == "6.3":
                rows = parse_multi_section_year_columns(df, dukes_table, source_file, _section_6_3)
            else:
                rows = []
            all_rows.extend(rows)
            logger.info("DUKES %s multi_section: %s rows", dukes_table, len(rows))
            continue

        if parser == "multi_section_year_columns_6_4":
            df = pd.read_excel(dest, sheet_name=cfg["sheet"], header=None)
            rows = parse_6_4_custom(df, dukes_table, source_file)
            all_rows.extend(rows)
            logger.info("DUKES 6.4: %s rows", len(rows))
            continue

        if parser == "dukes_6_5_bundle":
            xl = pd.ExcelFile(dest)
            for sh in cfg.get("sheets_summary", []):
                shname = sh["sheet"] if isinstance(sh, dict) else sh
                if shname not in xl.sheet_names:
                    continue
                df = pd.read_excel(dest, sheet_name=shname, header=None)
                rows = parse_multi_section_year_columns(df, dukes_table, source_file, _section_6_5_summary)
                all_rows.extend(rows)
                logger.info("DUKES 6.5 %s: %s rows", shname, len(rows))
            pat = re.compile(cfg.get("sheets_detail_regex", r"^\d{4}$"))
            hdr = int(cfg["detail_year_row_0indexed"])
            d0 = int(cfg["detail_data_start_0indexed"])
            detail_n = 0
            for sh in xl.sheet_names:
                if not pat.match(sh):
                    continue
                df = pd.read_excel(dest, sheet_name=sh, header=None)
                y = int(sh)
                rows = parse_dukes_6_5_detail_sheet(df, dukes_table, source_file, y, hdr, d0)
                detail_n += len(rows)
                all_rows.extend(rows)
            logger.info("DUKES 6.5 detail year sheets: %s rows", detail_n)
            continue

        if parser == "overseas_trade_by_country":
            xl = pd.ExcelFile(dest)
            for sh in cfg.get("sheets", []):
                if sh not in xl.sheet_names:
                    continue
                df = pd.read_excel(dest, sheet_name=sh, header=None)
                tag = sh.replace(".", "_")
                rows = parse_overseas_trade_sheet(df, dukes_table, source_file, tag)
                all_rows.extend(rows)
                logger.info("DUKES 6.6 %s: %s rows", sh, len(rows))
            continue

        if parser == "station_counts_snapshot":
            rows = parse_station_counts(dest, cfg, dukes_table, source_file)
            all_rows.extend(rows)
            logger.info("DUKES 6.7: %s rows", len(rows))
            continue

        logger.warning("Unknown Chapter 6 parser %s for %s", parser, fn)

    if not all_rows:
        logger.warning("DUKES Chapter 6: no rows parsed")
        return

    with client._conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO stg_dukes_chapter6 (
                dukes_table, period_year, period_label, row_label, column_label,
                metric_name, value, unit, source_file
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            all_rows,
        )
    logger.info("stg_dukes_chapter6: inserted %s rows", len(all_rows))

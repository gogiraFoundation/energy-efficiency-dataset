"""Load DUKES Excel tables into staging (Chapters 1, 4, 5, 6).

Chapter 1: https://www.gov.uk/government/statistics/energy-chapter-1-digest-of-united-kingdom-energy-statistics-dukes
Chapter 4: https://www.gov.uk/government/statistics/natural-gas-chapter-4-digest-of-united-kingdom-energy-statistics-dukes
Chapter 5: https://www.gov.uk/government/statistics/electricity-chapter-5-digest-of-united-kingdom-energy-statistics-dukes
Chapter 6: https://www.gov.uk/government/statistics/renewable-sources-of-energy-chapter-6-digest-of-united-kingdom-energy-statistics-dukes

Runs after JSONB raw ingest; creates/truncates ``stg_dukes_*`` and inserts parsed rows.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_registry() -> dict[str, Any]:
    path = REPO_ROOT / "metadata" / "dukes_registry.yaml"
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _dukes_dir(settings: dict) -> Path:
    raw = Path(settings["paths"]["raw_dir"])
    sub = settings["paths"].get("dukes_dir", "dukes")
    d = raw / sub
    d.mkdir(parents=True, exist_ok=True)
    return d


def _download(url: str, dest: Path, timeout: int) -> None:
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    dest.write_bytes(r.content)


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


def _ensure_tables(client, logger) -> None:
    for name in (
        "36_stg_dukes.sql",
        "37_stg_dukes_chapter6.sql",
        "38_stg_dukes_chapter1_sup.sql",
        "39_stg_dukes_chapter5.sql",
        "40_stg_dukes_chapter4.sql",
    ):
        sql_path = REPO_ROOT / "sql" / "staging" / name
        client.execute_file(str(sql_path))
        logger.info("DUKES staging DDL applied from %s", sql_path)


def _truncate_staging(client, logger) -> None:
    for t in (
        "stg_dukes_primary_consumption",
        "stg_dukes_energy_expenditure",
        "stg_dukes_final_consumption",
        "stg_dukes_primary_fuels",
        "stg_dukes_chapter1_sup",
        "stg_dukes_chapter4",
        "stg_dukes_chapter5",
        "stg_dukes_chapter6",
    ):
        client.execute(f"TRUNCATE TABLE {t};")
    logger.info("Truncated stg_dukes_* tables")


def _parse_primary_consumption(
    path: Path,
    cfg: dict[str, Any],
    mtoe_to_twh: float,
    source_file: str,
) -> list[tuple]:
    sheet = cfg["sheet"]
    h = int(cfg["header_row_0indexed"])
    d0 = int(cfg["data_start_row_0indexed"])
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    header = df.iloc[h].tolist()
    rows_out: list[tuple] = []
    # Expected columns from DUKES 2025 layout
    for ri in range(d0, len(df)):
        row = df.iloc[ri]
        year = _clean_numeric(row.iloc[0])
        if year is None or year < 1950 or year > 2100:
            continue
        y = int(year)
        pe = _clean_numeric(row.iloc[1])
        gdp = _clean_numeric(row.iloc[2])
        ratio = _clean_numeric(row.iloc[3])
        idx = _clean_numeric(row.iloc[4]) if len(row) > 4 else None
        mtoe = pe
        twh = (mtoe * mtoe_to_twh) if mtoe is not None else None
        rows_out.append((y, mtoe, twh, gdp, ratio, idx, source_file))
    return rows_out


def _parse_expenditure(
    path: Path,
    cfg: dict[str, Any],
    source_file: str,
) -> list[tuple]:
    sheet = cfg["sheet"]
    h = int(cfg["header_row_0indexed"])
    d0 = int(cfg["data_start_row_0indexed"])
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    headers = [str(c).strip() if c is not None and not pd.isna(c) else "" for c in df.iloc[h].tolist()]

    # Map Total columns to canonical sectors (DUKES 1.1.6 £ million)
    col_map: dict[int, str] = {}
    for i, name in enumerate(headers):
        nl = name.lower()
        if name.strip().startswith("Year"):
            continue
        if "total industry" in nl:
            col_map[i] = "industry"
        elif "total domestic" in nl:
            col_map[i] = "domestic"
        elif "of which road transport" in nl:
            col_map[i] = "transport_road"
        elif "total other final users" in nl:
            col_map[i] = "other_final_users"
        elif "total all final users" in nl:
            col_map[i] = "all_final_users"

    rows_out: list[tuple] = []
    for ri in range(d0, len(df)):
        row = df.iloc[ri]
        year_val = _clean_numeric(row.iloc[0])
        if year_val is None or year_val < 1950 or year_val > 2100:
            continue
        y = int(year_val)
        for ci, sector in col_map.items():
            exp = _clean_numeric(row.iloc[ci])
            if exp is None:
                continue
            rows_out.append((y, sector, exp, source_file))
    return rows_out


def _parse_final_consumption_sheet(
    path: Path,
    sheet_name: str,
    sector: str,
    header_row: int,
    data_start: int,
    ktoe_to_twh: float,
    source_file: str,
) -> list[tuple]:
    df = pd.read_excel(path, sheet_name=sheet_name, header=None)
    headers = df.iloc[header_row].tolist()
    rows_out: list[tuple] = []
    for ri in range(data_start, len(df)):
        row = df.iloc[ri]
        year_val = _clean_numeric(row.iloc[0])
        if year_val is None or year_val < 1950 or year_val > 2100:
            continue
        y = int(year_val)
        for ci in range(1, len(row)):
            fuel_label = headers[ci] if ci < len(headers) else None
            if fuel_label is None or str(fuel_label).strip() == "":
                continue
            fuel_type = re.sub(r"\s+", " ", str(fuel_label).strip())
            val = _clean_numeric(row.iloc[ci])
            if val is None:
                continue
            ktoe = val
            twh = ktoe * ktoe_to_twh
            rows_out.append((y, sector, fuel_type, ktoe, twh, source_file))
    return rows_out


def _parse_primary_fuels_b(
    path: Path,
    cfg: dict[str, Any],
    source_file: str,
) -> list[tuple]:
    sheet = cfg["sheet"]
    hy = int(cfg["header_year_row_0indexed"])
    d0 = int(cfg["data_start_row_0indexed"])
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    year_labels = df.iloc[hy].tolist()
    # columns 1.. are years (floats like 1970.0)
    year_cols: list[tuple[int, int]] = []
    for ci, lab in enumerate(year_labels):
        if ci == 0:
            continue
        yv = _clean_numeric(lab)
        if yv is None:
            continue
        if 1950 <= yv <= 2100:
            year_cols.append((ci, int(yv)))

    rows_out: list[tuple] = []
    for ri in range(d0, len(df)):
        label = df.iloc[ri, 0]
        if label is None or pd.isna(label):
            continue
        fuel_type = re.sub(r"\s+", " ", str(label).strip())
        if fuel_type.lower().startswith("column"):
            continue
        if "total" in fuel_type.lower() and "note" in fuel_type.lower():
            pass  # keep Total [note 6]
        for ci, year in year_cols:
            mtoe = _clean_numeric(df.iloc[ri, ci])
            if mtoe is None:
                continue
            rows_out.append((year, fuel_type, mtoe, source_file))
    return rows_out


def load_dukes(settings: dict, client, logger) -> None:
    reg = _load_registry()
    mtoe_to_twh = float(reg.get("mtoe_to_twh", 11.63))
    ktoe_to_twh = float(reg.get("ktoe_to_twh", 0.01163))
    timeout = int(settings.get("pipeline", {}).get("default_timeout_seconds", 180))
    tables = reg.get("tables", {})
    ddir = _dukes_dir(settings)

    _ensure_tables(client, logger)
    _truncate_staging(client, logger)

    # --- 1.1.4 ---
    pc = tables.get("primary_consumption_gdp", {})
    if pc:
        fn = pc["filename"]
        dest = ddir / fn
        if not dest.exists():
            logger.info("Downloading DUKES %s", fn)
            _download(pc["url"], dest, timeout)
        rows = _parse_primary_consumption(dest, pc, mtoe_to_twh, fn)
        if rows:
            with client._conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO stg_dukes_primary_consumption (
                        year, primary_energy_mtoe, primary_energy_twh, gdp_gbp_billion,
                        energy_ratio, energy_intensity_index_1970_100, source_file
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    rows,
                )
        logger.info("stg_dukes_primary_consumption: %s rows from %s", len(rows), fn)

    # --- 1.1.6 ---
    ex = tables.get("expenditure_final_user", {})
    if ex:
        fn = ex["filename"]
        dest = ddir / fn
        if not dest.exists():
            logger.info("Downloading DUKES %s", fn)
            _download(ex["url"], dest, timeout)
        rows = _parse_expenditure(dest, ex, fn)
        if rows:
            with client._conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO stg_dukes_energy_expenditure (year, sector, expenditure_million_gbp, source_file)
                    VALUES (%s, %s, %s, %s)
                    """,
                    rows,
                )
        logger.info("stg_dukes_energy_expenditure: %s rows from %s", len(rows), fn)

    # --- 1.1.5 ---
    fc = tables.get("final_consumption_by_user", {})
    if fc:
        fn = fc["filename"]
        dest = ddir / fn
        if not dest.exists():
            logger.info("Downloading DUKES %s", fn)
            _download(fc["url"], dest, timeout)
        hr = int(fc["header_row_0indexed"])
        dr = int(fc["data_start_row_0indexed"])
        all_rows: list[tuple] = []
        for sh in fc.get("sheets", []):
            all_rows.extend(
                _parse_final_consumption_sheet(
                    dest, sh["sheet"], str(sh["sector"]), hr, dr, ktoe_to_twh, fn
                )
            )
        if all_rows:
            with client._conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO stg_dukes_final_consumption (
                        year, sector, fuel_type, energy_ktoe, energy_twh, source_file
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    all_rows,
                )
        logger.info("stg_dukes_final_consumption: %s rows from %s", len(all_rows), fn)

    # --- 1.1.1.B primary fuels (Mtoe) ---
    pf = tables.get("primary_fuels_mtoe", {})
    if pf:
        fn = pf["filename"]
        dest = ddir / fn
        if not dest.exists():
            logger.info("Downloading DUKES %s", fn)
            _download(pf["url"], dest, timeout)
        rows = _parse_primary_fuels_b(dest, pf, fn)
        if rows:
            with client._conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO stg_dukes_primary_fuels (year, fuel_type, consumption_mtoe, source_file)
                    VALUES (%s, %s, %s, %s)
                    """,
                    rows,
                )
        logger.info("stg_dukes_primary_fuels: %s rows from %s", len(rows), fn)

    from pipeline.ingest.dukes_chapter1_sup import load_chapter1_supplementary_tables
    from pipeline.ingest.dukes_chapter4 import load_chapter4_tables
    from pipeline.ingest.dukes_chapter5 import load_chapter5_tables
    from pipeline.ingest.dukes_chapter6 import load_chapter6_tables

    load_chapter1_supplementary_tables(settings, client, logger, reg, ddir, timeout)
    load_chapter4_tables(settings, client, logger, reg, ddir, timeout)
    load_chapter5_tables(settings, client, logger, reg, ddir, timeout)
    load_chapter6_tables(settings, client, logger, reg, ddir, timeout)

    logger.info("DUKES ingest completed")

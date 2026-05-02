"""Load ONS Physical energy flow accounts (PEFA) xlsx into staging.

Official statistics:
https://www.ons.gov.uk/economy/environmentalaccounts/datasets/physicalenergyflowaccountspefa

Runs after raw JSONB ingest and DUKES; applies ``37_stg_pefa.sql`` and loads
``stg_pefa_matrix`` / ``stg_pefa_bridge``. Values are terajoules (TJ).
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
    path = REPO_ROOT / "metadata" / "pefa_registry.yaml"
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _pefa_dir(settings: dict) -> Path:
    raw = Path(settings["paths"]["raw_dir"])
    sub = settings["paths"].get("pefa_dir", "pefa")
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


def _extract_reference_year(df: pd.DataFrame) -> int | None:
    cell = df.iloc[0, 0] if df.shape[0] > 0 and df.shape[1] > 0 else None
    if cell is None or (isinstance(cell, float) and pd.isna(cell)):
        return None
    m = re.search(r"(19|20)\d{2}", str(cell))
    if not m:
        return None
    return int(m.group(0))


def _parse_matrix_table(
    df: pd.DataFrame,
    cfg: dict[str, Any],
    ref_year: int,
    source_file: str,
) -> list[tuple]:
    hr = int(cfg["header_row_0indexed"])
    d0 = int(cfg["data_start_row_0indexed"])
    fc = int(cfg["first_industry_col_0indexed"])
    step = int(cfg["industry_col_step"])
    tid = str(cfg["table_id"])

    ncols = df.shape[1]
    industry_cols: list[int] = []
    for c in range(fc, ncols, step):
        lab = df.iloc[hr, c] if c < ncols else None
        if lab is None or (isinstance(lab, float) and pd.isna(lab)):
            continue
        s = str(lab).strip()
        if not s:
            continue
        industry_cols.append(c)

    rows_out: list[tuple] = []
    for ri in range(d0, len(df)):
        code_raw = df.iloc[ri, 2]
        label_raw = df.iloc[ri, 3]
        if (code_raw is None or (isinstance(code_raw, float) and pd.isna(code_raw))) and (
            label_raw is None or (isinstance(label_raw, float) and pd.isna(label_raw))
        ):
            continue
        rno = _clean_numeric(df.iloc[ri, 0])
        row_no = int(rno) if rno is not None else None
        rl = _clean_numeric(df.iloc[ri, 1])
        row_level = int(rl) if rl is not None else None
        row_code = None if code_raw is None or pd.isna(code_raw) else str(code_raw).strip()
        row_label = None if label_raw is None or pd.isna(label_raw) else str(label_raw).strip()

        for c in industry_cols:
            ind = df.iloc[hr, c]
            industry_code = str(ind).strip() if ind is not None and not pd.isna(ind) else None
            val = _clean_numeric(df.iloc[ri, c])
            if val is None:
                continue
            rows_out.append(
                (
                    ref_year,
                    tid,
                    row_no,
                    row_level,
                    row_code,
                    row_label,
                    c,
                    industry_code,
                    val,
                    source_file,
                )
            )
    return rows_out


def _parse_indicator_table(
    df: pd.DataFrame,
    cfg: dict[str, Any],
    ref_year: int,
    source_file: str,
) -> list[tuple]:
    hr = int(cfg["header_row_0indexed"])
    d0 = int(cfg["data_start_row_0indexed"])
    nc = int(cfg["no_col_0indexed"])
    cc = int(cfg["code_col_0indexed"])
    lc = int(cfg["label_col_0indexed"])
    fc = int(cfg["first_industry_col_0indexed"])
    step = int(cfg["industry_col_step"])
    tid = str(cfg["table_id"])

    ncols = df.shape[1]
    industry_cols: list[int] = []
    for c in range(fc, ncols, step):
        lab = df.iloc[hr, c] if c < ncols else None
        if lab is None or (isinstance(lab, float) and pd.isna(lab)):
            continue
        s = str(lab).strip()
        if not s:
            continue
        industry_cols.append(c)

    rows_out: list[tuple] = []
    for ri in range(d0, len(df)):
        code_raw = df.iloc[ri, cc]
        label_raw = df.iloc[ri, lc]
        if code_raw is None or (isinstance(code_raw, float) and pd.isna(code_raw)):
            continue
        row_code = str(code_raw).strip()
        row_label = None if label_raw is None or pd.isna(label_raw) else str(label_raw).strip()
        rno = _clean_numeric(df.iloc[ri, nc])
        row_no = int(rno) if rno is not None else None

        for c in industry_cols:
            ind = df.iloc[hr, c]
            industry_code = str(ind).strip() if ind is not None and not pd.isna(ind) else None
            val = _clean_numeric(df.iloc[ri, c])
            if val is None:
                continue
            rows_out.append(
                (
                    ref_year,
                    tid,
                    row_no,
                    None,
                    row_code,
                    row_label,
                    c,
                    industry_code,
                    val,
                    source_file,
                )
            )
    return rows_out


def _parse_bridge_table(
    df: pd.DataFrame,
    cfg: dict[str, Any],
    ref_year: int,
    source_file: str,
) -> list[tuple]:
    d0 = int(cfg["data_start_row_0indexed"])
    cc = int(cfg["code_col_0indexed"])
    lc = int(cfg["label_col_0indexed"])
    vc = int(cfg["value_col_0indexed"])

    rows_out: list[tuple] = []
    for ri in range(d0, len(df)):
        code_raw = df.iloc[ri, cc]
        if code_raw is None or (isinstance(code_raw, float) and pd.isna(code_raw)):
            continue
        code_s = str(code_raw).strip()
        if not code_s:
            continue
        if code_s.lower().startswith("explanations") or code_s.lower() == "notes":
            break
        label_raw = df.iloc[ri, lc]
        bridge_label = None if label_raw is None or pd.isna(label_raw) else str(label_raw).strip()
        val = _clean_numeric(df.iloc[ri, vc])
        if val is None:
            continue
        rows_out.append((ref_year, code_s, bridge_label, val, source_file))
    return rows_out


def _ensure_tables(client: Any, logger: Any) -> None:
    sql_path = REPO_ROOT / "sql" / "staging" / "37_stg_pefa.sql"
    client.execute_file(str(sql_path))
    logger.info("PEFA staging DDL applied from %s", sql_path)


def _truncate_staging(client: Any, logger: Any) -> None:
    for t in ("stg_pefa_matrix", "stg_pefa_bridge"):
        client.execute(f"TRUNCATE TABLE {t};")
    logger.info("Truncated stg_pefa_* tables")


def load_pefa(settings: dict, client: Any, logger: Any) -> None:
    reg = _load_registry()
    timeout = int(settings.get("pipeline", {}).get("default_timeout_seconds", 180))
    edition_key = str(reg.get("default_edition", "2023revised"))
    editions = reg.get("editions") or {}
    ed = editions.get(edition_key)
    if not ed:
        logger.warning("PEFA edition %r not in registry; skip load_pefa", edition_key)
        return

    fn = ed["filename"]
    url = ed["url"]
    dest = _pefa_dir(settings) / fn
    if not dest.exists():
        logger.info("Downloading PEFA %s", fn)
        _download(url, dest, timeout)

    _ensure_tables(client, logger)
    _truncate_staging(client, logger)

    matrix_cfgs = reg.get("matrix_tables") or []
    ind_cfg = reg.get("indicator_table") or {}
    bridge_cfg = reg.get("bridge_table") or {}

    matrix_rows: list[tuple] = []
    bridge_rows: list[tuple] = []

    for mc in matrix_cfgs:
        sheet = str(mc["sheet"])
        df = pd.read_excel(dest, sheet_name=sheet, header=None)
        ref_year = _extract_reference_year(df)
        if ref_year is None:
            logger.error("PEFA %s: could not parse reference year from sheet title", sheet)
            continue
        matrix_rows.extend(_parse_matrix_table(df, mc, ref_year, fn))

    if ind_cfg:
        sheet = str(ind_cfg["sheet"])
        df = pd.read_excel(dest, sheet_name=sheet, header=None)
        ref_year = _extract_reference_year(df)
        if ref_year is None:
            logger.error("PEFA Table D: could not parse reference year")
        else:
            matrix_rows.extend(_parse_indicator_table(df, ind_cfg, ref_year, fn))

    if bridge_cfg:
        sheet = str(bridge_cfg["sheet"])
        df = pd.read_excel(dest, sheet_name=sheet, header=None)
        ref_year = _extract_reference_year(df)
        if ref_year is None:
            logger.error("PEFA Table E: could not parse reference year")
        else:
            bridge_rows.extend(_parse_bridge_table(df, bridge_cfg, ref_year, fn))

    if matrix_rows:
        with client._conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO stg_pefa_matrix (
                    reference_year, table_id, row_no, row_level, row_code, row_label,
                    industry_column_index, industry_code, energy_tj, source_file
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                matrix_rows,
            )
    logger.info("stg_pefa_matrix: %s rows from %s", len(matrix_rows), fn)

    if bridge_rows:
        with client._conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO stg_pefa_bridge (
                    reference_year, bridge_code, bridge_label, energy_tj, source_file
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                bridge_rows,
            )
    logger.info("stg_pefa_bridge: %s rows from %s", len(bridge_rows), fn)

    logger.info("PEFA ingest completed")

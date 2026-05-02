"""Load extracted everviz CSV files into raw_xlsx_* tables."""

from __future__ import annotations

import logging
import re
from io import StringIO
from pathlib import Path

import pandas as pd

from pipeline.ingest.load_xlsx import _parse_quarter, _upsert_rows

SRC_PREFIX = "everviz"


def _obligation_start_year(period: str) -> int | None:
    period = str(period).strip().strip('"')
    m = re.match(r"(\d{4})-(\d{2})$", period)
    if m:
        return int(m.group(1))
    return None


def _quarter_from_month_token(month: str, obligation_col: str) -> tuple[int | None, int | None]:
    """Map RO chart month + obligation period header to (calendar_year, calendar_quarter)."""
    start_y = _obligation_start_year(obligation_col)
    if start_y is None:
        return None, None
    mabbr = str(month).strip()[:3].title()
    month_idx = {
        "Apr": 4,
        "May": 5,
        "Jun": 6,
        "Jul": 7,
        "Aug": 8,
        "Sep": 9,
        "Oct": 10,
        "Nov": 11,
        "Dec": 12,
        "Jan": 1,
        "Feb": 2,
        "Mar": 3,
    }.get(mabbr)
    if month_idx is None:
        return None, None
    cal_year = start_y if month_idx >= 4 else start_y + 1
    cq = (month_idx - 1) // 3 + 1
    return cal_year, cq


def _parse_quarter_cell(label: str) -> tuple[int | None, int | None]:
    label = str(label).strip().strip('"')
    inner = re.search(r"\(\s*(Quarter\s+\d\s+\d{4})\s*\)", label, re.I)
    if inner:
        label = inner.group(1)
    q = _parse_quarter(label)
    if q:
        return q
    q = _parse_quarter(label.replace("Quarter", "Q").replace("  ", " "))
    return q if q else (None, None)


def _read_csv(path: Path) -> pd.DataFrame:
    """Everviz exports mix comma- and semicolon-separated tables."""
    raw = path.read_text(encoding="utf-8")
    sep = ";" if raw.count(";") > raw.count(",") else ","
    return pd.read_csv(StringIO(raw), sep=sep, dtype=str)


def _dedupe_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Keep first occurrence when everviz sheets accidentally duplicate column names."""
    seen: dict[str, int] = {}
    cols = []
    for c in df.columns:
        base = str(c)
        if base in seen:
            seen[base] += 1
            cols.append(f"{base}__dup{seen[base]}")
        else:
            seen[base] = 0
            cols.append(base)
    df = df.copy()
    df.columns = cols
    return df[[c for c in df.columns if "__dup" not in c]]


def load_credit_balances(path: Path, chart_id: str, logger: logging.Logger) -> list[dict]:
    df = _dedupe_columns(_read_csv(path))
    rows: list[dict] = []
    src = f"{SRC_PREFIX}:{chart_id}"
    if chart_id == "c_y_Dm7Rx":
        for _, r in df.iterrows():
            label = r.iloc[0]
            if pd.isna(label) or str(label).strip().lower().startswith("£"):
                continue
            yq = _parse_quarter(str(label).strip().strip('"'))
            if not yq:
                yq = _parse_quarter_cell(str(label))
            if not yq:
                continue
            year, quarter = yq
            v1 = pd.to_numeric(r.iloc[1], errors="coerce")
            v2 = pd.to_numeric(r.iloc[2], errors="coerce") if len(r) > 2 else None
            if v1 is not None and not pd.isna(v1):
                rows.append(
                    {
                        "period_date": None,
                        "period_label": str(label).strip(),
                        "year": year,
                        "quarter": quarter,
                        "commodity": "dual_fuel",
                        "payment_method": "direct_debit",
                        "supplier_group": None,
                        "supplier_size": None,
                        "segment": None,
                        "tariff_type": None,
                        "component": "credit_balance",
                        "metric_name": "credit_balance_total_bn_gbp",
                        "value": float(v1),
                        "unit": "gbp_billion",
                        "source_file": src,
                    }
                )
            if v2 is not None and not pd.isna(v2):
                rows.append(
                    {
                        "period_date": None,
                        "period_label": str(label).strip(),
                        "year": year,
                        "quarter": quarter,
                        "commodity": "dual_fuel",
                        "payment_method": "direct_debit",
                        "supplier_group": None,
                        "supplier_size": None,
                        "segment": None,
                        "tariff_type": None,
                        "component": "credit_balance",
                        "metric_name": "credit_balance_total_rolling12_bn_gbp",
                        "value": float(v2),
                        "unit": "gbp_billion",
                        "source_file": src,
                    }
                )
    elif chart_id == "fpptIG0Jf":
        for _, r in df.iterrows():
            label = r.iloc[0]
            if pd.isna(label) or "Household" not in str(label):
                continue
            yq = _parse_quarter_cell(str(label))
            if not yq:
                continue
            year, quarter = yq
            v1 = pd.to_numeric(r.iloc[1], errors="coerce")
            v2 = pd.to_numeric(r.iloc[2], errors="coerce") if len(r) > 2 else None
            if v1 is not None and not pd.isna(v1):
                rows.append(
                    {
                        "period_date": None,
                        "period_label": str(label).strip(),
                        "year": year,
                        "quarter": quarter,
                        "commodity": "dual_fuel",
                        "payment_method": "direct_debit",
                        "supplier_group": None,
                        "supplier_size": None,
                        "segment": None,
                        "tariff_type": None,
                        "component": "credit_balance",
                        "metric_name": "credit_balance_household_quarter_avg_gbp",
                        "value": float(v1),
                        "unit": "gbp",
                        "source_file": src,
                    }
                )
            if v2 is not None and not pd.isna(v2):
                rows.append(
                    {
                        "period_date": None,
                        "period_label": str(label).strip(),
                        "year": year,
                        "quarter": quarter,
                        "commodity": "dual_fuel",
                        "payment_method": "direct_debit",
                        "supplier_group": None,
                        "supplier_size": None,
                        "segment": None,
                        "tariff_type": None,
                        "component": "credit_balance",
                        "metric_name": "credit_balance_household_rolling12_avg_gbp",
                        "value": float(v2),
                        "unit": "gbp",
                        "source_file": src,
                    }
                )
    elif chart_id == "6EgYhkmDg":
        cols = list(df.columns)
        if len(cols) < 4:
            return rows
        metrics_map = {
            cols[1]: "credit_balance_quartile_lower_gbp",
            cols[2]: "credit_balance_quartile_median_gbp",
            cols[3]: "credit_balance_quartile_upper_gbp",
        }
        for _, r in df.iterrows():
            label = r.iloc[0]
            if pd.isna(label) or str(label).strip().lower().startswith("£"):
                continue
            yq = _parse_quarter(str(label).strip().strip('"'))
            if not yq:
                continue
            year, quarter = yq
            for col_name, metric_name in metrics_map.items():
                v = pd.to_numeric(r[col_name], errors="coerce")
                if v is None or pd.isna(v):
                    continue
                rows.append(
                    {
                        "period_date": None,
                        "period_label": str(label).strip(),
                        "year": year,
                        "quarter": quarter,
                        "commodity": "dual_fuel",
                        "payment_method": "direct_debit",
                        "supplier_group": None,
                        "supplier_size": None,
                        "segment": None,
                        "tariff_type": None,
                        "component": "credit_balance",
                        "metric_name": metric_name,
                        "value": float(v),
                        "unit": "gbp",
                        "source_file": src,
                    }
                )
    else:
        logger.warning("unknown credit chart_id=%s", chart_id)
    return rows


def load_fit_complaints(path: Path, chart_id: str, logger: logging.Logger) -> list[dict]:
    df = _read_csv(path)
    rows: list[dict] = []
    src = f"{SRC_PREFIX}:{chart_id}"
    entity_col = df.columns[0]
    for _, r in df.iterrows():
        token = r[entity_col]
        if pd.isna(token):
            continue
        yq = _parse_quarter(str(token).strip())
        if not yq:
            continue
        year, quarter = yq
        for col in df.columns[1:]:
            val = pd.to_numeric(r[col], errors="coerce")
            if val is None or pd.isna(val):
                continue
            rows.append(
                {
                    "period_date": None,
                    "period_label": str(token).strip(),
                    "year": year,
                    "quarter": quarter,
                    "supplier_name": str(col).strip(),
                    "segment": None,
                    "commodity": "electricity",
                    "metric_name": "fit_complaints_per_1000_accounts",
                    "value": float(val),
                    "unit": "rate_per_1000",
                    "source_file": src,
                }
            )
    return rows


def load_rocs_by_technology(path: Path, chart_id: str, logger: logging.Logger) -> list[dict]:
    df = _dedupe_columns(_read_csv(path))
    rows: list[dict] = []
    src = f"{SRC_PREFIX}:{chart_id}"
    tech_col = df.columns[0]
    for _, r in df.iterrows():
        tech = str(r[tech_col]).strip().strip('"')
        if not tech or tech.lower() in {"technology type", "technology (simplified)"}:
            continue
        for col in df.columns[1:]:
            ob = str(col).strip().strip('"')
            yr = _obligation_start_year(ob)
            if yr is None:
                continue
            v = pd.to_numeric(r[col], errors="coerce")
            if v is None or pd.isna(v):
                continue
            rows.append(
                {
                    "period_date": None,
                    "period_label": ob,
                    "year": yr,
                    "quarter": None,
                    "technology": tech,
                    "region": None,
                    "installation_type": None,
                    "metric_name": "rocs_issued_millions",
                    "value": float(v),
                    "unit": "million_rocs",
                    "source_file": src,
                }
            )
    return rows


def load_rocs_monthly(path: Path, chart_id: str, logger: logging.Logger) -> list[dict]:
    df = _dedupe_columns(_read_csv(path))
    rows: list[dict] = []
    src = f"{SRC_PREFIX}:{chart_id}"
    month_col = df.columns[0]
    for _, r in df.iterrows():
        month = str(r[month_col]).strip().strip('"')
        if not month or month.lower().startswith("ro year"):
            continue
        for col in df.columns[1:]:
            ob = str(col).strip().strip('"')
            yr = _obligation_start_year(ob)
            if yr is None:
                continue
            v = pd.to_numeric(r[col], errors="coerce")
            if v is None or pd.isna(v):
                continue
            cal_y, cq = _quarter_from_month_token(month, ob)
            rows.append(
                {
                    "period_date": None,
                    "period_label": f"{month}|{ob}",
                    "year": cal_y or yr,
                    "quarter": cq,
                    "technology": None,
                    "region": None,
                    "installation_type": None,
                    "metric_name": "rocs_monthly_millions",
                    "value": float(v),
                    "unit": "million_rocs",
                    "source_file": src,
                }
            )
    return rows


def load_capacity_by_technology(path: Path, chart_id: str, logger: logging.Logger) -> list[dict]:
    df = _dedupe_columns(_read_csv(path))
    rows: list[dict] = []
    src = f"{SRC_PREFIX}:{chart_id}"
    tech_col = df.columns[0]
    for _, r in df.iterrows():
        tech = str(r[tech_col]).strip().strip('"')
        if not tech or tech.lower().startswith("technology"):
            continue
        for col in df.columns[1:]:
            ob = str(col).strip().strip('"')
            yr = _obligation_start_year(ob)
            if yr is None:
                continue
            v = pd.to_numeric(r[col], errors="coerce")
            if v is None or pd.isna(v):
                continue
            rows.append(
                {
                    "period_date": None,
                    "period_label": ob,
                    "year": yr,
                    "quarter": None,
                    "technology": tech,
                    "region": None,
                    "installation_type": None,
                    "metric_name": "accredited_capacity_mw",
                    "value": float(v),
                    "unit": "mw",
                    "source_file": src,
                }
            )
    return rows


_STATION_LABEL = re.compile(
    r"^(?P<mon>[A-Za-z]{3})\s*-\s*(?P<yy>\d{2})\s*\*?$",
    re.IGNORECASE,
)


_MONTH_ABBR = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


def _parse_station_effective_month(label: str) -> tuple[int | None, int | None]:
    """Anchor labels like ``Apr-02`` / ``Apr 19*`` to (calendar_year, calendar_quarter)."""
    s = str(label).strip().strip('"').replace(" ", "")
    m = _STATION_LABEL.match(s)
    if not m:
        return None, None
    mon_abbr = m.group("mon").title()[:3]
    yy = int(m.group("yy"))
    year = 2000 + yy if yy < 70 else 1900 + yy
    month_num = _MONTH_ABBR.get(mon_abbr)
    if month_num is None:
        return None, None
    cq = (month_num - 1) // 3 + 1
    return year, cq


def load_stations_cumulative(path: Path, chart_id: str, logger: logging.Logger) -> list[dict]:
    df = _read_csv(path)
    rows: list[dict] = []
    src = f"{SRC_PREFIX}:{chart_id}"
    if len(df.columns) < 2:
        return rows
    label_col, val_col = df.columns[0], df.columns[1]
    metric = (
        "accredited_stations_cumulative_over50kw"
        if chart_id == "fhZjZWpFM"
        else "accredited_stations_cumulative_all"
    )
    for _, r in df.iterrows():
        label = str(r[label_col]).strip().strip('"')
        if not label or label.lower().startswith("month"):
            continue
        v = pd.to_numeric(r[val_col], errors="coerce")
        if v is None or pd.isna(v):
            continue
        cal_y, cq = _parse_station_effective_month(label)
        rows.append(
            {
                "period_date": None,
                "period_label": label,
                "year": cal_y,
                "quarter": cq,
                "technology": None,
                "region": None,
                "installation_type": None,
                "metric_name": metric,
                "value": float(v),
                "unit": "stations",
                "source_file": src,
            }
        )
    return rows


CHART_HANDLERS = {
    "c_y_Dm7Rx": load_credit_balances,
    "fpptIG0Jf": load_credit_balances,
    "6EgYhkmDg": load_credit_balances,
    "967faU9lS": load_fit_complaints,
    "M3eryTIgn": load_rocs_by_technology,
    "1PVEsSF5h": load_rocs_monthly,
    "qVunmJEFF": load_capacity_by_technology,
    "g6Gow9Uf8": load_stations_cumulative,
    "fhZjZWpFM": load_stations_cumulative,
}


def load_all_ofgem_portal(settings: dict, client, logger: logging.Logger) -> None:
    extract_dir = Path(settings["paths"].get("portal_extract_dir", "data/ofgem_portal_extracted"))
    if not extract_dir.is_dir():
        logger.warning("portal extract dir missing: %s — run fetch_ofgem_portal first", extract_dir)
        return

    client.execute_file("sql/raw/06_create_raw_xlsx_retail_tables.sql")
    client.execute_file("sql/raw/07_create_raw_xlsx_renewables_whd.sql")

    total = 0
    for chart_id, handler in CHART_HANDLERS.items():
        path = extract_dir / f"{chart_id}.csv"
        if not path.exists():
            logger.warning("portal CSV missing, skipping chart_id=%s", chart_id)
            continue
        rows = handler(path, chart_id, logger)
        if not rows:
            logger.warning("portal loader produced 0 rows for %s", chart_id)
            continue
        if chart_id in {"c_y_Dm7Rx", "fpptIG0Jf", "6EgYhkmDg"}:
            n = _upsert_rows(client, "raw_xlsx_retail_timeseries", rows, logger)
        elif chart_id == "967faU9lS":
            n = _upsert_rows(client, "raw_xlsx_supplier_metric", rows, logger)
        else:
            n = _upsert_rows(client, "raw_xlsx_renewables", rows, logger)
        logger.info("portal load %s -> %d upserts", chart_id, n)
        total += n
    logger.info("portal load complete (%d row upserts)", total)

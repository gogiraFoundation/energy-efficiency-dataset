"""Loader for the 38 Ofgem Data Portal xlsx files.

Reads ``metadata/xlsx_registry.yaml`` and ``metadata/riio_periods.yaml``, then
for every entry:

1. Opens the source xlsx with openpyxl/pandas.
2. Dispatches to one of five parser strategies (see registry comments).
3. Normalises rows to the appropriate ``raw_xlsx_*`` schema (network, share,
   or market shape).
4. Idempotently upserts rows via ``INSERT ... ON CONFLICT ... DO UPDATE`` keyed
   on the table's ``UNIQUE NULLS NOT DISTINCT`` constraint.
5. Records a row in ``etl_run_log`` (status ``loaded`` or ``failed``).

The loader is designed to keep going on per-file errors unless
``settings.pipeline.fail_fast`` is true.
"""
from __future__ import annotations

import logging
import math
import re
import traceback
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd
import yaml

from pipeline.utils.validators import resolve_period_to_year, unpivot_wide_riio


# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------

NETWORK_TABLES = {
    "raw_xlsx_reliability",
    "raw_xlsx_expenditure",
    "raw_xlsx_rore",
    "raw_xlsx_customer_satisfaction",
    "raw_xlsx_emissions",
    "raw_xlsx_connections",
    "raw_xlsx_fuel_poor",
    "raw_xlsx_undergrounding",
    "raw_xlsx_network_availability",
    "raw_xlsx_risk_reduction",
}
SHARE_TABLES = {"raw_xlsx_generation_share"}
MARKET_TABLES = {
    "raw_xlsx_market_prices",
    "raw_xlsx_market_volumes",
    "raw_xlsx_generation_mix",
    "raw_xlsx_gas_supply",
    "raw_xlsx_estimated_costs",
}
RETAIL_SUPPLIER_TABLES = {"raw_xlsx_supplier_metric"}
RETAIL_TIMESERIES_TABLES = {"raw_xlsx_retail_timeseries"}
RETAIL_SNAPSHOT_TABLES = {"raw_xlsx_retail_snapshot"}

NETWORK_COLUMNS = (
    "year",
    "company_name",
    "network_sector",
    "metric_name",
    "value",
    "unit",
    "source_file",
)
SHARE_COLUMNS = ("year", "company_name", "metric_name", "value", "unit", "source_file")
MARKET_COLUMNS = (
    "period_date",
    "period_label",
    "year",
    "commodity",
    "instrument",
    "metric_name",
    "value",
    "unit",
    "source_file",
)
RETAIL_SUPPLIER_COLUMNS = (
    "period_date",
    "period_label",
    "year",
    "quarter",
    "supplier_name",
    "segment",
    "commodity",
    "metric_name",
    "value",
    "unit",
    "source_file",
)
RETAIL_TIMESERIES_COLUMNS = (
    "period_date",
    "period_label",
    "year",
    "quarter",
    "commodity",
    "payment_method",
    "supplier_group",
    "supplier_size",
    "segment",
    "tariff_type",
    "component",
    "metric_name",
    "value",
    "unit",
    "source_file",
)
RETAIL_SNAPSHOT_COLUMNS = (
    "year",
    "category",
    "supplier_name",
    "segment",
    "commodity",
    "payment_method",
    "supplier_size",
    "aspect",
    "component",
    "tariff_type",
    "metric_name",
    "value",
    "unit",
    "source_file",
)

# Constraint names defined in sql/raw/05_create_raw_xlsx_tables.sql and 06_create_raw_xlsx_retail_tables.sql
TABLE_CONSTRAINT = {
    "raw_xlsx_reliability": "raw_xlsx_reliability_natural_uniq",
    "raw_xlsx_expenditure": "raw_xlsx_expenditure_natural_uniq",
    "raw_xlsx_rore": "raw_xlsx_rore_natural_uniq",
    "raw_xlsx_customer_satisfaction": "raw_xlsx_customer_satisfaction_natural_uniq",
    "raw_xlsx_emissions": "raw_xlsx_emissions_natural_uniq",
    "raw_xlsx_connections": "raw_xlsx_connections_natural_uniq",
    "raw_xlsx_fuel_poor": "raw_xlsx_fuel_poor_natural_uniq",
    "raw_xlsx_undergrounding": "raw_xlsx_undergrounding_natural_uniq",
    "raw_xlsx_network_availability": "raw_xlsx_network_availability_natural_uniq",
    "raw_xlsx_risk_reduction": "raw_xlsx_risk_reduction_natural_uniq",
    "raw_xlsx_generation_share": "raw_xlsx_generation_share_natural_uniq",
    "raw_xlsx_market_prices": "raw_xlsx_market_prices_natural_uniq",
    "raw_xlsx_market_volumes": "raw_xlsx_market_volumes_natural_uniq",
    "raw_xlsx_generation_mix": "raw_xlsx_generation_mix_natural_uniq",
    "raw_xlsx_gas_supply": "raw_xlsx_gas_supply_natural_uniq",
    "raw_xlsx_estimated_costs": "raw_xlsx_estimated_costs_natural_uniq",
    "raw_xlsx_supplier_metric": "raw_xlsx_supplier_metric_natural_uniq",
    "raw_xlsx_retail_timeseries": "raw_xlsx_retail_timeseries_natural_uniq",
    "raw_xlsx_retail_snapshot": "raw_xlsx_retail_snapshot_natural_uniq",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_float(v: Any) -> float | None:
    """Best-effort numeric coercion. Returns None for blanks / NaN / 'null'."""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, str):
        s = v.strip()
        if s == "" or s.lower() == "null" or s == "-":
            return None
        try:
            return float(s.replace(",", ""))
        except ValueError:
            return None
    try:
        f = float(v)
        if math.isnan(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _snake(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")


def _resolve_metric_via_map(label: Any, metric_map: Mapping[str, str], substring: bool) -> str | None:
    """Resolve a column label to a canonical metric name via metric_map."""
    if label is None or metric_map is None:
        return None
    text = str(label).strip()
    if substring:
        text_lower = text.lower()
        for key, canon in metric_map.items():
            if key.lower() in text_lower:
                return canon
        return None
    return metric_map.get(text)


def _parse_year_from_label(label: Any) -> int | None:
    """Parse a 4-digit year from a year-label cell like '2013-14' or '2013'."""
    if label is None:
        return None
    s = str(label).strip()
    m = re.search(r"(\d{4})\s*[-/\s]\s*(\d{2,4})", s)
    if m:
        a, b = m.group(1), m.group(2)
        if len(b) == 2:
            return int(a[:2] + b)
        return int(b)
    m = re.search(r"(\d{4})", s)
    if m:
        return int(m.group(1))
    return None


_QUARTER_LEAD = re.compile(r"^\s*Q(\d)\s+(\d{4})\s*$", re.IGNORECASE)
_QUARTER_TRAIL = re.compile(r"^\s*(\d{4})\s+Q(\d)\s*$", re.IGNORECASE)
_HALF_YEAR_WINTER = re.compile(r"^\s*(\d{4})\s*[/]\s*(\d{2,4})\s+winter\s*\*?\s*$", re.IGNORECASE)
_HALF_YEAR_SUMMER = re.compile(r"^\s*(\d{4})\s+summer\s*\*?\s*$", re.IGNORECASE)


def _parse_quarter(value: Any) -> tuple[int, int] | None:
    """Return (year, quarter) for 'Q1 2013', '2013 Q1', or datetime values; else None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.year, ((value.month - 1) // 3) + 1
    if isinstance(value, date):
        return value.year, ((value.month - 1) // 3) + 1
    s = str(value).strip()
    if not s:
        return None
    m = _QUARTER_LEAD.match(s) or _QUARTER_TRAIL.match(s)
    if m:
        groups = m.groups()
        if _QUARTER_LEAD.match(s):
            q, y = int(groups[0]), int(groups[1])
        else:
            y, q = int(groups[0]), int(groups[1])
        if 1 <= q <= 4 and 1900 <= y <= 2100:
            return y, q
    return None


def _parse_half_year(value: Any) -> tuple[int, int, str] | None:
    """Return (year, quarter, season) for '2018/19 winter' / '2019 summer'; else None."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    m = _HALF_YEAR_WINTER.match(s)
    if m:
        # 'YYYY/yy winter' covers Oct(year) - Mar(year+1). Anchor at Q1 of the trailing year.
        first = int(m.group(1))
        second = m.group(2)
        if len(second) == 2:
            year_end = int(str(first)[:2] + second)
        else:
            year_end = int(second)
        return year_end, 1, "winter"
    m = _HALF_YEAR_SUMMER.match(s)
    if m:
        return int(m.group(1)), 3, "summer"
    return None


def _parse_date(value: Any, fmt: str | None) -> date | None:
    """Parse a date cell using the registry-supplied format hint."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    candidates: list[str] = []
    if fmt == "month_year_short":   # "Apr-15"
        candidates = ["%b-%y"]
    elif fmt == "us_dayfirst":      # "12/28/2015"
        candidates = ["%m/%d/%Y", "%m-%d-%Y"]
    elif fmt == "dayfirst":         # "01/04/2010"
        candidates = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"]
    elif fmt == "quarterly":         # "Q1 1998" / "1998 Q1"
        yq = _parse_quarter(s)
        if yq is None:
            return None
        y, q = yq
        return date(y, (q - 1) * 3 + 1, 1)
    elif fmt == "half_year":         # "2018/19 winter" / "2019 summer"
        h = _parse_half_year(s)
        if h is None:
            return None
        y, q, _ = h
        return date(y, (q - 1) * 3 + 1, 1)
    else:
        candidates = [
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%m/%d/%Y",
            "%b-%y",
            "%d/%m/%Y %H:%M:%S",
        ]
    for f in candidates:
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            continue
    return None


def _year_from_date(d: date | None, label: Any | None = None) -> int | None:
    if d is not None:
        return d.year
    return _parse_year_from_label(label)


def _read_xlsx(path: Path, sheet: str = "Sheet1", header_row: int = 0) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name=sheet, header=header_row, engine="openpyxl")


def _replace_null_strings(df: pd.DataFrame) -> pd.DataFrame:
    """Replace literal 'null' string entity placeholders with NaN."""
    return df.replace({"null": pd.NA, "NULL": pd.NA, "None": pd.NA})


# ---------------------------------------------------------------------------
# Parser strategies
# Each returns a list of dicts matching one of NETWORK / SHARE / MARKET schemas.
# ---------------------------------------------------------------------------


def parse_wide_period_metric(
    entry: Mapping,
    df: pd.DataFrame,
    riio_periods: Mapping,
    source_file: str,
) -> list[dict]:
    """entity in col 0, paired or grouped (period, metric) columns elsewhere."""
    entity_col = df.columns[entry.get("entity_column_index", 0)]
    pattern = re.compile(entry["column_pattern"])
    kind_map = entry.get("kind_metric_map", {})
    kind_substring = bool(entry.get("kind_metric_map_substring", False))
    period_from_fy = bool(entry.get("period_from_fy", False))
    sector = entry.get("network_sector")
    scheme = entry.get("scheme")
    unit = entry.get("unit")
    fixed_company = entry.get("fixed_company_name")
    multiplier = float(entry.get("value_multiplier", 1.0))

    rows: list[dict] = []
    for col in df.columns:
        if col == entity_col:
            continue
        m = pattern.search(str(col))
        if not m:
            continue
        groups = m.groupdict()
        kind_raw = (groups.get("kind") or "_default").strip()
        period_n = groups.get("period")
        period_n_int = int(period_n) if period_n and period_n.isdigit() else None
        fy_token = groups.get("fy")
        if period_from_fy:
            year = resolve_period_to_year(None, fy_token, scheme, riio_periods)
        else:
            year = resolve_period_to_year(period_n_int, fy_token, scheme, riio_periods)
        if kind_substring:
            metric = next(
                (canon for key, canon in kind_map.items() if key.lower() in kind_raw.lower()),
                None,
            )
        else:
            metric = kind_map.get(kind_raw) or kind_map.get("_default")
        if metric is None:
            continue
        for _, srcrow in df.iterrows():
            entity_val = fixed_company or srcrow[entity_col]
            if pd.isna(entity_val):
                continue
            value = _to_float(srcrow[col])
            if value is not None:
                value = value * multiplier
            rows.append({
                "year": year,
                "company_name": str(entity_val).strip() if entity_val is not None else None,
                "network_sector": sector,
                "metric_name": metric,
                "value": value,
                "unit": unit,
                "source_file": source_file,
            })
    return rows


def parse_year_label_long(
    entry: Mapping,
    df: pd.DataFrame,
    riio_periods: Mapping,
    source_file: str,
) -> list[dict]:
    """Col 0 holds a year label, every other col is a metric."""
    entity_col = df.columns[entry.get("entity_column_index", 0)]
    metric_map = entry.get("metric_map", {})
    substring = bool(entry.get("metric_map_substring", False))
    sector = entry.get("network_sector")
    unit = entry.get("unit")
    company = entry.get("fixed_company_name")
    rows: list[dict] = []
    for _, srcrow in df.iterrows():
        year = _parse_year_from_label(srcrow[entity_col])
        if year is None:
            continue
        for col in df.columns:
            if col == entity_col:
                continue
            metric = _resolve_metric_via_map(col, metric_map, substring)
            if metric is None:
                continue
            value = _to_float(srcrow[col])
            rows.append({
                "year": year,
                "company_name": company,
                "network_sector": sector,
                "metric_name": metric,
                "value": value,
                "unit": unit,
                "source_file": source_file,
            })
    return rows


def parse_columnar_snapshot(
    entry: Mapping,
    df: pd.DataFrame,
    riio_periods: Mapping,
    source_file: str,
) -> list[dict]:
    """No period dimension; snapshot_year applied to every row."""
    entity_col = df.columns[entry.get("entity_column_index", 0)]
    metric_map = entry.get("metric_map", {})
    substring = bool(entry.get("metric_map_substring", False))
    sector = entry.get("network_sector")
    unit = entry.get("unit")
    snapshot_year = entry.get("snapshot_year")
    raw_table = entry["raw_table"]
    is_share = raw_table in SHARE_TABLES

    rows: list[dict] = []
    for _, srcrow in df.iterrows():
        entity_val = srcrow[entity_col]
        if pd.isna(entity_val) or str(entity_val).strip().lower() == "null":
            continue
        for col in df.columns:
            if col == entity_col:
                continue
            metric = _resolve_metric_via_map(col, metric_map, substring)
            if metric is None:
                continue
            value = _to_float(srcrow[col])
            row = {
                "year": snapshot_year,
                "company_name": str(entity_val).strip(),
                "metric_name": metric,
                "value": value,
                "unit": unit,
                "source_file": source_file,
            }
            if not is_share:
                row["network_sector"] = sector
            rows.append(row)
    return rows


def parse_time_series_long(
    entry: Mapping,
    df: pd.DataFrame,
    riio_periods: Mapping,
    source_file: str,
) -> list[dict]:
    """Col 0 is a date; remaining cols are metrics or instruments-with-default-metric."""
    entity_col = df.columns[entry.get("entity_column_index", 0)]
    date_format = entry.get("date_format")
    metric_map = entry.get("metric_map", {})
    substring = bool(entry.get("metric_map_substring", False))
    fuel_columns_as_metric = bool(entry.get("fuel_columns_as_metric", False))
    commodity = entry.get("commodity")
    unit = entry.get("unit")
    default_metric = entry.get("default_metric_name") or f"{commodity or 'value'}_observation"

    rows: list[dict] = []
    for _, srcrow in df.iterrows():
        period_label = srcrow[entity_col]
        if pd.isna(period_label):
            continue
        period_label_s = str(period_label).strip()
        period_date = _parse_date(period_label, date_format)
        year = _year_from_date(period_date, period_label)
        for col in df.columns:
            if col == entity_col:
                continue
            value = _to_float(srcrow[col])
            if value is None:
                continue
            mapped = _resolve_metric_via_map(col, metric_map, substring) if metric_map else None
            if mapped is not None:
                metric = mapped
                instrument = None
            elif fuel_columns_as_metric or not metric_map:
                metric = default_metric
                instrument = _snake(str(col))
            else:
                continue
            rows.append({
                "period_date": period_date,
                "period_label": period_label_s,
                "year": year,
                "commodity": commodity,
                "instrument": instrument,
                "metric_name": metric,
                "value": value,
                "unit": unit,
                "source_file": source_file,
            })
    return rows


def parse_multi_year_unpivot(
    entry: Mapping,
    df: pd.DataFrame,
    riio_periods: Mapping,
    source_file: str,
) -> list[dict]:
    """Col 0 is an in-year period index (date or isoweek); each other col is a year."""
    entity_col = df.columns[entry.get("entity_column_index", 0)]
    period_kind = entry.get("period_kind", "isoweek")
    year_pattern = re.compile(entry["year_pattern"])
    pre_year_label = entry.get("pre_year_label")
    metric_name = entry.get("metric_name", "value")
    commodity = entry.get("commodity")
    unit = entry.get("unit")

    column_year_map: dict[str, tuple[int | None, str]] = {}
    for col in df.columns:
        if col == entity_col:
            continue
        m = year_pattern.search(str(col))
        if not m:
            continue
        groups = m.groupdict()
        year_str = groups.get("year")
        pre_year = groups.get("year_pre")
        if year_str:
            column_year_map[col] = (int(year_str), str(year_str))
        elif pre_year and pre_year_label:
            column_year_map[col] = (None, pre_year_label)
        else:
            column_year_map[col] = (None, str(col))

    rows: list[dict] = []
    for _, srcrow in df.iterrows():
        period_raw = srcrow[entity_col]
        if pd.isna(period_raw):
            continue
        if period_kind == "isoweek":
            period_label = f"isoweek_{int(_to_float(period_raw) or 0):02d}"
            period_date = None
        elif period_kind == "date_dayfirst":
            period_date = _parse_date(period_raw, "dayfirst")
            period_label = str(period_raw).strip() if period_date is None else period_date.isoformat()
        else:
            period_date = _parse_date(period_raw, period_kind)
            period_label = str(period_raw).strip() if period_date is None else period_date.isoformat()
        for col, (yr, label) in column_year_map.items():
            value = _to_float(srcrow[col])
            if value is None:
                continue
            rows.append({
                "period_date": period_date,
                "period_label": period_label,
                "year": yr,
                "commodity": commodity,
                "instrument": label,
                "metric_name": metric_name,
                "value": value,
                "unit": unit,
                "source_file": source_file,
            })
    return rows


def _resolve_period_token(token: Any, period_kind: str | None) -> dict:
    """Common period parsing for retail parsers.

    Returns a dict with as many of these populated as can be inferred:
        period_date, period_label, year, quarter
    """
    if token is None:
        return {}
    period_label = str(token).strip() if not isinstance(token, (date, datetime)) else None
    period_date: date | None = None
    year: int | None = None
    quarter: int | None = None

    if period_kind == "year":
        year = _parse_year_from_label(token)
        if period_label is None and year is not None:
            period_label = str(year)
    elif period_kind == "quarterly":
        period_date = _parse_date(token, "quarterly")
        yq = _parse_quarter(token)
        if yq is not None:
            year, quarter = yq
        if period_label is None and period_date is not None:
            period_label = period_date.isoformat()
    elif period_kind == "half_year":
        period_date = _parse_date(token, "half_year")
        h = _parse_half_year(token)
        if h is not None:
            year, quarter, _season = h
        if period_label is None and isinstance(token, (date, datetime)):
            period_label = period_date.isoformat() if period_date else None
    elif period_kind == "month_year_short":
        period_date = _parse_date(token, "month_year_short")
        if period_date is not None:
            year = period_date.year
            quarter = ((period_date.month - 1) // 3) + 1
        if period_label is None:
            period_label = str(token).strip()
    elif period_kind == "us_dayfirst":
        period_date = _parse_date(token, "us_dayfirst")
        if period_date is not None:
            year = period_date.year
            quarter = ((period_date.month - 1) // 3) + 1
    elif period_kind == "dayfirst":
        period_date = _parse_date(token, "dayfirst")
        if period_date is not None:
            year = period_date.year
            quarter = ((period_date.month - 1) // 3) + 1
    else:  # auto: try each format
        for fmt in ("quarterly", "month_year_short", "us_dayfirst", "dayfirst", "half_year"):
            period_date = _parse_date(token, fmt)
            if period_date:
                year = period_date.year
                quarter = ((period_date.month - 1) // 3) + 1
                break
        if year is None:
            year = _parse_year_from_label(token)
        if period_label is None and isinstance(token, (date, datetime)):
            period_label = (period_date.isoformat() if period_date else str(token))
    if isinstance(token, (date, datetime)) and period_date is None:
        period_date = token if isinstance(token, date) and not isinstance(token, datetime) else token.date()
        year = period_date.year
        quarter = ((period_date.month - 1) // 3) + 1
        period_label = period_date.isoformat()

    return {
        "period_date": period_date,
        "period_label": period_label,
        "year": year,
        "quarter": quarter,
    }


def parse_period_supplier_matrix(
    entry: Mapping,
    df: pd.DataFrame,
    riio_periods: Mapping,
    source_file: str,
) -> list[dict]:
    """Period in col 0; remaining columns are supplier names; cells are values.

    Used for: retail supplier profits (annual), market shares by supplier (quarterly),
    quarterly complaints / satisfaction by supplier, etc.
    """
    entity_col = df.columns[entry.get("entity_column_index", 0)]
    period_kind = entry.get("period_kind", "auto")
    metric_name = entry.get("metric_name", "value")
    segment = entry.get("segment")
    commodity = entry.get("commodity")
    unit = entry.get("unit")
    skip_cols = set(entry.get("skip_columns", []) or [])

    rows: list[dict] = []
    for _, srcrow in df.iterrows():
        period_token = srcrow[entity_col]
        if pd.isna(period_token):
            continue
        ptoken = _resolve_period_token(period_token, period_kind)
        for col in df.columns:
            if col == entity_col or col in skip_cols:
                continue
            value = _to_float(srcrow[col])
            if value is None:
                continue
            supplier_name = str(col).strip()
            # Strip lifecycle annotations like " - Start Q1 2020" / " - End Q4 2020".
            supplier_name = re.sub(r"\s*-\s*(Start|End)\s+Q\d+\s+\d{4}\s*$", "", supplier_name).strip()
            rows.append({
                "period_date": ptoken.get("period_date"),
                "period_label": ptoken.get("period_label") or str(period_token).strip(),
                "year": ptoken.get("year"),
                "quarter": ptoken.get("quarter"),
                "supplier_name": supplier_name,
                "segment": segment,
                "commodity": commodity,
                "metric_name": metric_name,
                "value": value,
                "unit": unit,
                "source_file": source_file,
            })
    return rows


def parse_period_dimension_matrix(
    entry: Mapping,
    df: pd.DataFrame,
    riio_periods: Mapping,
    source_file: str,
) -> list[dict]:
    """Period in col 0; remaining columns map to fixed enumerated dimensions.

    Used for: retail timeseries shaped by (commodity, payment_method, supplier_size,
    component, ...), e.g. switching time, debt arrears, disconnections, price cap
    components.
    """
    entity_col = df.columns[entry.get("entity_column_index", 0)]
    period_kind = entry.get("period_kind", "auto")
    metric_name = entry.get("metric_name", "value")
    unit = entry.get("unit")
    column_dim_map: Mapping[str, Mapping] = entry.get("column_dimension_map", {}) or {}
    column_dim_substring = bool(entry.get("column_dimension_substring", False))
    fixed_dims: Mapping = entry.get("dimensions", {}) or {}

    def resolve_column(col_label: str) -> dict | None:
        col_label_s = str(col_label).strip()
        if not column_dim_map:
            return {"component": col_label_s}
        if column_dim_substring:
            cl = col_label_s.lower()
            for key, dims in column_dim_map.items():
                if key.lower() in cl:
                    return dict(dims)
            return None
        return dict(column_dim_map.get(col_label_s, {})) if col_label_s in column_dim_map else None

    rows: list[dict] = []
    for _, srcrow in df.iterrows():
        period_token = srcrow[entity_col]
        if pd.isna(period_token):
            continue
        ptoken = _resolve_period_token(period_token, period_kind)
        for col in df.columns:
            if col == entity_col:
                continue
            dims = resolve_column(col)
            if dims is None:
                continue
            value = _to_float(srcrow[col])
            if value is None:
                continue
            row = {
                "period_date": ptoken.get("period_date"),
                "period_label": ptoken.get("period_label") or str(period_token).strip(),
                "year": ptoken.get("year"),
                "quarter": ptoken.get("quarter"),
                "commodity": dims.get("commodity") or fixed_dims.get("commodity"),
                "payment_method": dims.get("payment_method") or fixed_dims.get("payment_method"),
                "supplier_group": dims.get("supplier_group") or fixed_dims.get("supplier_group"),
                "supplier_size": dims.get("supplier_size") or fixed_dims.get("supplier_size"),
                "segment": dims.get("segment") or fixed_dims.get("segment"),
                "tariff_type": dims.get("tariff_type") or fixed_dims.get("tariff_type"),
                "component": dims.get("component") or fixed_dims.get("component"),
                "metric_name": dims.get("metric_name") or metric_name,
                "value": value,
                "unit": unit,
                "source_file": source_file,
            }
            rows.append(row)
    return rows


def parse_category_aspect_snapshot(
    entry: Mapping,
    df: pd.DataFrame,
    riio_periods: Mapping,
    source_file: str,
) -> list[dict]:
    """No period dimension; col 0 holds a category (supplier / aspect / component),
    remaining columns hold metrics. Emits raw_xlsx_retail_snapshot rows.

    Supports two key shapes:
      1. col 0 = aspect/category, columns = metrics (column_role omitted)
      2. col 0 = aspect, columns = supplier names (column_role = 'supplier_name')

    When ``column_role`` is set, the column label populates that field (e.g.
    supplier_name, payment_method, supplier_size) and `metric_name` defaults to
    ``metric_name``.
    """
    entity_col = df.columns[entry.get("entity_column_index", 0)]
    snapshot_year = entry.get("snapshot_year")
    entity_role = entry.get("entity_role", "category")  # category | supplier | aspect | component | supplier_size
    column_role = entry.get("column_role")              # None | supplier_name | payment_method | supplier_size | commodity | segment
    column_dim_map: Mapping[str, Mapping] = entry.get("column_dimension_map", {}) or {}
    column_dim_substring = bool(entry.get("column_dimension_substring", False))
    metric_name_default = entry.get("metric_name")
    fixed_dims: Mapping = entry.get("dimensions", {}) or {}
    skip_cols = set(entry.get("skip_columns", []) or [])
    unit = entry.get("unit")
    role_keys = {"supplier_name", "payment_method", "supplier_size", "commodity", "segment", "aspect", "component", "tariff_type"}

    def resolve_column(col_label: str) -> dict | None:
        col_label_s = str(col_label).strip()
        if column_role:
            val = col_label_s
            if column_role == "supplier_name":
                val = re.sub(r"\s*-\s*(Start|End)\s+Q\d+\s+\d{4}\s*$", "", val).strip()
            return {column_role: val, "metric_name": metric_name_default}
        if column_dim_map:
            if column_dim_substring:
                cl = col_label_s.lower()
                for key, dims in column_dim_map.items():
                    if key.lower() in cl:
                        return dict(dims)
                return None
            return dict(column_dim_map.get(col_label_s, {})) if col_label_s in column_dim_map else None
        if metric_name_default is None:
            return {"metric_name": _snake(col_label_s)}
        return {"aspect": col_label_s, "metric_name": metric_name_default}

    rows: list[dict] = []
    for _, srcrow in df.iterrows():
        entity_val = srcrow[entity_col]
        if pd.isna(entity_val) or str(entity_val).strip().lower() in {"null", "none"}:
            continue
        entity_s = str(entity_val).strip()
        for col in df.columns:
            if col == entity_col or col in skip_cols:
                continue
            dims = resolve_column(col)
            if dims is None:
                continue
            value = _to_float(srcrow[col])
            if value is None:
                continue
            metric = dims.get("metric_name") or metric_name_default or _snake(str(col))
            row = {
                "year": snapshot_year,
                "category": entity_s if entity_role == "category" else None,
                "supplier_name": entity_s if entity_role == "supplier" else dims.get("supplier_name") or fixed_dims.get("supplier_name"),
                "segment": dims.get("segment") or fixed_dims.get("segment"),
                "commodity": dims.get("commodity") or fixed_dims.get("commodity"),
                "payment_method": dims.get("payment_method") or fixed_dims.get("payment_method"),
                "supplier_size": dims.get("supplier_size") or (entity_s if entity_role == "supplier_size" else fixed_dims.get("supplier_size")),
                "aspect": entity_s if entity_role == "aspect" else dims.get("aspect"),
                "component": entity_s if entity_role == "component" else dims.get("component"),
                "tariff_type": dims.get("tariff_type") or fixed_dims.get("tariff_type"),
                "metric_name": metric,
                "value": value,
                "unit": unit,
                "source_file": source_file,
            }
            rows.append(row)
    return rows


PARSERS = {
    "wide_period_metric": parse_wide_period_metric,
    "year_label_long": parse_year_label_long,
    "columnar_snapshot": parse_columnar_snapshot,
    "time_series_long": parse_time_series_long,
    "multi_year_unpivot": parse_multi_year_unpivot,
    "period_supplier_matrix": parse_period_supplier_matrix,
    "period_dimension_matrix": parse_period_dimension_matrix,
    "category_aspect_snapshot": parse_category_aspect_snapshot,
}


# ---------------------------------------------------------------------------
# Upsert and orchestration
# ---------------------------------------------------------------------------


def _upsert_rows(client, table: str, rows: list[dict], logger: logging.Logger) -> int:
    """Idempotent upsert via INSERT ... ON CONFLICT ON CONSTRAINT ... DO UPDATE."""
    if not rows:
        return 0
    if table in NETWORK_TABLES:
        cols = NETWORK_COLUMNS
    elif table in SHARE_TABLES:
        cols = SHARE_COLUMNS
    elif table in MARKET_TABLES:
        cols = MARKET_COLUMNS
    elif table in RETAIL_SUPPLIER_TABLES:
        cols = RETAIL_SUPPLIER_COLUMNS
    elif table in RETAIL_TIMESERIES_TABLES:
        cols = RETAIL_TIMESERIES_COLUMNS
    elif table in RETAIL_SNAPSHOT_TABLES:
        cols = RETAIL_SNAPSHOT_COLUMNS
    else:
        raise ValueError(f"Unknown raw_xlsx table: {table}")

    constraint = TABLE_CONSTRAINT[table]
    update_cols = [c for c in cols if c not in {"source_file"}]
    update_clause = ", ".join([f"{c} = EXCLUDED.{c}" for c in update_cols])
    placeholders = ", ".join(["%s"] * len(cols))
    sql = (
        f"INSERT INTO {table} ({', '.join(cols)}) "
        f"VALUES ({placeholders}) "
        f"ON CONFLICT ON CONSTRAINT {constraint} DO UPDATE SET {update_clause}, loaded_at = now();"
    )
    inserted = 0
    with client._conn.cursor() as cur:
        for r in rows:
            params = [r.get(c) for c in cols]
            try:
                cur.execute(sql, params)
                inserted += 1
            except Exception:
                logger.exception("Upsert failed for %s row=%s", table, r)
                raise
    return inserted


def _log_run(client, source_id: str, table: str, count: int, status: str, error: str | None = None) -> None:
    client.execute(
        """
        INSERT INTO etl_run_log (run_ts, source_id, target_table, row_count, null_rate_json, status, error_message)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
        """,
        (
            datetime.now(timezone.utc),
            source_id,
            table,
            int(count),
            "{}",
            status,
            error,
        ),
    )


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_mapping_csv(client, table: str, csv_path: Path, logger: logging.Logger) -> int:
    """COPY a metadata CSV into a stg_*_alias table after truncating it."""
    if not csv_path.exists():
        logger.warning("metadata CSV missing: %s", csv_path)
        return 0
    client.execute(f"TRUNCATE TABLE {table};")
    with csv_path.open("r", encoding="utf-8") as f:
        with client._conn.cursor() as cur:
            cur.copy_expert(f"COPY {table} FROM STDIN WITH CSV HEADER", f)
    count = client.fetchall(f"SELECT count(*) FROM {table}")[0][0]
    logger.info("loaded %s from %s (%d rows)", table, csv_path, count)
    return count


def load_metadata_tables(settings: dict, client, logger: logging.Logger) -> None:
    """Idempotently (re)load the mapping CSVs into stg_*_alias tables."""
    client.execute_file("sql/raw/10_create_mapping_tables.sql")
    metadata_dir = Path(settings.get("sources", {}).get("company_mapping_file", "metadata/company_mapping.csv")).parent
    files = [
        ("stg_company_alias", metadata_dir / "company_mapping.csv"),
        ("stg_geography_alias", metadata_dir / "geography_mapping.csv"),
        ("stg_sic_alias", metadata_dir / "sic_mapping.csv"),
        ("stg_supplier_alias", metadata_dir / "supplier_mapping.csv"),
    ]
    for table, path in files:
        _load_mapping_csv(client, table, path, logger)


def load_all_xlsx(settings: dict, client, logger: logging.Logger) -> None:
    """Entry point invoked from pipeline.orchestrate."""
    client.execute_file("sql/raw/00_create_raw_tables.sql")
    client.execute_file("sql/raw/05_create_raw_xlsx_tables.sql")
    client.execute_file("sql/raw/06_create_raw_xlsx_retail_tables.sql")
    load_metadata_tables(settings, client, logger)

    registry = _load_yaml(Path("metadata/xlsx_registry.yaml"))
    riio_periods = _load_yaml(Path("metadata/riio_periods.yaml"))
    defaults = registry.get("defaults", {})
    default_data_dir = Path(defaults.get("data_dir", "data/ofgem_data_portal_xlsx"))
    sheet = defaults.get("sheet_name", "Sheet1")
    header_row = int(defaults.get("header_row", 0))
    fail_fast = bool(settings.get("pipeline", {}).get("fail_fast", False))

    files = registry.get("files", []) or []
    logger.info("xlsx loader: %d entries to process from registry", len(files))

    total_loaded = 0
    failures: list[str] = []
    for entry in files:
        source_file = entry["file"]
        raw_table = entry["raw_table"]
        parser_name = entry["parser"]
        data_dir = Path(entry["data_dir"]) if entry.get("data_dir") else default_data_dir
        full_path = data_dir / source_file
        if not full_path.exists():
            msg = f"file not found: {full_path}"
            logger.warning("%s -> %s", source_file, msg)
            _log_run(client, source_file, raw_table, 0, "skipped", msg)
            failures.append(source_file)
            continue
        parser = PARSERS.get(parser_name)
        if parser is None:
            msg = f"unknown parser '{parser_name}' for {source_file}"
            logger.error(msg)
            _log_run(client, source_file, raw_table, 0, "failed", msg)
            failures.append(source_file)
            if fail_fast:
                raise ValueError(msg)
            continue
        try:
            df = _read_xlsx(full_path, sheet=sheet, header_row=header_row)
            df = _replace_null_strings(df)
            rows = parser(entry, df, riio_periods, source_file)
            count = _upsert_rows(client, raw_table, rows, logger)
            _log_run(client, source_file, raw_table, count, "loaded")
            total_loaded += count
            logger.info("xlsx loaded %s -> %s (%d rows)", source_file, raw_table, count)
        except Exception as exc:
            err_text = f"{type(exc).__name__}: {exc}"
            tb = traceback.format_exc()
            logger.error("xlsx FAILED %s: %s\n%s", source_file, err_text, tb)
            try:
                client.rollback()
            except Exception:
                pass
            _log_run(client, source_file, raw_table, 0, "failed", err_text)
            client.commit()
            failures.append(source_file)
            if fail_fast:
                raise
    logger.info("xlsx loader done: %d rows upserted, %d failed/skipped", total_loaded, len(failures))
    if failures:
        logger.warning("xlsx files with issues: %s", failures)

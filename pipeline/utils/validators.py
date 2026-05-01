from __future__ import annotations

import re
from typing import Iterable, Mapping

import pandas as pd


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed = [
        c.strip().lower().replace(" ", "_").replace("-", "_").replace("/", "_")
        for c in df.columns
    ]
    df = df.copy()
    df.columns = renamed
    return df


def require_columns(df: pd.DataFrame, expected_columns: Iterable[str], table_name: str) -> None:
    missing = [col for col in expected_columns if col not in df.columns]
    if missing:
        raise ValueError(f"{table_name}: missing expected columns {missing}")


def check_non_negative(df: pd.DataFrame, columns: Iterable[str], table_name: str) -> None:
    for column in columns:
        if column in df.columns and (df[column].dropna() < 0).any():
            raise ValueError(f"{table_name}: negative values detected in {column}")


def null_rate(df: pd.DataFrame) -> pd.Series:
    return (df.isna().sum() / max(len(df), 1)).sort_values(ascending=False)


# -----------------------------------------------------------------------------
# RIIO period helpers used by load_xlsx.py
# -----------------------------------------------------------------------------

# Regulatory period token -> calendar end-year resolver.  When `period_n` is
# given (e.g. "Year 1"), the calendar year is derived from the scheme's
# start_fy_end_year. When an `fy_token` is given (e.g. "13/14", "2013-14",
# "2013 - 14") the lookup table or a regex resolves the end calendar year.

_FY_REGEX = re.compile(r"(?P<a>\d{2,4})\s*[-/]\s*(?P<b>\d{2,4})")


def resolve_period_to_year(
    period_n: int | None,
    fy_token: str | None,
    scheme: str | None,
    riio_periods: Mapping,
) -> int | None:
    """Translate a regulatory-year token into a calendar end-year.

    Args:
        period_n: integer N parsed from a "Year N"/"Y N" token, or None.
        fy_token: an FY-style token like "13/14" / "2013-14" / "2013 - 14".
        scheme: RIIO scheme key (T1, ED1, GD1) used when period_n is given.
        riio_periods: parsed metadata/riio_periods.yaml.

    Returns the four-digit calendar year that ends the regulatory year, or
    None if neither token is resolvable.
    """
    if period_n is not None:
        scheme_cfg = (riio_periods.get("schemes") or {}).get(scheme or "")
        if not scheme_cfg:
            return None
        start = int(scheme_cfg["start_fy_end_year"])
        return start + (period_n - 1)

    if fy_token:
        token = fy_token.strip()
        lookup = (riio_periods.get("fy_label_to_end_year") or {})
        if token in lookup:
            return int(lookup[token])
        m = _FY_REGEX.search(token)
        if m:
            a = m.group("a")
            b = m.group("b")
            if len(b) == 2:
                # Fold "13/14" -> 2014, "99/00" -> 2000
                century = 2000 if int(a) >= 50 or int(b) <= 50 else 1900
                return century + int(b)
            return int(b)
    return None


def unpivot_wide_riio(
    df: pd.DataFrame,
    entity_col_index: int,
    column_pattern: str,
    kind_metric_map: Mapping[str, str],
    scheme: str | None,
    riio_periods: Mapping,
    *,
    period_from_fy: bool = False,
    kind_metric_map_substring: bool = False,
) -> pd.DataFrame:
    """Unpivot a wide RIIO-shaped Excel table to long form.

    Returns a DataFrame with columns: entity, year, metric_name, value.
    Rows whose period or metric cannot be resolved are silently dropped after
    the caller's logger gets a warning via the loader.
    """
    pattern = re.compile(column_pattern)
    entity_col = df.columns[entity_col_index]
    out_rows = []
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
        if kind_metric_map_substring:
            metric = next(
                (canon for key, canon in kind_metric_map.items() if key.lower() in kind_raw.lower()),
                None,
            )
        else:
            metric = kind_metric_map.get(kind_raw) or kind_metric_map.get("_default")
        if metric is None:
            continue
        for _, row in df.iterrows():
            out_rows.append(
                {
                    "entity": row[entity_col],
                    "year": year,
                    "metric_name": metric,
                    "value": row[col],
                }
            )
    return pd.DataFrame(out_rows)

"""Dashboard SQL queries for Warm Home Discount (WHD).

Reads `mart_warm_home_discount` (built from `stg_whd_*`).  All helpers
degrade gracefully to an empty DataFrame when the underlying mart or its
source rows are missing, so the dashboard page can render a single info
banner instead of crashing on a fresh database.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from dashboard.db import get_engine, object_exists, read_sql


@st.cache_data(ttl=600)
def whd_national(y0: int, y1: int) -> pd.DataFrame:
    """National scheme-year rows: expenditure_pct and scheme_value_mgbp by nation."""
    engine = get_engine()
    if not object_exists(engine, "mart_warm_home_discount"):
        return pd.DataFrame()
    q = """
    SELECT scheme_year, calendar_year, nation,
           expenditure_pct, scheme_value_mgbp, source_file
    FROM mart_warm_home_discount
    WHERE grain = 'national'
      AND (calendar_year IS NULL OR calendar_year BETWEEN :y0 AND :y1)
    ORDER BY calendar_year, nation
    """
    try:
        return read_sql(engine, q, {"y0": y0, "y1": y1})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def whd_national_fallback() -> pd.DataFrame:
    """National WHD rows ignoring year filter — used when the filtered query is empty but the mart has data."""
    engine = get_engine()
    if not object_exists(engine, "mart_warm_home_discount"):
        return pd.DataFrame()
    q = """
    SELECT scheme_year, calendar_year, nation,
           expenditure_pct, scheme_value_mgbp, source_file
    FROM mart_warm_home_discount
    WHERE grain = 'national'
    ORDER BY calendar_year DESC NULLS LAST, scheme_year DESC, nation
    LIMIT 300
    """
    try:
        return read_sql(engine, q)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def whd_supplier(
    y0: int, y1: int, supplier_key: tuple[int, ...] | None = None
) -> pd.DataFrame:
    """Supplier-grain WHD rows: obligation amounts and redistribution by method."""
    engine = get_engine()
    if not object_exists(engine, "mart_warm_home_discount"):
        return pd.DataFrame()
    params: dict[str, Any] = {"y0": y0, "y1": y1}
    clause = ""
    if supplier_key:
        ph = ", ".join(f":s{i}" for i in range(len(supplier_key)))
        clause = f" AND supplier_id IN ({ph}) "
        params.update({f"s{i}": int(v) for i, v in enumerate(supplier_key)})
    q = f"""
    SELECT scheme_year, calendar_year, supplier_id, supplier_name,
           supplier_group, supplier_size, obligation_method,
           obligation_amount_mgbp, redistributed_mgbp, source_file
    FROM mart_warm_home_discount
    WHERE grain = 'supplier'
      AND (calendar_year IS NULL OR calendar_year BETWEEN :y0 AND :y1)
      {clause}
    ORDER BY calendar_year, supplier_name NULLS LAST, obligation_method NULLS LAST
    """
    try:
        return read_sql(engine, q, params)
    except Exception:
        return pd.DataFrame()

"""Cross-layer mart queries for dashboard pages."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from dashboard.db import get_engine, read_sql


@st.cache_data(ttl=600)
def cross_cost_to_consumer(y0: int, y1: int) -> pd.DataFrame:
    q = """
    SELECT *
    FROM mart_cross_layer_cost_to_consumer
    WHERE year BETWEEN :y0 AND :y1
    ORDER BY year
    """
    try:
        return read_sql(get_engine(), q, {"y0": y0, "y1": y1})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def cross_volatility_complaints(y0: int, y1: int) -> pd.DataFrame:
    q = """
    SELECT *
    FROM mart_cross_layer_volatility_complaints
    WHERE year BETWEEN :y0 AND :y1
    ORDER BY year
    """
    try:
        return read_sql(get_engine(), q, {"y0": y0, "y1": y1})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def cross_supplier_quality(y0: int, y1: int, supplier_key: tuple[int, ...] | None = None) -> pd.DataFrame:
    params: dict[str, Any] = {"y0": y0, "y1": y1}
    clause = ""
    if supplier_key:
        ph = ", ".join(f":s{i}" for i in range(len(supplier_key)))
        clause = f" AND supplier_id IN ({ph}) "
        params.update({f"s{i}": int(v) for i, v in enumerate(supplier_key)})
    q = f"""
    SELECT *
    FROM mart_cross_layer_supplier_quality
    WHERE year BETWEEN :y0 AND :y1 {clause}
    ORDER BY year, supplier_name
    """
    try:
        return read_sql(get_engine(), q, params)
    except Exception:
        return pd.DataFrame()

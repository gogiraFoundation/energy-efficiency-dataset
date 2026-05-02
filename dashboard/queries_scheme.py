"""Dashboard SQL for policy scheme administration metrics (ECO, BUS, RHI, queues, etc.).

Reads ``mart_scheme_metric`` (pass-through of ``core_fact_scheme_metric``).  Empty
DataFrame when the mart is missing or has no rows for the filter.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from dashboard.db import get_engine, object_exists, read_sql


@st.cache_data(ttl=600)
def scheme_metric_exists() -> bool:
    return object_exists(get_engine(), "mart_scheme_metric")


@st.cache_data(ttl=600)
def scheme_metric_distinct_schemes(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    if not object_exists(engine, "mart_scheme_metric"):
        return pd.DataFrame()
    q = """
    SELECT scheme_key, COUNT(*)::bigint AS n
    FROM mart_scheme_metric
    WHERE (calendar_year IS NULL OR calendar_year BETWEEN :y0 AND :y1)
    GROUP BY scheme_key
    ORDER BY scheme_key
    """
    try:
        return read_sql(engine, q, {"y0": y0, "y1": y1})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def scheme_metric_distinct_metrics(
    y0: int, y1: int, scheme_key: str | None
) -> pd.DataFrame:
    engine = get_engine()
    if not object_exists(engine, "mart_scheme_metric"):
        return pd.DataFrame()
    params: dict[str, Any] = {"y0": y0, "y1": y1}
    sk_clause = ""
    if scheme_key:
        sk_clause = " AND scheme_key = :scheme_key "
        params["scheme_key"] = scheme_key
    q = f"""
    SELECT metric_name, COUNT(*)::bigint AS n
    FROM mart_scheme_metric
    WHERE (calendar_year IS NULL OR calendar_year BETWEEN :y0 AND :y1)
    {sk_clause}
    GROUP BY metric_name
    ORDER BY metric_name
    """
    try:
        return read_sql(engine, q, params)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def scheme_metric_long(
    y0: int,
    y1: int,
    scheme_key: str | None = None,
    metric_name: str | None = None,
    limit: int = 5000,
) -> pd.DataFrame:
    """Long-format rows for tables and charts."""
    engine = get_engine()
    if not object_exists(engine, "mart_scheme_metric"):
        return pd.DataFrame()
    params: dict[str, Any] = {"y0": y0, "y1": y1, "limit": limit}
    clauses: list[str] = [
        "(calendar_year IS NULL OR calendar_year BETWEEN :y0 AND :y1)",
    ]
    if scheme_key:
        clauses.append("scheme_key = :scheme_key")
        params["scheme_key"] = scheme_key
    if metric_name:
        clauses.append("metric_name = :metric_name")
        params["metric_name"] = metric_name
    where_sql = " AND ".join(clauses)
    q = f"""
    SELECT
        scheme_metric_id,
        period_date,
        period_label,
        calendar_year,
        calendar_month,
        quarter,
        scheme_key,
        entity,
        metric_name,
        value,
        unit,
        source_file
    FROM mart_scheme_metric
    WHERE {where_sql}
    ORDER BY calendar_year NULLS LAST, scheme_key, metric_name, period_date NULLS LAST
    LIMIT :limit
    """
    try:
        return read_sql(engine, q, params)
    except Exception:
        return pd.DataFrame()

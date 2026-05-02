"""Dashboard reads for long-format DUKES staging (Chapters 4 & 5, Chapter 1 supplementary)."""

from __future__ import annotations

from typing import Literal

import pandas as pd
import streamlit as st

from dashboard.db import get_engine, object_exists, read_sql

StagingKey = Literal["ch4", "ch5", "ch1_sup"]

_STAGING_TABLE: dict[StagingKey, str] = {
    "ch4": "stg_dukes_chapter4",
    "ch5": "stg_dukes_chapter5",
    "ch1_sup": "stg_dukes_chapter1_sup",
}


def _physical_table(key: StagingKey) -> str:
    return _STAGING_TABLE[key]


@st.cache_data(ttl=600)
def dukes_staging_distinct_tables(staging_key: StagingKey) -> pd.DataFrame:
    """Single column ``dukes_table`` sorted."""
    engine = get_engine()
    rel = _physical_table(staging_key)
    if not object_exists(engine, rel):
        return pd.DataFrame(columns=["dukes_table"])
    q = f"""
    SELECT DISTINCT dukes_table::text AS dukes_table
    FROM {rel}
    ORDER BY 1
    """
    try:
        return read_sql(engine, q)
    except Exception:
        return pd.DataFrame(columns=["dukes_table"])


@st.cache_data(ttl=600)
def dukes_staging_distinct_metrics(staging_key: StagingKey, dukes_table: str) -> pd.DataFrame:
    engine = get_engine()
    rel = _physical_table(staging_key)
    if not object_exists(engine, rel):
        return pd.DataFrame(columns=["metric_name"])
    q = f"""
    SELECT DISTINCT metric_name::text AS metric_name
    FROM {rel}
    WHERE dukes_table = :tid
    ORDER BY 1
    """
    try:
        return read_sql(engine, q, params={"tid": dukes_table})
    except Exception:
        return pd.DataFrame(columns=["metric_name"])


@st.cache_data(ttl=600)
def dukes_staging_long(
    y0: int,
    y1: int,
    staging_key: StagingKey,
    dukes_table: str,
    metric_name: str | None = None,
) -> pd.DataFrame:
    """Long rows for one ``dukes_table``; includes NULL ``period_year`` (e.g. cumulative columns)."""
    engine = get_engine()
    rel = _physical_table(staging_key)
    if not object_exists(engine, rel):
        return pd.DataFrame()
    params: dict[str, object] = {"tid": dukes_table, "y0": y0, "y1": y1}
    metric_clause = ""
    if metric_name:
        metric_clause = " AND metric_name = :m"
        params["m"] = metric_name
    q = f"""
    SELECT
        dukes_table,
        period_year,
        period_label,
        row_label,
        column_label,
        metric_name,
        value,
        unit,
        source_file,
        value_text
    FROM {rel}
    WHERE dukes_table = :tid
      AND (period_year IS NULL OR (period_year >= :y0 AND period_year <= :y1))
    {metric_clause}
    ORDER BY period_year NULLS LAST, row_label, column_label, metric_name
    """
    try:
        return read_sql(engine, q, params=params)
    except Exception:
        return pd.DataFrame()


def staging_table_exists(staging_key: StagingKey) -> bool:
    engine = get_engine()
    return object_exists(engine, _physical_table(staging_key))


def staging_relation_name(staging_key: StagingKey) -> str:
    """Physical relation name for UI captions."""
    return _physical_table(staging_key)

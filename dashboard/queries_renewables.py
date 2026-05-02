"""Dashboard SQL queries for renewables: MCS-style deployment, RO portal, and DUKES Ch.6.

Reads `mart_renewables_deployment` (from `stg_renewables_*`) and, for official
national statistics, `mart_dukes_official_renewables` (from `stg_dukes_chapter6`).

MCS-style grain values: `annual_gb`, `quarterly_gb`, `regional`, `by_installation_type`.

All helpers degrade gracefully to an empty DataFrame when the underlying objects
are missing.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from dashboard.db import get_engine, object_exists, read_sql


@st.cache_data(ttl=600)
def renewables_annual(y0: int, y1: int) -> pd.DataFrame:
    """Annual GB cumulative capacity / installations by technology."""
    engine = get_engine()
    if not object_exists(engine, "mart_renewables_deployment"):
        return pd.DataFrame()
    q = """
    SELECT year, technology, capacity_kw, installations,
           cumulative_capacity_kw, cumulative_installations
    FROM mart_renewables_deployment
    WHERE grain = 'annual_gb'
      AND year BETWEEN :y0 AND :y1
    ORDER BY year, technology
    """
    try:
        return read_sql(engine, q, {"y0": y0, "y1": y1})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def renewables_quarterly(y0: int, y1: int) -> pd.DataFrame:
    """Quarterly GB net additions by technology."""
    engine = get_engine()
    if not object_exists(engine, "mart_renewables_deployment"):
        return pd.DataFrame()
    q = """
    SELECT year, quarter, period_date, technology,
           capacity_kw_quarter, installations_quarter
    FROM mart_renewables_deployment
    WHERE grain = 'quarterly_gb'
      AND year BETWEEN :y0 AND :y1
    ORDER BY period_date NULLS LAST, year, quarter, technology
    """
    try:
        return read_sql(engine, q, {"y0": y0, "y1": y1})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def renew_obligation_by_technology() -> pd.DataFrame:
    """ROCs issued (millions) and accredited capacity (MW) by obligation period × technology."""
    engine = get_engine()
    if not object_exists(engine, "mart_renewables_obligation"):
        return pd.DataFrame()
    q = """
    SELECT obligation_period, technology,
           rocs_issued_millions, accredited_capacity_mw,
           rocs_source_file, capacity_source_file
    FROM mart_renewables_obligation
    ORDER BY obligation_period, technology
    """
    try:
        return read_sql(engine, q, {})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def renewables_regional(y0: int, y1: int) -> pd.DataFrame:
    """Regional capacity / installations / share by technology."""
    engine = get_engine()
    if not object_exists(engine, "mart_renewables_deployment"):
        return pd.DataFrame()
    q = """
    SELECT year, region, technology, share_pct, capacity_kw, installations
    FROM mart_renewables_deployment
    WHERE grain = 'regional'
      AND year BETWEEN :y0 AND :y1
    ORDER BY year, region, technology
    """
    try:
        return read_sql(engine, q, {"y0": y0, "y1": y1})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def dukes_official_chapter6_generation_gwh(y0: int, y1: int) -> pd.DataFrame:
    """DUKES 6.2 — electricity generation (GWh) by technology row."""
    engine = get_engine()
    if not object_exists(engine, "mart_dukes_official_renewables"):
        return pd.DataFrame()
    q = """
    SELECT period_year AS year, trim(both from row_label) AS technology, value
    FROM mart_dukes_official_renewables
    WHERE grain = 'capacity_generation_shares'
      AND metric_name = 'generation_gwh'
      AND period_year BETWEEN :y0 AND :y1
    ORDER BY year, technology
    """
    try:
        return read_sql(engine, q, {"y0": y0, "y1": y1})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def dukes_official_chapter6_load_factors(y0: int, y1: int) -> pd.DataFrame:
    """DUKES 6.3 — load factors (%), average-capacity basis."""
    engine = get_engine()
    if not object_exists(engine, "mart_dukes_official_renewables"):
        return pd.DataFrame()
    q = """
    SELECT period_year AS year, trim(both from row_label) AS technology, value
    FROM mart_dukes_official_renewables
    WHERE grain = 'load_factors'
      AND metric_name = 'load_factor_avg_capacity_pct'
      AND period_year BETWEEN :y0 AND :y1
    ORDER BY year, technology
    """
    try:
        return read_sql(engine, q, {"y0": y0, "y1": y1})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def dukes_official_chapter6_electricity_renewable_share(y0: int, y1: int) -> pd.DataFrame:
    """DUKES 6.5a — renewable share of gross final electricity (proportion 0–1)."""
    engine = get_engine()
    if not object_exists(engine, "mart_dukes_official_renewables"):
        return pd.DataFrame()
    q = """
    SELECT DISTINCT ON (period_year)
      period_year AS year,
      value AS renewable_share_of_gfc_electricity
    FROM mart_dukes_official_renewables
    WHERE grain = 'gross_final_consumption'
      AND metric_name = 'gfc_electricity_renewable_share_pct'
      AND period_year BETWEEN :y0 AND :y1
      AND value IS NOT NULL
      AND value BETWEEN 0 AND 1
      AND trim(both from row_label) ILIKE '%Renewable share of gross final electricity consumption%'
    ORDER BY period_year, trim(both from row_label)
    """
    try:
        return read_sql(engine, q, {"y0": y0, "y1": y1})
    except Exception:
        return pd.DataFrame()

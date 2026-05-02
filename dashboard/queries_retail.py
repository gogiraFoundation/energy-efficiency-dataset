"""Retail-layer dashboard SQL queries (marts + dimensions)."""

from __future__ import annotations

from typing import Any, Literal

import pandas as pd
import streamlit as st

from dashboard.db import get_engine, object_exists, read_sql


@st.cache_data(ttl=600)
def fetch_suppliers() -> pd.DataFrame:
    q = """
    SELECT supplier_id, supplier_name, supplier_group, supplier_size
    FROM core_dim_supplier
    ORDER BY supplier_name
    """
    try:
        return read_sql(get_engine(), q)
    except Exception:
        return pd.DataFrame(columns=['supplier_id','supplier_name','supplier_group','supplier_size'])


def coerce_retail_supplier_health_result(
    result: object,
) -> tuple[pd.DataFrame, str]:
    """Normalize ``retail_supplier_health`` output to ``(DataFrame, tag)``.

    Streamlit cache or a mistaken ``df = retail_supplier_health(...)`` assignment can leave a
    tuple where a DataFrame is expected; unwrap single-element wrappers from cached tuples.
    """
    if isinstance(result, pd.DataFrame):
        return result, "mart"
    while isinstance(result, tuple) and len(result) == 1:
        result = result[0]
    if isinstance(result, tuple) and len(result) == 2:
        df, tag = result
        if isinstance(df, pd.DataFrame) and isinstance(tag, str):
            return df, tag
    return pd.DataFrame(), "empty"


@st.cache_data(ttl=600)
def retail_supplier_health(
    y0: int,
    y1: int,
    supplier_key: tuple[int, ...] | None = None,
    *,
    _cache_version: int = 3,
) -> tuple[pd.DataFrame, Literal["mart", "fallback", "empty"]]:
    params: dict[str, Any] = {'y0': y0, 'y1': y1}
    clause = ''
    if supplier_key:
        ph = ', '.join(f':s{i}' for i in range(len(supplier_key)))
        clause = f' AND supplier_id IN ({ph}) '
        params.update({f's{i}': int(v) for i, v in enumerate(supplier_key)})
    q = f"""
    SELECT *
    FROM mart_retail_supplier_health
    WHERE year BETWEEN :y0 AND :y1 {clause}
    ORDER BY year, supplier_name
    """
    try:
        mart_df = read_sql(get_engine(), q, params)
        if not mart_df.empty:
            return mart_df, "mart"
    except Exception:
        pass

    # Fallback path: build supplier-health rows directly from core retail facts.
    # This keeps the dashboard usable when marts are not refreshed yet.
    fallback_q = f"""
    WITH supplier_year AS (
        SELECT
            d.year,
            s.supplier_id,
            s.supplier_name,
            s.supplier_group,
            s.supplier_size,
            MAX(s.exited_quarter) AS exited_quarter,
            SUM(f.value) FILTER (
                WHERE f.metric_name = 'profit_million_gbp'
                  AND COALESCE(f.segment, 'domestic') = 'domestic'
            ) AS profit_million_gbp,
            AVG(f.value) FILTER (WHERE f.metric_name = 'pretax_domestic_margin_pct') AS pretax_margin_pct
        FROM core_fact_supplier_financial f
        JOIN core_dim_date d ON d.date_id = f.date_id
        LEFT JOIN core_dim_supplier s ON s.supplier_id = f.supplier_id
        WHERE d.year BETWEEN :y0 AND :y1 {clause}
        GROUP BY d.year, s.supplier_id, s.supplier_name, s.supplier_group, s.supplier_size
    ),
    structure AS (
        SELECT
            d.year,
            SUM(ms.value) FILTER (WHERE ms.metric_name = 'supplier_entries')   AS supplier_entries,
            SUM(ms.value) FILTER (WHERE ms.metric_name = 'supplier_exits')     AS supplier_exits,
            AVG(ms.value) FILTER (WHERE ms.metric_name = 'active_suppliers')   AS active_suppliers_avg,
            AVG(ms.value) FILTER (WHERE ms.metric_name = 'continuing_active') AS continuing_active_avg
        FROM core_fact_market_structure ms
        JOIN core_dim_date d ON d.date_id = ms.date_id
        WHERE d.year BETWEEN :y0 AND :y1
        GROUP BY d.year
    ),
    hhi AS (
        SELECT
            year,
            AVG(hhi_by_commodity) AS hhi
        FROM (
            SELECT
                d.year,
                msr.commodity,
                SUM(POWER(msr.share_pct / 100.0, 2)) AS hhi_by_commodity
            FROM core_fact_market_share_retail msr
            JOIN core_dim_date d ON d.date_id = msr.date_id
            WHERE d.year BETWEEN :y0 AND :y1
            GROUP BY d.year, msr.commodity
        ) c
        GROUP BY year
    )
    SELECT
        sy.year,
        sy.supplier_id,
        sy.supplier_name,
        sy.supplier_group,
        sy.supplier_size,
        'domestic'::text AS segment,
        'all'::text AS commodity,
        sy.exited_quarter,
        sy.profit_million_gbp,
        sy.pretax_margin_pct,
        st.supplier_entries,
        st.supplier_exits,
        st.active_suppliers_avg,
        st.continuing_active_avg,
        h.hhi
    FROM supplier_year sy
    LEFT JOIN structure st ON st.year = sy.year
    LEFT JOIN hhi h ON h.year = sy.year
    ORDER BY sy.year, sy.supplier_name
    """
    try:
        fb = read_sql(get_engine(), fallback_q, params)
        if not fb.empty:
            return fb, "fallback"
    except Exception:
        pass
    return pd.DataFrame(), "empty"


@st.cache_data(ttl=120)
def retail_supplier_health_status() -> pd.DataFrame:
    """Report whether required retail tables/views exist for supplier health page."""
    engine = get_engine()
    objs = [
        "mart_retail_supplier_health",
        "core_fact_supplier_financial",
        "core_fact_market_structure",
        "core_fact_market_share_retail",
        "raw_xlsx_supplier_metric",
        "raw_xlsx_retail_timeseries",
    ]
    rows: list[dict[str, Any]] = []
    for name in objs:
        exists = False
        n_rows = None
        try:
            exists = object_exists(engine, name)
            if exists:
                n_rows = int(read_sql(engine, f"SELECT COUNT(*) AS n FROM {name}").iloc[0]["n"])
        except Exception:
            exists = False
            n_rows = None
        rows.append({"object_name": name, "exists": exists, "rows": n_rows})
    return pd.DataFrame(rows)


@st.cache_data(ttl=600)
def retail_consumer_vulnerability(
    y0: int,
    y1: int,
    commodity: str,
    payment_method: str | None = None,
    *,
    _cache_version: int = 2,
) -> pd.DataFrame:
    params: dict[str, Any] = {"y0": y0, "y1": y1}
    clause = "" if commodity == "both" else " AND commodity = :commodity "
    if commodity != "both":
        params["commodity"] = commodity
    pm = payment_method or "all"
    pm_clause = ""
    if pm != "all":
        pm_clause = " AND payment_method = :payment_method "
        params["payment_method"] = pm
    q = f"""
    SELECT *
    FROM mart_retail_consumer_vulnerability
    WHERE year BETWEEN :y0 AND :y1 {clause}{pm_clause}
    ORDER BY year, quarter, commodity, payment_method
    """
    try:
        return read_sql(get_engine(), q, params)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def retail_hhi_normalized_by_year(
    y0: int,
    y1: int,
    commodity: str,
) -> pd.DataFrame:
    """Retail HHI on 0–1 scale from ``core_fact_market_share_retail`` (mean across fuels if ``both``)."""
    params: dict[str, Any] = {"y0": y0, "y1": y1}
    comm_clause = ""
    if commodity != "both":
        comm_clause = " AND lower(msr.commodity) = lower(:commodity) "
        params["commodity"] = commodity
    q = f"""
    WITH by_yc AS (
        SELECT
            d.year,
            msr.commodity,
            SUM(POWER(msr.share_pct / 100.0, 2)) AS hhi_c
        FROM core_fact_market_share_retail msr
        JOIN core_dim_date d ON d.date_id = msr.date_id
        WHERE d.year BETWEEN :y0 AND :y1
        {comm_clause}
        GROUP BY d.year, msr.commodity
    )
    SELECT year, AVG(hhi_c) AS hhi
    FROM by_yc
    GROUP BY year
    ORDER BY year
    """
    try:
        return read_sql(get_engine(), q, params)
    except Exception:
        return pd.DataFrame()


def retail_hhi_normalized_latest(y0: int, y1: int, commodity: str) -> float | None:
    df = retail_hhi_normalized_by_year(y0, y1, commodity)
    if df.empty or "hhi" not in df.columns:
        return None
    last = pd.to_numeric(df["hhi"], errors="coerce").dropna()
    if last.empty:
        return None
    return float(last.iloc[-1])


@st.cache_data(ttl=600)
def retail_customer_accounts(
    y0: int,
    y1: int,
    commodity: str,
    supplier_key: tuple[int, ...] | None = None,
) -> pd.DataFrame:
    """Annual snapshot: domestic customer accounts by supplier × tariff type."""
    params: dict[str, Any] = {"y0": y0, "y1": y1}
    clause = ""
    if commodity != "both":
        clause += " AND lower(c.commodity) = lower(:commodity) "
        params["commodity"] = commodity
    if supplier_key:
        ph = ", ".join(f":a{i}" for i in range(len(supplier_key)))
        clause += f" AND c.supplier_id IN ({ph}) "
        params.update({f"a{i}": int(v) for i, v in enumerate(supplier_key)})
    q = f"""
    SELECT
        d.year,
        s.supplier_name,
        c.commodity,
        c.segment,
        c.tariff_type,
        c.value,
        c.unit
    FROM core_fact_customer_accounts_retail c
    JOIN core_dim_date d ON d.date_id = c.date_id
    LEFT JOIN core_dim_supplier s ON s.supplier_id = c.supplier_id
    WHERE d.year BETWEEN :y0 AND :y1
      AND d.quarter IS NULL
    {clause}
    ORDER BY d.year, s.supplier_name NULLS LAST, c.tariff_type
    """
    try:
        return read_sql(get_engine(), q, params)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def retail_heating_systems(y0: int, y1: int) -> pd.DataFrame:
    """RHI / heat-pump style approval counts from ``core_fact_heating_systems``."""
    q = """
    SELECT
        d.year,
        d.quarter,
        h.component,
        h.value,
        h.unit
    FROM core_fact_heating_systems h
    JOIN core_dim_date d ON d.date_id = h.date_id
    WHERE d.year BETWEEN :y0 AND :y1
    ORDER BY d.year, d.quarter NULLS LAST, h.component
    """
    try:
        return read_sql(get_engine(), q, {"y0": y0, "y1": y1})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def retail_disconnections_by_supplier(
    y0: int,
    y1: int,
    commodity: str,
    supplier_key: tuple[int, ...] | None = None,
    *,
    top_n: int = 15,
) -> pd.DataFrame:
    """Per-supplier disconnections for debt (annual snapshot grain in core facts).

    When ``supplier_key`` is empty, restricts to the top ``top_n`` suppliers by total
    disconnections over ``[y0, y1]`` for readability.
    """
    params: dict[str, Any] = {"y0": y0, "y1": y1, "top_n": top_n}
    commodity_clause = ""
    if commodity != "both":
        commodity_clause = " AND cdx.commodity = :commodity "
        params["commodity"] = commodity

    if supplier_key:
        ph = ", ".join(f":s{i}" for i in range(len(supplier_key)))
        supplier_filter = f" AND s.supplier_id IN ({ph}) "
        params.update({f"s{i}": int(v) for i, v in enumerate(supplier_key)})
        q = f"""
        SELECT
            d.year,
            s.supplier_id,
            s.supplier_name,
            SUM(cdx.value) AS disconnections_for_debt
        FROM core_fact_consumer_disconnections cdx
        JOIN core_dim_date d ON d.date_id = cdx.date_id
        JOIN core_dim_supplier s ON s.supplier_id = cdx.supplier_id
        WHERE cdx.metric_name = 'disconnections_for_debt'
          AND cdx.supplier_id IS NOT NULL
          AND d.year BETWEEN :y0 AND :y1
          {commodity_clause}
          {supplier_filter}
        GROUP BY d.year, s.supplier_id, s.supplier_name
        ORDER BY d.year, s.supplier_name
        """
    else:
        q = f"""
        WITH per_year AS (
            SELECT
                d.year,
                s.supplier_id,
                s.supplier_name,
                SUM(cdx.value) AS disconnections_for_debt
            FROM core_fact_consumer_disconnections cdx
            JOIN core_dim_date d ON d.date_id = cdx.date_id
            JOIN core_dim_supplier s ON s.supplier_id = cdx.supplier_id
            WHERE cdx.metric_name = 'disconnections_for_debt'
              AND cdx.supplier_id IS NOT NULL
              AND d.year BETWEEN :y0 AND :y1
              {commodity_clause}
            GROUP BY d.year, s.supplier_id, s.supplier_name
        ),
        supplier_totals AS (
            SELECT supplier_id, SUM(disconnections_for_debt) AS tot
            FROM per_year
            GROUP BY supplier_id
        ),
        top_suppliers AS (
            SELECT supplier_id
            FROM supplier_totals
            ORDER BY tot DESC NULLS LAST
            LIMIT :top_n
        )
        SELECT py.year, py.supplier_id, py.supplier_name, py.disconnections_for_debt
        FROM per_year py
        WHERE py.supplier_id IN (SELECT supplier_id FROM top_suppliers)
        ORDER BY py.year, py.supplier_name
        """
    try:
        return read_sql(get_engine(), q, params)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def retail_competition(y0: int, y1: int, commodity: str) -> pd.DataFrame:
    params: dict[str, Any] = {'y0': y0, 'y1': y1}
    clause = '' if commodity == 'both' else ' AND commodity = :commodity '
    if commodity != 'both':
        params['commodity'] = commodity
    q = f"""
    SELECT *
    FROM mart_retail_competition
    WHERE year BETWEEN :y0 AND :y1 {clause}
    ORDER BY year, quarter, commodity
    """
    try:
        return read_sql(get_engine(), q, params)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def retail_affordability(y0: int, y1: int, payment_method: str | None = None) -> pd.DataFrame:
    params: dict[str, Any] = {'y0': y0, 'y1': y1}
    clause = ''
    if payment_method and payment_method != 'all':
        clause = ' AND (payment_method = :payment_method OR payment_method IS NULL) '
        params['payment_method'] = payment_method
    q = f"""
    SELECT *
    FROM mart_retail_affordability
    WHERE year BETWEEN :y0 AND :y1 {clause}
    ORDER BY layer, year, quarter
    """
    try:
        return read_sql(get_engine(), q, params)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def retail_complaints(y0: int, y1: int, supplier_key: tuple[int, ...] | None = None) -> pd.DataFrame:
    params: dict[str, Any] = {'y0': y0, 'y1': y1}
    clause = ''
    if supplier_key:
        ph = ', '.join(f':s{i}' for i in range(len(supplier_key)))
        clause = f' AND supplier_id IN ({ph}) '
        params.update({f's{i}': int(v) for i, v in enumerate(supplier_key)})
    q = f"""
    SELECT *
    FROM mart_retail_complaints
    WHERE year BETWEEN :y0 AND :y1 {clause}
    ORDER BY year, quarter, supplier_name NULLS LAST
    """
    try:
        return read_sql(get_engine(), q, params)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def retail_incidents(y0: int, y1: int, supplier_key: tuple[int, ...] | None = None) -> pd.DataFrame:
    """Major and minor incidents from mart_retail_complaints.

    Returns one row per (supplier, metric_name) with the historical and current
    snapshot counts pivoted into columns. Rows where neither metric is populated
    are dropped.
    """
    params: dict[str, Any] = {'y0': y0, 'y1': y1}
    clause = ''
    if supplier_key:
        ph = ', '.join(f':s{i}' for i in range(len(supplier_key)))
        clause = f' AND supplier_id IN ({ph}) '
        params.update({f's{i}': int(v) for i, v in enumerate(supplier_key)})
    q = f"""
    SELECT year, supplier_id, supplier_name, supplier_group, supplier_size,
           metric_name, value, unit, source_file
    FROM mart_retail_complaints
    WHERE metric_name IN (
        'minor_incidents_historical', 'minor_incidents_current',
        'major_incidents_historical', 'major_incidents_current'
    )
      AND year BETWEEN :y0 AND :y1 {clause}
    ORDER BY year, supplier_name NULLS LAST
    """
    try:
        df = read_sql(get_engine(), q, params)
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    pivot = (
        df.pivot_table(
            index=['year', 'supplier_id', 'supplier_name', 'supplier_group', 'supplier_size'],
            columns='metric_name',
            values='value',
            aggfunc='max',
        )
        .reset_index()
    )
    for col in (
        'minor_incidents_historical', 'minor_incidents_current',
        'major_incidents_historical', 'major_incidents_current',
    ):
        if col not in pivot.columns:
            pivot[col] = pd.NA
    return pivot


@st.cache_data(ttl=600)
def retail_satisfaction(y0: int, y1: int, supplier_key: tuple[int, ...] | None = None) -> pd.DataFrame:
    params: dict[str, Any] = {'y0': y0, 'y1': y1}
    clause = ''
    if supplier_key:
        ph = ', '.join(f':s{i}' for i in range(len(supplier_key)))
        clause = f' AND supplier_id IN ({ph}) '
        params.update({f's{i}': int(v) for i, v in enumerate(supplier_key)})
    q = f"""
    SELECT *
    FROM mart_retail_satisfaction
    WHERE year BETWEEN :y0 AND :y1 {clause}
    ORDER BY year, quarter, supplier_name NULLS LAST
    """
    try:
        return read_sql(get_engine(), q, params)
    except Exception:
        return pd.DataFrame()

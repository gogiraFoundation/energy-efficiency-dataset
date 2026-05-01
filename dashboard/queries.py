"""Parameterized SQL access with Streamlit caching."""

from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

import streamlit as st

from dashboard.config import database_url
from dashboard.utils import CommodityFilter, zscore


def _read_sql(engine: Engine, sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or None)


# ---------------------------------------------------------------------------
# Engine & schema probes
# ---------------------------------------------------------------------------


@st.cache_resource
def get_engine() -> Engine:
    return create_engine(database_url(), pool_pre_ping=True, future=True)


def _table_exists(engine: Engine, name: str) -> bool:
    q = """
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = :name
    LIMIT 1
    """
    df = _read_sql(engine, q, {"name": name})
    return not df.empty


def _matview_exists(engine: Engine, name: str) -> bool:
    q = """
    SELECT 1 FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relname = :name
      AND c.relkind IN ('r', 'm', 'v')
    LIMIT 1
    """
    df = _read_sql(engine, q, {"name": name})
    return not df.empty


@st.cache_data(ttl=600)
def fetch_year_bounds() -> tuple[int, int]:
    engine = get_engine()
    q = """
    SELECT
        LEAST(
            coalesce((SELECT MIN(year) FROM core_dim_date), 2013),
            coalesce((SELECT MIN(year) FROM core_fact_network_reliability nr
                      JOIN core_dim_date d ON d.date_id = nr.date_id), 2013)
        ) AS y_min,
        GREATEST(
            coalesce((SELECT MAX(year) FROM core_dim_date), 2021),
            coalesce((SELECT MAX(year) FROM core_fact_network_reliability nr
                      JOIN core_dim_date d ON d.date_id = nr.date_id), 2021)
        ) AS y_max
    """
    df = _read_sql(engine, q)
    if df.empty or pd.isna(df.iloc[0]["y_min"]):
        return 2013, 2023
    return int(df.iloc[0]["y_min"]), int(df.iloc[0]["y_max"])


@st.cache_data(ttl=600)
def fetch_companies(commodity: CommodityFilter) -> pd.DataFrame:
    engine = get_engine()
    if commodity == "both":
        q = """
        SELECT DISTINCT c.company_id, c.company_name, ns.commodity, ns.sector_name
        FROM core_dim_company c
        JOIN core_dim_network_sector ns ON ns.network_sector_id = c.network_sector_id
        ORDER BY c.company_name
        """
        return _read_sql(engine, q)
    q = """
    SELECT DISTINCT c.company_id, c.company_name, ns.commodity, ns.sector_name
    FROM core_dim_company c
    JOIN core_dim_network_sector ns ON ns.network_sector_id = c.network_sector_id
    WHERE lower(ns.commodity) = :commodity
    ORDER BY c.company_name
    """
    return _read_sql(engine, q, {"commodity": commodity})


@st.cache_data(ttl=600)
def fetch_regions() -> pd.DataFrame:
    engine = get_engine()
    q = """
    SELECT geography_id, geography_code, geography_name, geography_type
    FROM core_dim_geography
    WHERE geography_type IN ('region', 'distribution_licence_area', 'transmission_zone')
    ORDER BY geography_type, geography_name
    """
    return _read_sql(engine, q)


@st.cache_data(ttl=600)
def home_kpis() -> pd.DataFrame:
    engine = get_engine()
    parts = [
        "SELECT 'core_fact_network_reliability' AS obj, COUNT(*)::bigint AS n FROM core_fact_network_reliability",
        "SELECT 'core_fact_financial_performance' AS obj, COUNT(*)::bigint AS n FROM core_fact_financial_performance",
        "SELECT 'core_fact_customer_metrics' AS obj, COUNT(*)::bigint AS n FROM core_fact_customer_metrics",
        "SELECT 'core_fact_emissions' AS obj, COUNT(*)::bigint AS n FROM core_fact_emissions",
        "SELECT 'core_fact_market_prices' AS obj, COUNT(*)::bigint AS n FROM core_fact_market_prices",
        "SELECT 'core_fact_market_context' AS obj, COUNT(*)::bigint AS n FROM core_fact_market_context",
    ]
    if _matview_exists(engine, "mart_cost_reliability"):
        parts.append("SELECT 'mart_cost_reliability' AS obj, COUNT(*)::bigint AS n FROM mart_cost_reliability")
    if _matview_exists(engine, "mart_economic_impact"):
        parts.append("SELECT 'mart_economic_impact' AS obj, COUNT(*)::bigint AS n FROM mart_economic_impact")
    if _matview_exists(engine, "mart_regulatory_performance"):
        parts.append("SELECT 'mart_regulatory_performance' AS obj, COUNT(*)::bigint AS n FROM mart_regulatory_performance")
    if _matview_exists(engine, "mart_market_context"):
        parts.append("SELECT 'mart_market_context' AS obj, COUNT(*)::bigint AS n FROM mart_market_context")
    sql = " UNION ALL ".join(parts)
    try:
        return _read_sql(engine, sql)
    except Exception:
        return pd.DataFrame(columns=["obj", "n"])


@st.cache_data(ttl=600)
def home_companies_years() -> pd.DataFrame:
    engine = get_engine()
    q = """
    SELECT
        COUNT(DISTINCT c.company_id) AS companies,
        MIN(d.year) AS year_min,
        MAX(d.year) AS year_max
    FROM core_fact_network_reliability nr
    JOIN core_dim_company c ON c.company_id = nr.company_id
    JOIN core_dim_date d ON d.date_id = nr.date_id
    """
    return _read_sql(engine, q)


@st.cache_data(ttl=600)
def home_ens_totex_trend(
    y0: int, y1: int, companies_key: tuple[str, ...] | None
) -> pd.DataFrame:
    engine = get_engine()
    companies = list(companies_key) if companies_key else None
    if not _matview_exists(engine, "mart_cost_reliability"):
        return pd.DataFrame()
    comp_clause = ""
    params: dict[str, Any] = {"y0": y0, "y1": y1}
    if companies:
        comp_clause = " AND company_name IN :names "
        params["names"] = tuple(companies)
    # IN tuple: pandas read_sql with sqlalchemy may need raw expansion
    if companies:
        placeholders = ", ".join([f":c{i}" for i in range(len(companies))])
        comp_clause = f" AND company_name IN ({placeholders}) "
        params = {"y0": y0, "y1": y1, **{f"c{i}": companies[i] for i in range(len(companies))}}
    q = f"""
    SELECT year, SUM(ens_mwh) AS ens_mwh, SUM(actual_totex_million_gbp) AS totex_million_gbp
    FROM mart_cost_reliability
    WHERE year BETWEEN :y0 AND :y1 {comp_clause}
    GROUP BY year ORDER BY year
    """
    return _read_sql(engine, q, params)


# ---------------------------------------------------------------------------
# Theme 1
# ---------------------------------------------------------------------------


@st.cache_data(ttl=600)
def theme1_fuel_poor(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    if not _table_exists(engine, "raw_xlsx_fuel_poor"):
        return pd.DataFrame()
    q = """
    SELECT year, company_name, network_sector, metric_name, value, unit
    FROM raw_xlsx_fuel_poor
    WHERE year BETWEEN :y0 AND :y1
      AND metric_name IN ('fuel_poor_connections_actual', 'fuel_poor_connections_target')
    ORDER BY year, company_name
    """
    return _read_sql(engine, q, {"y0": y0, "y1": y1})


@st.cache_data(ttl=600)
def theme1_reliability_cml(
    y0: int, y1: int, companies_key: tuple[str, ...] | None, commodity: CommodityFilter
) -> pd.DataFrame:
    engine = get_engine()
    companies = list(companies_key) if companies_key else None
    comp_clause = ""
    params: dict[str, Any] = {"y0": y0, "y1": y1}
    if companies:
        placeholders = ", ".join([f":c{i}" for i in range(len(companies))])
        comp_clause = f" AND c.company_name IN ({placeholders}) "
        params.update({f"c{i}": companies[i] for i in range(len(companies))})
    comm_clause = ""
    if commodity != "both":
        comm_clause = " AND lower(ns.commodity) = :comm "
        params["comm"] = commodity
    q = f"""
    SELECT d.year, c.company_name, ns.sector_name, ns.commodity,
           nr.minutes_lost, nr.ens_mwh, nr.gas_lost_volume
    FROM core_fact_network_reliability nr
    JOIN core_dim_date d ON d.date_id = nr.date_id
    JOIN core_dim_company c ON c.company_id = nr.company_id
    JOIN core_dim_network_sector ns ON ns.network_sector_id = nr.network_sector_id
    WHERE d.year BETWEEN :y0 AND :y1 {comp_clause} {comm_clause}
    ORDER BY d.year, c.company_name
    """
    return _read_sql(engine, q, params)


@st.cache_data(ttl=600)
def theme1_prepayment_series(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    if not _table_exists(engine, "raw_xlsx_estimated_costs"):
        return pd.DataFrame()
    q = """
    SELECT period_date, year, metric_name, value, unit, commodity
    FROM raw_xlsx_estimated_costs
    WHERE metric_name IN (
        'prepayment_price_cap_gbp', 'prepayment_svt_market_avg_gbp', 'prepayment_cheapest_gbp'
    )
    AND (year IS NULL OR year BETWEEN :y0 AND :y1 OR period_date IS NOT NULL)
    ORDER BY period_date NULLS LAST, year
    """
    return _read_sql(engine, q, {"y0": y0, "y1": y1})


@st.cache_data(ttl=600)
def theme1_satisfaction_connections(
    y0: int, y1: int, companies_key: tuple[str, ...] | None
) -> pd.DataFrame:
    engine = get_engine()
    if not _table_exists(engine, "raw_xlsx_connections"):
        return pd.DataFrame()
    companies = list(companies_key) if companies_key else None
    comp_clause = ""
    params: dict[str, Any] = {"y0": y0, "y1": y1}
    if companies:
        placeholders = ", ".join([f":c{i}" for i in range(len(companies))])
        comp_clause = f" AND c.company_name IN ({placeholders}) "
        params.update({f"c{i}": companies[i] for i in range(len(companies))})
    q = f"""
    SELECT d.year, c.company_name, ns.sector_name,
           cm.satisfaction_score,
           conn.avg_conn_days
    FROM core_fact_customer_metrics cm
    JOIN core_dim_date d ON d.date_id = cm.date_id
    LEFT JOIN core_dim_company c ON c.company_id = cm.company_id
    LEFT JOIN core_dim_network_sector ns ON ns.network_sector_id = cm.network_sector_id
    LEFT JOIN (
        SELECT year, company_name,
               AVG(value) FILTER (WHERE metric_name LIKE 'connection_%actual%days%')
               AS avg_conn_days
        FROM raw_xlsx_connections
        WHERE year BETWEEN :y0 AND :y1
        GROUP BY year, company_name
    ) conn ON conn.year = d.year AND conn.company_name = c.company_name
    WHERE d.year BETWEEN :y0 AND :y1
      AND cm.satisfaction_score IS NOT NULL
      {comp_clause}
    ORDER BY d.year, c.company_name
    """
    try:
        return _read_sql(engine, q, params)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def theme1_top_operators_vulnerability(y0: int, y1: int) -> pd.DataFrame:
    """Rank operators by fuel poor (GD) and minutes lost (ED) where names align."""
    fp = theme1_fuel_poor(y0, y1)
    rel = theme1_reliability_cml(y0, y1, None, "both")
    if fp.empty and rel.empty:
        return pd.DataFrame()
    fp_p = (
        fp[fp["metric_name"] == "fuel_poor_connections_actual"]
        .groupby("company_name", as_index=False)["value"]
        .mean()
        .rename(columns={"value": "fuel_poor_avg"})
    )
    rel_p = (
        rel.groupby("company_name", as_index=False)
        .agg(minutes_lost_avg=("minutes_lost", "mean"), gas_lost_avg=("gas_lost_volume", "mean"))
    )
    m = fp_p.merge(rel_p, on="company_name", how="outer")
    if m.empty:
        return m

    m["score"] = (
        zscore(m["fuel_poor_avg"].fillna(0)) + zscore(m["minutes_lost_avg"].fillna(0))
    ).fillna(0)
    return m.sort_values("score", ascending=False).head(10)


# ---------------------------------------------------------------------------
# Theme 2
# ---------------------------------------------------------------------------


@st.cache_data(ttl=600)
def theme2_churn_monthly(y0: int, y1: int, commodity: str) -> pd.DataFrame:
    engine = get_engine()
    if not _table_exists(engine, "raw_xlsx_market_volumes"):
        return pd.DataFrame()
    comm = commodity if commodity != "both" else "electricity"
    q = """
    SELECT period_date, year, commodity, instrument, metric_name, value, unit
    FROM raw_xlsx_market_volumes
    WHERE year BETWEEN :y0 AND :y1
      AND lower(commodity) = :comm
      AND (
          lower(coalesce(instrument, '')) LIKE '%churn%'
          OR lower(metric_name) LIKE '%churn%'
          OR instrument = 'churn'
      )
    ORDER BY period_date
    """
    return _read_sql(engine, q, {"y0": y0, "y1": y1, "comm": comm})


@st.cache_data(ttl=600)
def theme2_volatility_monthly(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    q = """
    SELECT period_date, year, commodity, metric_name, value, unit
    FROM core_fact_market_prices
    WHERE year BETWEEN :y0 AND :y1
      AND metric_name IN (
          'volatility_electricity_baseload', 'volatility_gas', 'volatility_electricity_peakload'
      )
    ORDER BY period_date
    """
    try:
        return _read_sql(engine, q, {"y0": y0, "y1": y1})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def theme2_renewable_share_annual(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    q = """
    WITH t AS (
        SELECT year, fuel_source, value
        FROM core_fact_market_context
        WHERE commodity = 'electricity'
          AND metric_name = 'generation_twh'
          AND year BETWEEN :y0 AND :y1
          AND upper(fuel_source) <> 'TOTAL'
    ), tot AS (
        SELECT year, SUM(value) AS twh_total FROM t GROUP BY year
    ), ren AS (
        SELECT year,
               SUM(value) FILTER (
                   WHERE lower(fuel_source) LIKE ANY (ARRAY['%%wind%%', '%%solar%%', '%%hydro%%', '%%bio%%'])
               ) AS twh_renewable
        FROM t
        GROUP BY year
    )
    SELECT r.year,
           100.0 * r.twh_renewable / NULLIF(t.twh_total, 0) AS renewable_pct
    FROM ren r
    JOIN tot t ON t.year = r.year
    ORDER BY r.year
    """
    try:
        return _read_sql(engine, q, {"y0": y0, "y1": y1})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def theme2_power_price_annual_avg(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    q = """
    SELECT year,
           AVG(value) FILTER (WHERE metric_name = 'power_price_baseload') AS power_gbp_mwh
    FROM core_fact_market_prices
    WHERE commodity = 'electricity' AND year BETWEEN :y0 AND :y1
    GROUP BY year ORDER BY year
    """
    try:
        return _read_sql(engine, q, {"y0": y0, "y1": y1})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def theme2_spark_dark_quarterly(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    q = """
    SELECT
        date_trunc('quarter', period_date)::date AS quarter_start,
        AVG(value) FILTER (WHERE metric_name = 'spark_spread_central') AS spark_central,
        AVG(value) FILTER (WHERE metric_name = 'dark_spread') AS dark_spread
    FROM core_fact_market_prices
    WHERE commodity = 'electricity'
      AND year BETWEEN :y0 AND :y1
      AND period_date IS NOT NULL
    GROUP BY 1
    HAVING COUNT(*) > 0
    ORDER BY 1
    """
    try:
        return _read_sql(engine, q, {"y0": y0, "y1": y1})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def theme2_bid_offer_weekly(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    q = """
    SELECT period_date, year, commodity, value AS bid_offer_spread
    FROM core_fact_market_prices
    WHERE metric_name = 'bid_offer_spread'
      AND year BETWEEN :y0 AND :y1
    ORDER BY period_date
    """
    try:
        return _read_sql(engine, q, {"y0": y0, "y1": y1})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def theme2_market_share_hhi() -> pd.DataFrame:
    engine = get_engine()
    q = """
    SELECT year, commodity, company_name, share_pct
    FROM core_fact_market_share
    WHERE commodity = 'electricity'
    ORDER BY year, share_pct DESC
    """
    try:
        df = _read_sql(engine, q)
        if df.empty:
            return df
        rows = []
        for y, g in df.groupby("year"):
            s = g["share_pct"].astype(float) / 100.0
            rows.append({"year": y, "hhi": float((s**2).sum())})
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Theme 3
# ---------------------------------------------------------------------------


@st.cache_data(ttl=600)
def theme3_undergrounding(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    if not _table_exists(engine, "raw_xlsx_undergrounding"):
        return pd.DataFrame()
    q = """
    SELECT year, company_name, metric_name, value
    FROM raw_xlsx_undergrounding
    WHERE year BETWEEN :y0 AND :y1
      AND metric_name = 'undergrounding_km'
    """
    return _read_sql(engine, q, {"y0": y0, "y1": y1})


@st.cache_data(ttl=600)
def theme3_cml_next_year(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    params = {"y0": y0, "y1": y1 + 1}
    q = """
    SELECT d.year, c.company_name, nr.minutes_lost
    FROM core_fact_network_reliability nr
    JOIN core_dim_date d ON d.date_id = nr.date_id
    JOIN core_dim_company c ON c.company_id = nr.company_id
    JOIN core_dim_network_sector ns ON ns.network_sector_id = nr.network_sector_id
    WHERE d.year BETWEEN :y0 AND :y1
      AND lower(ns.sector_name) LIKE '%distribution%'
      AND lower(ns.commodity) = 'electricity'
    """
    return _read_sql(engine, q, params)


@st.cache_data(ttl=600)
def theme3_risk_reduction(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    if not _table_exists(engine, "raw_xlsx_risk_reduction"):
        return pd.DataFrame()
    q = """
    SELECT year, company_name, metric_name, value
    FROM raw_xlsx_risk_reduction
    WHERE year BETWEEN :y0 AND :y1
    """
    return _read_sql(engine, q, {"y0": y0, "y1": y1})


@st.cache_data(ttl=600)
def theme3_gas_lost_by_operator(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    q = """
    SELECT d.year, c.company_name, nr.gas_lost_volume
    FROM core_fact_network_reliability nr
    JOIN core_dim_date d ON d.date_id = nr.date_id
    JOIN core_dim_company c ON c.company_id = nr.company_id
    JOIN core_dim_network_sector ns ON ns.network_sector_id = nr.network_sector_id
    WHERE d.year BETWEEN :y0 AND :y1
      AND lower(ns.commodity) = 'gas'
      AND lower(ns.sector_name) LIKE '%distribution%'
    """
    return _read_sql(engine, q, {"y0": y0, "y1": y1})


@st.cache_data(ttl=600)
def theme3_sf6_ens_totex(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    if _matview_exists(engine, "mart_regulatory_performance") and _matview_exists(
        engine, "mart_cost_reliability"
    ):
        q = """
        SELECT m.year, m.company_name, m.sector_name, m.sf6_kg,
               cr.ens_mwh, cr.actual_totex_million_gbp, m.rore_pct
        FROM mart_regulatory_performance m
        JOIN mart_cost_reliability cr
          ON cr.year = m.year AND cr.company_name = m.company_name AND cr.sector_name = m.sector_name
        WHERE m.year BETWEEN :y0 AND :y1
          AND lower(m.sector_name) LIKE '%transmission%'
        """
        try:
            df = _read_sql(engine, q, {"y0": y0, "y1": y1})
            if not df.empty:
                return df
        except Exception:
            pass
    q = """
    SELECT d.year, c.company_name, ns.sector_name,
           e.sf6_kg, nr.ens_mwh, f.actual_totex_million_gbp
    FROM core_fact_emissions e
    JOIN core_dim_date d ON d.date_id = e.date_id
    JOIN core_dim_company c ON c.company_id = e.company_id
    JOIN core_dim_network_sector ns ON ns.network_sector_id = e.network_sector_id
    JOIN core_fact_network_reliability nr
      ON nr.date_id = e.date_id AND nr.company_id = e.company_id AND nr.network_sector_id = e.network_sector_id
    JOIN core_fact_financial_performance f
      ON f.date_id = e.date_id AND f.company_id = e.company_id AND f.network_sector_id = e.network_sector_id
    WHERE d.year BETWEEN :y0 AND :y1
      AND lower(ns.sector_name) LIKE '%transmission%'
    """
    return _read_sql(engine, q, {"y0": y0, "y1": y1})


@st.cache_data(ttl=600)
def theme3_network_availability(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    if not _table_exists(engine, "raw_xlsx_network_availability"):
        return pd.DataFrame()
    q = """
    SELECT year, company_name, network_sector, metric_name, value
    FROM raw_xlsx_network_availability
    WHERE year BETWEEN :y0 AND :y1
    """
    return _read_sql(engine, q, {"y0": y0, "y1": y1})


# ---------------------------------------------------------------------------
# Theme 4
# ---------------------------------------------------------------------------


@st.cache_data(ttl=600)
def theme4_sf6_change_riio_t1() -> pd.DataFrame:
    engine = get_engine()
    q = """
    WITH base AS (
        SELECT d.year, c.company_name, e.sf6_kg
        FROM core_fact_emissions e
        JOIN core_dim_date d ON d.date_id = e.date_id
        JOIN core_dim_company c ON c.company_id = e.company_id
        JOIN core_dim_network_sector ns ON ns.network_sector_id = e.network_sector_id
        WHERE d.year IN (2013, 2021)
          AND lower(ns.sector_name) LIKE '%electricity transmission%'
    ), p AS (
        SELECT company_name,
               MAX(sf6_kg) FILTER (WHERE year = 2013) AS sf6_2013,
               MAX(sf6_kg) FILTER (WHERE year = 2021) AS sf6_2021
        FROM base
        GROUP BY company_name
    )
    SELECT company_name, sf6_2013, sf6_2021,
           100.0 * (sf6_2021 - sf6_2013) / NULLIF(sf6_2013, 0) AS pct_change
    FROM p
    WHERE sf6_2013 IS NOT NULL OR sf6_2021 IS NOT NULL
    ORDER BY pct_change DESC NULLS LAST
    """
    return _read_sql(engine, q)


@st.cache_data(ttl=600)
def theme4_generation_mix_quarterly(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    if not _table_exists(engine, "raw_xlsx_generation_mix"):
        return pd.DataFrame()
    q = """
    SELECT period_date, year, instrument AS fuel_source, value AS twh
    FROM raw_xlsx_generation_mix
    WHERE year BETWEEN :y0 AND :y1
      AND metric_name = 'generation_share_twh'
    ORDER BY period_date, instrument
    """
    return _read_sql(engine, q, {"y0": y0, "y1": y1})


@st.cache_data(ttl=600)
def theme4_connections_renewable_proxy(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    if not _table_exists(engine, "raw_xlsx_connections"):
        return pd.DataFrame()
    q = """
    SELECT year, company_name, network_sector,
           SUM(value) FILTER (WHERE metric_name ILIKE '%connection%') AS connections_activity
    FROM raw_xlsx_connections
    WHERE year BETWEEN :y0 AND :y1
      AND lower(network_sector) LIKE '%transmission%'
    GROUP BY year, company_name, network_sector
    """
    return _read_sql(engine, q, {"y0": y0, "y1": y1})


@st.cache_data(ttl=600)
def theme4_totex_lag(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    q = """
    SELECT d.year, c.company_name, ns.sector_name, f.actual_totex_million_gbp
    FROM core_fact_financial_performance f
    JOIN core_dim_date d ON d.date_id = f.date_id
    JOIN core_dim_company c ON c.company_id = f.company_id
    JOIN core_dim_network_sector ns ON ns.network_sector_id = f.network_sector_id
    WHERE d.year BETWEEN :y0 AND :y1
      AND lower(ns.sector_name) LIKE '%transmission%'
    """
    return _read_sql(engine, q, {"y0": y0 - 1, "y1": y1})


# ---------------------------------------------------------------------------
# Theme 5
# ---------------------------------------------------------------------------


@st.cache_data(ttl=600)
def theme5_mart_regulatory(y0: int, y1: int, companies_key: tuple[str, ...] | None) -> pd.DataFrame:
    engine = get_engine()
    companies = list(companies_key) if companies_key else None
    if not _matview_exists(engine, "mart_regulatory_performance"):
        return pd.DataFrame()
    comp_clause = ""
    params: dict[str, Any] = {"y0": y0, "y1": y1}
    if companies:
        placeholders = ", ".join([f":c{i}" for i in range(len(companies))])
        comp_clause = f" AND company_name IN ({placeholders}) "
        params.update({f"c{i}": companies[i] for i in range(len(companies))})
    q = f"""
    SELECT *
    FROM mart_regulatory_performance
    WHERE year BETWEEN :y0 AND :y1 {comp_clause}
    """
    return _read_sql(engine, q, params)


@st.cache_data(ttl=600)
def theme5_rore_ens_transmission(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    q = """
    SELECT d.year, c.company_name, f.rore_pct, nr.ens_mwh
    FROM core_fact_financial_performance f
    JOIN core_dim_date d ON d.date_id = f.date_id
    JOIN core_dim_company c ON c.company_id = f.company_id
    JOIN core_dim_network_sector ns ON ns.network_sector_id = f.network_sector_id
    JOIN core_fact_network_reliability nr
      ON nr.date_id = f.date_id AND nr.company_id = f.company_id AND nr.network_sector_id = f.network_sector_id
    WHERE d.year BETWEEN :y0 AND :y1
      AND lower(ns.sector_name) LIKE '%transmission%'
      AND lower(ns.commodity) = 'electricity'
    ORDER BY c.company_name, d.year
    """
    return _read_sql(engine, q, {"y0": y0, "y1": y1})


@st.cache_data(ttl=600)
def theme5_efficiency_rank(y0: int, y1: int) -> pd.DataFrame:
    """(actual/allowance) / year-over-year improvement in reliability_rate proxy."""
    engine = get_engine()
    if not _matview_exists(engine, "mart_cost_reliability"):
        return pd.DataFrame()
    q = """
    WITH m AS (
        SELECT year, company_name, sector_name,
               actual_totex_million_gbp, totex_allowance_million_gbp,
               reliability_rate, ens_mwh
        FROM mart_cost_reliability
        WHERE year BETWEEN :y0 AND :y1
    ), yoy AS (
        SELECT *,
               reliability_rate - LAG(reliability_rate) OVER (PARTITION BY company_name, sector_name ORDER BY year) AS rel_improve
        FROM m
    )
    SELECT year, company_name, sector_name,
           (actual_totex_million_gbp / NULLIF(totex_allowance_million_gbp, 0)) AS spend_ratio,
           rel_improve,
           CASE WHEN rel_improve IS NOT NULL AND rel_improve <> 0
                THEN (actual_totex_million_gbp / NULLIF(totex_allowance_million_gbp, 0)) / rel_improve
                END AS efficiency_score
    FROM yoy
    WHERE rel_improve IS NOT NULL
    ORDER BY efficiency_score DESC NULLS LAST
    """
    return _read_sql(engine, q, {"y0": y0, "y1": y1})


@st.cache_data(ttl=600)
def theme5_connections_totals(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    if not _table_exists(engine, "raw_xlsx_connections"):
        return pd.DataFrame()
    q = """
    SELECT year,
           SUM(value) FILTER (WHERE lower(network_sector) LIKE '%electricity%transmission%') AS elec_tx,
           SUM(value) FILTER (WHERE lower(network_sector) LIKE '%gas%transmission%') AS gas_tx
    FROM raw_xlsx_connections
    WHERE year BETWEEN :y0 AND :y1
    GROUP BY year ORDER BY year
    """
    return _read_sql(engine, q, {"y0": y0, "y1": y1})


@st.cache_data(ttl=600)
def theme5_economic_impact_regions(
    y0: int, y1: int, geography_ids_key: tuple[int, ...] | None
) -> pd.DataFrame:
    engine = get_engine()
    geography_ids = list(geography_ids_key) if geography_ids_key else None
    if not _matview_exists(engine, "mart_economic_impact"):
        return pd.DataFrame()
    geo_clause = ""
    params: dict[str, Any] = {"y0": y0, "y1": y1}
    if geography_ids:
        placeholders = ", ".join([f":g{i}" for i in range(len(geography_ids))])
        geo_clause = f""" AND geography_code IN (
            SELECT geography_code FROM core_dim_geography WHERE geography_id IN ({placeholders})
        ) """
        params.update({f"g{i}": int(geography_ids[i]) for i in range(len(geography_ids))})
    q = f"""
    SELECT year, geography_code, geography_name, SUM(output_at_risk_gbp) AS output_at_risk_gbp
    FROM mart_economic_impact
    WHERE year BETWEEN :y0 AND :y1 {geo_clause}
    GROUP BY year, geography_code, geography_name
    ORDER BY year, geography_name
    """
    return _read_sql(engine, q, params)


@st.cache_data(ttl=600)
def mart_economic_impact_detail(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    if not _matview_exists(engine, "mart_economic_impact"):
        return pd.DataFrame()
    q = """
    SELECT *
    FROM mart_economic_impact
    WHERE year BETWEEN :y0 AND :y1
    """
    return _read_sql(engine, q, {"y0": y0, "y1": y1})


@st.cache_data(ttl=600)
def forecast_ens_annual(y0: int, y1: int, company: str) -> pd.DataFrame:
    engine = get_engine()
    if not _matview_exists(engine, "mart_cost_reliability"):
        return pd.DataFrame()
    q = """
    SELECT year, SUM(ens_mwh) AS ens_mwh
    FROM mart_cost_reliability
    WHERE year BETWEEN :y0 AND :y1 AND company_name = :company
    GROUP BY year ORDER BY year
    """
    return _read_sql(engine, q, {"y0": y0, "y1": y1, "company": company})

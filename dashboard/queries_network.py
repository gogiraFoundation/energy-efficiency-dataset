"""Parameterized SQL access with Streamlit caching."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from dashboard.db import get_engine, object_exists, read_sql
from dashboard.utils import CommodityFilter, apply_canonical_company, load_company_mapping_df, zscore


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
    df = read_sql(engine, q)
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
        return read_sql(engine, q)
    q = """
    SELECT DISTINCT c.company_id, c.company_name, ns.commodity, ns.sector_name
    FROM core_dim_company c
    JOIN core_dim_network_sector ns ON ns.network_sector_id = c.network_sector_id
    WHERE lower(ns.commodity) = :commodity
    ORDER BY c.company_name
    """
    return read_sql(engine, q, {"commodity": commodity})


@st.cache_data(ttl=600)
def fetch_regions() -> pd.DataFrame:
    engine = get_engine()
    q = """
    SELECT geography_id, geography_code, geography_name, geography_type
    FROM core_dim_geography
    WHERE geography_type IN ('region', 'distribution_licence_area', 'transmission_zone')
    ORDER BY geography_type, geography_name
    """
    return read_sql(engine, q)


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
        "SELECT 'core_fact_daily_prices' AS obj, COUNT(*)::bigint AS n FROM core_fact_daily_prices",
        "SELECT 'core_fact_input_output' AS obj, COUNT(*)::bigint AS n FROM core_fact_input_output",
    ]
    if object_exists(engine, "mart_cost_reliability"):
        parts.append("SELECT 'mart_cost_reliability' AS obj, COUNT(*)::bigint AS n FROM mart_cost_reliability")
    if object_exists(engine, "mart_economic_impact"):
        parts.append("SELECT 'mart_economic_impact' AS obj, COUNT(*)::bigint AS n FROM mart_economic_impact")
    if object_exists(engine, "mart_regulatory_performance"):
        parts.append("SELECT 'mart_regulatory_performance' AS obj, COUNT(*)::bigint AS n FROM mart_regulatory_performance")
    if object_exists(engine, "mart_market_context"):
        parts.append("SELECT 'mart_market_context' AS obj, COUNT(*)::bigint AS n FROM mart_market_context")
    if object_exists(engine, "mart_daily_market_monitoring"):
        parts.append("SELECT 'mart_daily_market_monitoring' AS obj, COUNT(*)::bigint AS n FROM mart_daily_market_monitoring")
    if object_exists(engine, "stg_dukes_primary_consumption"):
        parts.append("SELECT 'stg_dukes_primary_consumption' AS obj, COUNT(*)::bigint AS n FROM stg_dukes_primary_consumption")
    if object_exists(engine, "stg_dukes_energy_expenditure"):
        parts.append("SELECT 'stg_dukes_energy_expenditure' AS obj, COUNT(*)::bigint AS n FROM stg_dukes_energy_expenditure")
    if object_exists(engine, "stg_dukes_chapter1_sup"):
        parts.append("SELECT 'stg_dukes_chapter1_sup' AS obj, COUNT(*)::bigint AS n FROM stg_dukes_chapter1_sup")
    if object_exists(engine, "stg_dukes_chapter4"):
        parts.append("SELECT 'stg_dukes_chapter4' AS obj, COUNT(*)::bigint AS n FROM stg_dukes_chapter4")
    if object_exists(engine, "stg_dukes_chapter5"):
        parts.append("SELECT 'stg_dukes_chapter5' AS obj, COUNT(*)::bigint AS n FROM stg_dukes_chapter5")
    if object_exists(engine, "stg_pefa_matrix"):
        parts.append("SELECT 'stg_pefa_matrix' AS obj, COUNT(*)::bigint AS n FROM stg_pefa_matrix")
    if object_exists(engine, "stg_pefa_bridge"):
        parts.append("SELECT 'stg_pefa_bridge' AS obj, COUNT(*)::bigint AS n FROM stg_pefa_bridge")
    sql = " UNION ALL ".join(parts)
    try:
        return read_sql(engine, sql)
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
    return read_sql(engine, q)


@st.cache_data(ttl=600)
def home_ens_totex_trend(
    y0: int, y1: int, companies_key: tuple[str, ...] | None
) -> pd.DataFrame:
    engine = get_engine()
    companies = list(companies_key) if companies_key else None
    if not object_exists(engine, "mart_cost_reliability"):
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
    return read_sql(engine, q, params)


# ---------------------------------------------------------------------------
# Theme 1
# ---------------------------------------------------------------------------


@st.cache_data(ttl=600)
def theme1_fuel_poor(y0: int, y1: int) -> pd.DataFrame:
    """Fuel poor xlsx is often a single snapshot year (e.g. 2021); if the selected
    year range misses that year, fall back to the latest snapshot rows."""
    engine = get_engine()
    if not object_exists(engine, "raw_xlsx_fuel_poor"):
        return pd.DataFrame()
    q = """
    WITH in_range AS (
        SELECT year, company_name, network_sector, metric_name, value, unit
        FROM raw_xlsx_fuel_poor
        WHERE year BETWEEN :y0 AND :y1
          AND metric_name IN ('fuel_poor_connections_actual', 'fuel_poor_connections_target')
    ),
    latest_snap AS (
        SELECT fp.year, fp.company_name, fp.network_sector, fp.metric_name, fp.value, fp.unit
        FROM raw_xlsx_fuel_poor fp
        INNER JOIN (
            SELECT MAX(year) AS y
            FROM raw_xlsx_fuel_poor
            WHERE metric_name IN ('fuel_poor_connections_actual', 'fuel_poor_connections_target')
        ) m ON fp.year = m.y
        WHERE fp.metric_name IN ('fuel_poor_connections_actual', 'fuel_poor_connections_target')
    )
    SELECT * FROM in_range
    UNION ALL
    SELECT * FROM latest_snap
    WHERE NOT EXISTS (SELECT 1 FROM in_range LIMIT 1)
    ORDER BY year, company_name
    """
    try:
        return read_sql(engine, q, {"y0": y0, "y1": y1})
    except Exception:
        q_simple = """
        SELECT year, company_name, network_sector, metric_name, value, unit
        FROM raw_xlsx_fuel_poor
        WHERE year BETWEEN :y0 AND :y1
          AND metric_name IN ('fuel_poor_connections_actual', 'fuel_poor_connections_target')
        ORDER BY year, company_name
        """
        return read_sql(engine, q_simple, {"y0": y0, "y1": y1})


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
    stg_comp_clause = ""
    if companies:
        placeholders = ", ".join([f":c{i}" for i in range(len(companies))])
        stg_comp_clause = f" AND stg.company_name IN ({placeholders}) "
    comm_clause = ""
    if commodity != "both":
        comm_clause = " AND lower(ns.commodity) = :comm "
        params["comm"] = commodity
    q = f"""
    SELECT d.year, c.company_name, ns.sector_name, ns.commodity,
           CASE WHEN lower(ns.commodity) = 'gas'
                THEN COALESCE(nr.minutes_lost, nr.gas_lost_volume)
                ELSE nr.minutes_lost
           END AS minutes_lost,
           nr.ens_mwh, nr.gas_lost_volume
    FROM core_fact_network_reliability nr
    JOIN core_dim_date d ON d.date_id = nr.date_id
    JOIN core_dim_company c ON c.company_id = nr.company_id
    JOIN core_dim_network_sector ns ON ns.network_sector_id = nr.network_sector_id
    WHERE d.year BETWEEN :y0 AND :y1 {comp_clause} {comm_clause}
    ORDER BY d.year, c.company_name
    """
    out = read_sql(engine, q, params)
    if not out.empty or not object_exists(engine, "stg_network_reliability"):
        return out

    q_stg = f"""
    SELECT stg.year, stg.company_name, ns.sector_name, ns.commodity,
           CASE WHEN lower(ns.commodity) = 'gas'
                THEN COALESCE(stg.minutes_lost, stg.gas_lost_volume)
                ELSE stg.minutes_lost
           END AS minutes_lost,
           stg.ens_mwh, stg.gas_lost_volume
    FROM stg_network_reliability stg
    JOIN core_dim_network_sector ns
      ON ns.sector_code = CASE trim(stg.network_sector)
          WHEN 'Electricity Transmission' THEN 'ET'
          WHEN 'Electricity Distribution' THEN 'ED'
          WHEN 'Gas Transmission' THEN 'GT'
          WHEN 'Gas Distribution' THEN 'GD'
          ELSE trim(stg.network_sector)
      END
    WHERE stg.year BETWEEN :y0 AND :y1 {stg_comp_clause} {comm_clause}
    ORDER BY stg.year, stg.company_name
    """
    try:
        return read_sql(engine, q_stg, params)
    except Exception:
        return out


@st.cache_data(ttl=600)
def theme1_prepayment_series(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    if not object_exists(engine, "raw_xlsx_estimated_costs"):
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
    return read_sql(engine, q, {"y0": y0, "y1": y1})


@st.cache_data(ttl=600)
def theme1_satisfaction_connections(
    y0: int, y1: int, companies_key: tuple[str, ...] | None
) -> pd.DataFrame:
    engine = get_engine()
    if not object_exists(engine, "raw_xlsx_connections"):
        return pd.DataFrame()
    companies = list(companies_key) if companies_key else None
    comp_clause = ""
    raw_comp_clause = ""
    params: dict[str, Any] = {"y0": y0, "y1": y1}
    if companies:
        placeholders = ", ".join([f":c{i}" for i in range(len(companies))])
        comp_clause = f" AND c.company_name IN ({placeholders}) "
        raw_comp_clause = f" AND cs.company_name IN ({placeholders}) "
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
               AVG(value) FILTER (
                   WHERE metric_name LIKE 'connection_%actual%days%'
                      OR metric_name IN (
                          'connection_lvssa_actual_days',
                          'connection_lvssb_actual_days'
                      )
               )
               AS avg_conn_days
        FROM raw_xlsx_connections
        WHERE year BETWEEN :y0 AND :y1
        GROUP BY year, company_name
    ) conn ON conn.year = d.year AND conn.company_name = c.company_name
    WHERE d.year BETWEEN :y0 AND :y1
      AND (
          cm.satisfaction_score IS NOT NULL
          OR conn.avg_conn_days IS NOT NULL
      )
      {comp_clause}
    ORDER BY d.year, c.company_name
    """
    try:
        out = read_sql(engine, q, params)
    except Exception:
        out = pd.DataFrame()

    if not out.empty or not object_exists(engine, "raw_xlsx_customer_satisfaction"):
        return out

    q_raw = f"""
    SELECT cs.year,
           cs.company_name,
           NULL::text AS sector_name,
           AVG(cs.value) FILTER (
               WHERE cs.metric_name IN (
                   'customer_survey_score',
                   'stakeholder_engagement_score',
                   'stakeholder_survey_score'
               )
           ) AS satisfaction_score,
           conn.avg_conn_days
    FROM raw_xlsx_customer_satisfaction cs
    INNER JOIN (
        SELECT year, company_name,
               AVG(value) FILTER (
                   WHERE metric_name LIKE 'connection_%actual%days%'
                      OR metric_name IN (
                          'connection_lvssa_actual_days',
                          'connection_lvssb_actual_days'
                      )
               ) AS avg_conn_days
        FROM raw_xlsx_connections
        WHERE year BETWEEN :y0 AND :y1
        GROUP BY year, company_name
    ) conn ON conn.year = cs.year AND conn.company_name = cs.company_name
    WHERE cs.year BETWEEN :y0 AND :y1
      {raw_comp_clause}
    GROUP BY cs.year, cs.company_name, conn.avg_conn_days
    HAVING AVG(cs.value) FILTER (
               WHERE cs.metric_name IN (
                   'customer_survey_score',
                   'stakeholder_engagement_score',
                   'stakeholder_survey_score'
               )
           ) IS NOT NULL
       AND conn.avg_conn_days IS NOT NULL
    ORDER BY cs.year, cs.company_name
    """
    try:
        return read_sql(engine, q_raw, params)
    except Exception:
        return out


@st.cache_data(ttl=600)
def theme1_top_operators_vulnerability(y0: int, y1: int) -> pd.DataFrame:
    """Rank operators by fuel poor (GD) vs gas-distribution reliability (same sector)."""
    fp = theme1_fuel_poor(y0, y1)
    rel = theme1_reliability_cml(y0, y1, None, "gas")
    if fp.empty and rel.empty:
        return pd.DataFrame()
    cmap = load_company_mapping_df()
    fp_p = (
        fp[fp["metric_name"] == "fuel_poor_connections_actual"]
        .assign(
            operator_key=lambda d: apply_canonical_company(d["company_name"], cmap, prefer_sector="GD")
        )
        .groupby("operator_key", as_index=False)["value"]
        .mean()
        .rename(columns={"value": "fuel_poor_avg"})
    )
    rel_p = (
        rel.assign(
            operator_key=lambda d: apply_canonical_company(d["company_name"], cmap, prefer_sector="GD")
        )
        .groupby("operator_key", as_index=False)
        .agg(minutes_lost_avg=("minutes_lost", "mean"), gas_lost_avg=("gas_lost_volume", "mean"))
    )
    m = fp_p.merge(rel_p, on="operator_key", how="outer")
    if m.empty:
        return m

    m["score"] = (
        zscore(m["fuel_poor_avg"].fillna(0)) + zscore(m["minutes_lost_avg"].fillna(0))
    ).fillna(0)
    return m.sort_values("score", ascending=False).head(10)


# ---------------------------------------------------------------------------
# Theme 2
# ---------------------------------------------------------------------------


def _fill_isoweek_period_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Map `isoweek_NN` + `year` to a Monday `period_date` (ISO week)."""
    if df.empty or "period_label" not in df.columns:
        return df
    out = df.copy()
    m = out["period_date"].isna() & out["period_label"].astype(str).str.match(
        r"^isoweek_\d+",
        case=False,
        na=False,
    )
    if not m.any():
        return out

    def _to_date(row: pd.Series) -> Any:
        if pd.notna(row.get("period_date")):
            return row["period_date"]
        lab = str(row.get("period_label", ""))
        mo = re.match(r"^isoweek_(\d+)", lab, re.I)
        if not mo or pd.isna(row.get("year")):
            return pd.NaT
        try:
            return date.fromisocalendar(int(row["year"]), int(mo.group(1)), 1)
        except ValueError:
            return pd.NaT

    out.loc[m, "period_date"] = out.loc[m].apply(_to_date, axis=1)
    return out


@st.cache_data(ttl=600)
def theme2_churn_monthly(y0: int, y1: int, commodity: str) -> pd.DataFrame:
    engine = get_engine()
    if not object_exists(engine, "raw_xlsx_market_volumes"):
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
    return read_sql(engine, q, {"y0": y0, "y1": y1, "comm": comm})


@st.cache_data(ttl=600)
def theme2_volatility_monthly(y0: int, y1: int) -> pd.DataFrame:
    """Monthly volatility: use raw_xlsx_market_prices (core only has annual roll-ups, no period_date)."""
    engine = get_engine()
    if object_exists(engine, "raw_xlsx_market_prices"):
        q_raw = """
        SELECT period_date, year, commodity, metric_name, value, unit
        FROM raw_xlsx_market_prices
        WHERE year BETWEEN :y0 AND :y1
          AND period_date IS NOT NULL
          AND metric_name IN (
              'volatility_electricity_baseload', 'volatility_gas', 'volatility_electricity_peakload'
          )
        ORDER BY period_date
        """
        try:
            df = read_sql(engine, q_raw, {"y0": y0, "y1": y1})
            if not df.empty:
                return df
        except Exception:
            pass

    q_core = """
    SELECT period_date, year, commodity, metric_name, value, unit
    FROM core_fact_market_prices
    WHERE year BETWEEN :y0 AND :y1
      AND metric_name IN (
          'volatility_electricity_baseload', 'volatility_gas', 'volatility_electricity_peakload'
      )
    ORDER BY year, metric_name
    """
    try:
        return read_sql(engine, q_core, {"y0": y0, "y1": y1})
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
        df = read_sql(engine, q, {"y0": y0, "y1": y1})
    except Exception:
        df = pd.DataFrame()
    if not df.empty and df["renewable_pct"].notna().any():
        return df

    if not object_exists(engine, "raw_xlsx_generation_mix"):
        return pd.DataFrame()
    q_raw = """
    WITH t AS (
        SELECT year, instrument AS fuel_source, SUM(value) AS twh
        FROM raw_xlsx_generation_mix
        WHERE commodity = 'electricity'
          AND year BETWEEN :y0 AND :y1
          AND metric_name IN ('generation_share_twh', 'generation_twh')
          AND upper(coalesce(instrument, '')) NOT IN ('TOTAL', '')
        GROUP BY year, instrument
    ), tot AS (
        SELECT year, SUM(twh) AS twh_total FROM t GROUP BY year
    ), ren AS (
        SELECT year,
               SUM(twh) FILTER (
                   WHERE lower(fuel_source) LIKE ANY (ARRAY['%%wind%%', '%%solar%%', '%%hydro%%', '%%bio%%'])
               ) AS twh_renewable
        FROM t
        GROUP BY year
    )
    SELECT r.year,
           100.0 * r.twh_renewable / NULLIF(t2.twh_total, 0) AS renewable_pct
    FROM ren r
    JOIN tot t2 ON t2.year = r.year
    ORDER BY r.year
    """
    try:
        return read_sql(engine, q_raw, {"y0": y0, "y1": y1})
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
        df = read_sql(engine, q, {"y0": y0, "y1": y1})
    except Exception:
        df = pd.DataFrame()
    if not df.empty and df["power_gbp_mwh"].notna().any():
        return df

    if not object_exists(engine, "raw_xlsx_market_prices"):
        return df
    q_raw = """
    SELECT year,
           AVG(value) AS power_gbp_mwh
    FROM raw_xlsx_market_prices
    WHERE commodity = 'electricity'
      AND year BETWEEN :y0 AND :y1
      AND metric_name = 'power_price_baseload'
    GROUP BY year
    ORDER BY year
    """
    try:
        return read_sql(engine, q_raw, {"y0": y0, "y1": y1})
    except Exception:
        return df


@st.cache_data(ttl=600)
def theme2_spark_dark_quarterly(y0: int, y1: int) -> pd.DataFrame:
    """Prefer dated rows in raw_xlsx_market_prices (core roll-ups lack period_date)."""
    engine = get_engine()

    def _has_values(d: pd.DataFrame) -> bool:
        if d.empty:
            return False
        return bool(d[["spark_central", "dark_spread"]].notna().any(axis=None))

    if object_exists(engine, "raw_xlsx_market_prices"):
        q_raw = """
        SELECT
            date_trunc('quarter', period_date)::date AS quarter_start,
            AVG(value) FILTER (WHERE metric_name = 'spark_spread_central') AS spark_central,
            AVG(value) FILTER (WHERE metric_name = 'dark_spread') AS dark_spread
        FROM raw_xlsx_market_prices
        WHERE commodity = 'electricity'
          AND year BETWEEN :y0 AND :y1
          AND period_date IS NOT NULL
          AND metric_name IN ('spark_spread_central', 'dark_spread')
        GROUP BY 1
        HAVING COUNT(*) > 0
        ORDER BY 1
        """
        try:
            raw_df = read_sql(engine, q_raw, {"y0": y0, "y1": y1})
            if _has_values(raw_df):
                return raw_df
        except Exception:
            pass

    q_core_yearly = """
    SELECT
        make_date(year, 1, 1)::date AS quarter_start,
        AVG(value) FILTER (WHERE metric_name = 'spark_spread_central') AS spark_central,
        AVG(value) FILTER (WHERE metric_name = 'dark_spread') AS dark_spread
    FROM core_fact_market_prices
    WHERE commodity = 'electricity'
      AND year BETWEEN :y0 AND :y1
      AND metric_name IN ('spark_spread_central', 'dark_spread')
    GROUP BY year
    HAVING AVG(value) FILTER (WHERE metric_name = 'spark_spread_central') IS NOT NULL
        OR AVG(value) FILTER (WHERE metric_name = 'dark_spread') IS NOT NULL
    ORDER BY 1
    """
    try:
        core_df = read_sql(engine, q_core_yearly, {"y0": y0, "y1": y1})
        if _has_values(core_df):
            return core_df
    except Exception:
        pass

    return pd.DataFrame()


@st.cache_data(ttl=600)
def theme2_bid_offer_weekly(y0: int, y1: int, commodity: str = "electricity") -> pd.DataFrame:
    """Bid-offer series: ISO-week files leave `period_date` null — derive from `isoweek_NN` + year."""
    engine = get_engine()
    comm = commodity if commodity != "both" else "electricity"
    comm_clause = "AND lower(commodity) = lower(:comm)"

    q_core = f"""
    SELECT period_date, period_label, year, commodity, value AS bid_offer_spread
    FROM core_fact_market_prices
    WHERE metric_name = 'bid_offer_spread'
      AND year BETWEEN :y0 AND :y1
      {comm_clause}
      AND (period_date IS NOT NULL OR period_label ~* '^isoweek_[0-9]+')
    ORDER BY year, period_label, period_date
    """
    try:
        core_df = read_sql(engine, q_core, {"y0": y0, "y1": y1, "comm": comm})
        core_df = _fill_isoweek_period_dates(core_df)
        if not core_df.empty and core_df["bid_offer_spread"].notna().any():
            out = core_df.loc[core_df["period_date"].notna()]
            if not out.empty:
                return out
    except Exception:
        pass

    if not object_exists(engine, "raw_xlsx_market_prices"):
        return pd.DataFrame()
    q_raw = f"""
    SELECT period_date, period_label, year, commodity, value AS bid_offer_spread
    FROM raw_xlsx_market_prices
    WHERE metric_name = 'bid_offer_spread'
      AND year BETWEEN :y0 AND :y1
      {comm_clause}
      AND (period_date IS NOT NULL OR period_label ~* '^isoweek_[0-9]+')
    ORDER BY year, period_label, period_date
    """
    try:
        raw_df = read_sql(engine, q_raw, {"y0": y0, "y1": y1, "comm": comm})
        raw_df = _fill_isoweek_period_dates(raw_df)
        raw_df = raw_df.loc[raw_df["period_date"].notna()]
        return raw_df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def theme2_metric_year_bounds(metric_name: str) -> pd.DataFrame:
    """Return available year bounds for a market metric across core/raw tables."""
    engine = get_engine()
    q_core = """
    SELECT MIN(year) AS y_min, MAX(year) AS y_max, COUNT(*) AS n
    FROM core_fact_market_prices
    WHERE metric_name = :metric_name
    """
    q_raw = """
    SELECT MIN(year) AS y_min, MAX(year) AS y_max, COUNT(*) AS n
    FROM raw_xlsx_market_prices
    WHERE metric_name = :metric_name
    """
    rows: list[dict[str, Any]] = []
    try:
        c = read_sql(engine, q_core, {"metric_name": metric_name})
        if not c.empty:
            rows.append(
                {
                    "source": "core_fact_market_prices",
                    "y_min": c.iloc[0]["y_min"],
                    "y_max": c.iloc[0]["y_max"],
                    "n": int(c.iloc[0]["n"] or 0),
                }
            )
    except Exception:
        pass
    if object_exists(engine, "raw_xlsx_market_prices"):
        try:
            r = read_sql(engine, q_raw, {"metric_name": metric_name})
            if not r.empty:
                rows.append(
                    {
                        "source": "raw_xlsx_market_prices",
                        "y_min": r.iloc[0]["y_min"],
                        "y_max": r.iloc[0]["y_max"],
                        "n": int(r.iloc[0]["n"] or 0),
                    }
                )
        except Exception:
            pass
    return pd.DataFrame(rows)


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
        df = read_sql(engine, q)
    except Exception:
        df = pd.DataFrame()

    if df.empty and object_exists(engine, "raw_xlsx_generation_share"):
        q_raw = """
        SELECT year, 'electricity' AS commodity, company_name, value AS share_pct
        FROM raw_xlsx_generation_share
        WHERE metric_name = 'generation_market_share_pct'
        ORDER BY year, share_pct DESC
        """
        try:
            df = read_sql(engine, q_raw)
        except Exception:
            df = pd.DataFrame()

    if df.empty:
        return df
    rows = []
    for y, g in df.groupby("year"):
        raw = g["share_pct"].astype(float)
        # Classic HHI 0–10,000: shares as percentages. If stored as decimals (max <= 1), scale up.
        if float(raw.max()) <= 1.0 + 1e-9:
            s = raw * 100.0
        else:
            s = raw
        rows.append({"year": y, "hhi": float((s**2).sum())})
    return pd.DataFrame(rows)


@st.cache_data(ttl=600)
def theme2_renewable_pct_from_mart(y0: int, y1: int) -> pd.DataFrame:
    """Renewable share of generation from `mart_market_context` (preferred over ad-hoc core SQL)."""
    engine = get_engine()
    if not object_exists(engine, "mart_market_context"):
        return pd.DataFrame()
    q = """
    WITH t AS (
        SELECT year, fuel_source, fuel_value
        FROM mart_market_context
        WHERE commodity = 'electricity'
          AND year BETWEEN :y0 AND :y1
          AND market_share_pct_2024 IS NULL
          AND fuel_value IS NOT NULL
          AND upper(COALESCE(fuel_source, '')) <> 'TOTAL'
    ), ren AS (
        SELECT year,
               SUM(fuel_value) FILTER (
                   WHERE lower(fuel_source) LIKE ANY (ARRAY['%%wind%%', '%%solar%%', '%%hydro%%', '%%bio%%'])
               ) AS twh_renewable,
               SUM(fuel_value) AS twh_total
        FROM t
        GROUP BY year
    )
    SELECT year,
           100.0 * twh_renewable / NULLIF(twh_total, 0) AS renewable_pct
    FROM ren
    WHERE COALESCE(twh_total, 0) > 0
    ORDER BY year
    """
    try:
        return read_sql(engine, q, {"y0": y0, "y1": y1})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def theme2_power_price_from_mart(y0: int, y1: int) -> pd.DataFrame:
    """Average baseload power price by year from `mart_market_context`."""
    engine = get_engine()
    if not object_exists(engine, "mart_market_context"):
        return pd.DataFrame()
    q = """
    SELECT year, MAX(power_baseload_avg) AS power_gbp_mwh
    FROM mart_market_context
    WHERE commodity = 'electricity'
      AND year BETWEEN :y0 AND :y1
      AND market_share_pct_2024 IS NULL
    GROUP BY year
    HAVING MAX(power_baseload_avg) IS NOT NULL
    ORDER BY year
    """
    try:
        return read_sql(engine, q, {"y0": y0, "y1": y1})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def theme2_hhi_from_market_context(y0: int, y1: int) -> pd.DataFrame:
    """Generation HHI (0–10,000) from wholesale share rows appended in `mart_market_context`."""
    engine = get_engine()
    if not object_exists(engine, "mart_market_context"):
        return pd.DataFrame()
    q = """
    SELECT year, commodity, fuel_source AS company_name, market_share_pct_2024 AS share_pct
    FROM mart_market_context
    WHERE market_share_pct_2024 IS NOT NULL
      AND year BETWEEN :y0 AND :y1
    ORDER BY year, commodity, market_share_pct_2024 DESC
    """
    try:
        df = read_sql(engine, q, {"y0": y0, "y1": y1})
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    rows: list[dict[str, Any]] = []
    for (y, comm), g in df.groupby(["year", "commodity"]):
        raw = g["share_pct"].astype(float)
        if float(raw.max()) <= 1.0 + 1e-9:
            s = raw * 100.0
        else:
            s = raw
        rows.append({"year": y, "commodity": comm, "hhi": float((s**2).sum())})
    return pd.DataFrame(rows)


@st.cache_data(ttl=600)
def theme2_market_context_churn_annual(y0: int, y1: int, commodity: str) -> pd.DataFrame:
    """Annual churn ratio from `mart_market_context` (contrasted with monthly raw churn scatter)."""
    engine = get_engine()
    if not object_exists(engine, "mart_market_context"):
        return pd.DataFrame()
    comm = commodity if commodity != "both" else "electricity"
    q = """
    SELECT year, MAX(churn_ratio_avg) AS churn_ratio_avg
    FROM mart_market_context
    WHERE commodity = :commodity
      AND year BETWEEN :y0 AND :y1
      AND market_share_pct_2024 IS NULL
    GROUP BY year
    ORDER BY year
    """
    try:
        return read_sql(engine, q, {"y0": y0, "y1": y1, "commodity": comm})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def theme2_daily_market_monitoring(y0: int, y1: int, commodity: CommodityFilter) -> pd.DataFrame:
    engine = get_engine()
    if not object_exists(engine, "mart_daily_market_monitoring"):
        return pd.DataFrame()
    params: dict[str, Any] = {"y0": y0, "y1": y1}
    comm_clause = ""
    if commodity != "both":
        comm_clause = " AND commodity = :commodity "
        params["commodity"] = commodity
    q = f"""
    SELECT *
    FROM mart_daily_market_monitoring
    WHERE year BETWEEN :y0 AND :y1 {comm_clause}
    ORDER BY year, commodity, source_name, metric_name
    """
    return read_sql(engine, q, params)


@st.cache_data(ttl=600)
def theme2_daily_price_series(y0: int, y1: int, commodity: CommodityFilter) -> pd.DataFrame:
    engine = get_engine()
    if not object_exists(engine, "core_fact_daily_prices"):
        return pd.DataFrame()
    params: dict[str, Any] = {"y0": y0, "y1": y1}
    comm_clause = ""
    if commodity != "both":
        comm_clause = " AND commodity = :commodity "
        params["commodity"] = commodity
    q = f"""
    SELECT
        period_date,
        EXTRACT(YEAR FROM period_date)::int AS year,
        commodity,
        source_name,
        metric_name,
        value,
        unit
    FROM core_fact_daily_prices
    WHERE period_date BETWEEN make_date(:y0, 1, 1) AND make_date(:y1, 12, 31)
      {comm_clause}
    ORDER BY period_date, commodity, source_name, metric_name
    """
    return read_sql(engine, q, params)


@st.cache_data(ttl=600)
def dukes_primary_gdp_ratio(y0: int, y1: int) -> pd.DataFrame:
    """DUKES 1.1.4 — primary energy, GDP, energy ratio (national macro)."""
    engine = get_engine()
    if not object_exists(engine, "stg_dukes_primary_consumption"):
        return pd.DataFrame()
    q = """
    SELECT year, primary_energy_mtoe, primary_energy_twh, gdp_gbp_billion, energy_ratio,
           energy_intensity_index_1970_100, source_file
    FROM stg_dukes_primary_consumption
    WHERE year BETWEEN :y0 AND :y1
    ORDER BY year
    """
    try:
        return read_sql(engine, q, {"y0": y0, "y1": y1})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def dukes_expenditure_by_sector(y0: int, y1: int) -> pd.DataFrame:
    """DUKES 1.1.6 — expenditure by final user (£ million)."""
    engine = get_engine()
    if not object_exists(engine, "stg_dukes_energy_expenditure"):
        return pd.DataFrame()
    q = """
    SELECT year, sector, expenditure_million_gbp, source_file
    FROM stg_dukes_energy_expenditure
    WHERE year BETWEEN :y0 AND :y1
    ORDER BY year, sector
    """
    try:
        return read_sql(engine, q, {"y0": y0, "y1": y1})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def dukes_final_consumption_long(y0: int, y1: int, sector: str | None = None) -> pd.DataFrame:
    """DUKES 1.1.5 — energy by final user and fuel (ktoe / TWh)."""
    engine = get_engine()
    if not object_exists(engine, "stg_dukes_final_consumption"):
        return pd.DataFrame()
    params: dict[str, Any] = {"y0": y0, "y1": y1}
    sec_clause = ""
    if sector and sector != "all":
        sec_clause = " AND sector = :sector "
        params["sector"] = sector
    q = f"""
    SELECT year, sector, fuel_type, energy_ktoe, energy_twh, source_file
    FROM stg_dukes_final_consumption
    WHERE year BETWEEN :y0 AND :y1 {sec_clause}
    ORDER BY year, sector, fuel_type
    """
    try:
        return read_sql(engine, q, params)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def dukes_primary_fuels_mtoe(y0: int, y1: int) -> pd.DataFrame:
    """DUKES 1.1.1.B — inland consumption by fuel (Mtoe)."""
    engine = get_engine()
    if not object_exists(engine, "stg_dukes_primary_fuels"):
        return pd.DataFrame()
    q = """
    SELECT year, fuel_type, consumption_mtoe, source_file
    FROM stg_dukes_primary_fuels
    WHERE year BETWEEN :y0 AND :y1
    ORDER BY year, fuel_type
    """
    try:
        return read_sql(engine, q, {"y0": y0, "y1": y1})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def dukes_network_cost_proxy(y0: int, y1: int) -> pd.DataFrame:
    """Average annual GB network cost per domestic customer (£/year) from Ofgem workbook."""
    engine = get_engine()
    if not object_exists(engine, "raw_xlsx_estimated_costs"):
        return pd.DataFrame()
    q = """
    SELECT
        year,
        AVG(value) FILTER (WHERE metric_name = 'cost_per_customer_et_gbp') AS elec_tx_avg_gbp,
        AVG(value) FILTER (WHERE metric_name = 'cost_per_customer_ed_gbp') AS elec_dx_avg_gbp,
        AVG(value) FILTER (WHERE metric_name = 'cost_per_customer_gt_gbp') AS gas_tx_avg_gbp,
        AVG(value) FILTER (WHERE metric_name = 'cost_per_customer_gd_gbp') AS gas_dx_avg_gbp
    FROM raw_xlsx_estimated_costs
    WHERE year BETWEEN :y0 AND :y1
      AND year IS NOT NULL
    GROUP BY year
    ORDER BY year
    """
    try:
        return read_sql(engine, q, {"y0": y0, "y1": y1})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def pefa_bridge(y0: int, y1: int) -> pd.DataFrame:
    """ONS PEFA Table E — residence vs territory bridge (TJ)."""
    engine = get_engine()
    if not object_exists(engine, "stg_pefa_bridge"):
        return pd.DataFrame()
    q = """
    SELECT reference_year, bridge_code, bridge_label, energy_tj, source_file
    FROM stg_pefa_bridge
    WHERE reference_year BETWEEN :y0 AND :y1
    ORDER BY reference_year, bridge_code
    """
    try:
        return read_sql(engine, q, {"y0": y0, "y1": y1})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def pefa_table_d_indicators_au(y0: int, y1: int) -> pd.DataFrame:
    """PEFA Table D key rows — total economy column ``A_U`` (TJ)."""
    engine = get_engine()
    if not object_exists(engine, "stg_pefa_matrix"):
        return pd.DataFrame()
    q = """
    SELECT reference_year, row_no, row_code, row_label, energy_tj, source_file
    FROM stg_pefa_matrix
    WHERE table_id = 'D'
      AND industry_code = 'A_U'
      AND reference_year BETWEEN :y0 AND :y1
    ORDER BY reference_year, row_no NULLS LAST, row_code
    """
    try:
        return read_sql(engine, q, {"y0": y0, "y1": y1})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def pefa_physical_supply_au(y0: int, y1: int, limit: int = 25) -> pd.DataFrame:
    """Table A — physical supply by product row for aggregate ``A_U`` (TJ)."""
    engine = get_engine()
    if not object_exists(engine, "stg_pefa_matrix"):
        return pd.DataFrame()
    q = """
    SELECT reference_year, row_code, row_label, energy_tj, source_file
    FROM stg_pefa_matrix
    WHERE table_id = 'A'
      AND industry_code = 'A_U'
      AND reference_year BETWEEN :y0 AND :y1
    ORDER BY energy_tj DESC NULLS LAST
    LIMIT :lim
    """
    try:
        return read_sql(engine, q, {"y0": y0, "y1": y1, "lim": limit})
    except Exception:
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Theme 3
# ---------------------------------------------------------------------------


@st.cache_data(ttl=600)
def theme3_undergrounding(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    if not object_exists(engine, "raw_xlsx_undergrounding"):
        return pd.DataFrame()
    q = """
    SELECT year, company_name, metric_name, value
    FROM raw_xlsx_undergrounding
    WHERE year BETWEEN :y0 AND :y1
      AND metric_name = 'undergrounding_km'
    """
    df = read_sql(engine, q, {"y0": y0, "y1": y1})
    if df.empty or "company_name" not in df.columns:
        return df
    cmap = load_company_mapping_df()
    out = df.copy()
    out["company_name"] = apply_canonical_company(out["company_name"], cmap, prefer_sector="ED")
    return out


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
    df = read_sql(engine, q, params)
    if df.empty or "company_name" not in df.columns:
        return df
    cmap = load_company_mapping_df()
    out = df.copy()
    out["company_name"] = apply_canonical_company(out["company_name"], cmap, prefer_sector="ED")
    return out


@st.cache_data(ttl=600)
def theme3_risk_reduction(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    if not object_exists(engine, "raw_xlsx_risk_reduction"):
        return pd.DataFrame()
    q = """
    SELECT year, company_name, metric_name, value
    FROM raw_xlsx_risk_reduction
    WHERE year BETWEEN :y0 AND :y1
    """
    df = read_sql(engine, q, {"y0": y0, "y1": y1})
    if df.empty or "company_name" not in df.columns:
        return df
    cmap = load_company_mapping_df()
    out = df.copy()
    out["company_name"] = apply_canonical_company(out["company_name"], cmap, prefer_sector="GD")
    return out


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
    df = read_sql(engine, q, {"y0": y0, "y1": y1})
    if df.empty or "company_name" not in df.columns:
        return df
    cmap = load_company_mapping_df()
    out = df.copy()
    out["company_name"] = apply_canonical_company(out["company_name"], cmap, prefer_sector="GD")
    return out


@st.cache_data(ttl=600)
def theme3_sf6_ens_totex(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    if object_exists(engine, "mart_regulatory_performance") and object_exists(
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
            df = read_sql(engine, q, {"y0": y0, "y1": y1})
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
    return read_sql(engine, q, {"y0": y0, "y1": y1})


@st.cache_data(ttl=600)
def theme3_network_availability(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    if not object_exists(engine, "raw_xlsx_network_availability"):
        return pd.DataFrame()
    q = """
    SELECT year, company_name, network_sector, metric_name, value
    FROM raw_xlsx_network_availability
    WHERE year BETWEEN :y0 AND :y1
    """
    return read_sql(engine, q, {"y0": y0, "y1": y1})


# ---------------------------------------------------------------------------
# Theme 4
# ---------------------------------------------------------------------------


def _sf6_change_et_sql_sources(y0: int, y1: int) -> list[tuple[str, str]]:
    """Core → staging → raw; ET via sector_code / network_sector."""
    ylist = ", ".join(str(y) for y in sorted({y0, y1}))
    return [
        (
            "core",
            f"""
    WITH base AS (
        SELECT d.year, c.company_name, e.sf6_kg
        FROM core_fact_emissions e
        JOIN core_dim_date d ON d.date_id = e.date_id
        JOIN core_dim_company c ON c.company_id = e.company_id
        JOIN core_dim_network_sector ns ON ns.network_sector_id = e.network_sector_id
        WHERE d.year IN ({ylist})
          AND ns.sector_code = 'ET'
    )""",
        ),
        (
            "stg",
            f"""
    WITH base AS (
        SELECT year, company_name, sf6_kg
        FROM stg_emissions
        WHERE year IN ({ylist})
          AND network_sector = 'ET'
    )""",
        ),
        (
            "raw",
            f"""
    WITH base AS (
        SELECT year, company_name,
               MAX(value) AS sf6_kg
        FROM raw_xlsx_emissions
        WHERE year IN ({ylist})
          AND metric_name = 'sf6_kg'
          AND (
              lower(trim(network_sector)) LIKE '%electricity%transmission%'
              OR trim(network_sector) IN ('ET', 'Electricity Transmission')
          )
        GROUP BY year, company_name
    )""",
        ),
    ]


@st.cache_data(ttl=600)
def theme4_sf6_change_riio_t1() -> pd.DataFrame:
    """RIIO-T1 style SF6 change for electricity transmission (ET).

    Prefers ``core_fact_emissions``; falls back to ``stg_emissions`` then
    ``raw_xlsx_emissions`` when core is empty (e.g. company dimension mismatch).

    Tries year pairs that match RIIO-T1 ``Y1``…``Y8`` → calendar years first:
    scheme ``start_fy_end_year`` is **2014**, so **Y1→2014** and **Y8→2021** (not 2013).
    Falls back to other pairs if extracts use different dating.
    """
    engine = get_engine()
    year_pairs = (
        (2014, 2021),
        (2013, 2021),
        (2014, 2022),
        (2015, 2023),
        (2012, 2020),
        (2011, 2019),
    )
    for y0, y1 in year_pairs:
        heads = _sf6_change_et_sql_sources(y0, y1)
        tail = f"""
    , p AS (
        SELECT company_name,
               MAX(sf6_kg) FILTER (WHERE year = {y0}) AS sf6_baseline,
               MAX(sf6_kg) FILTER (WHERE year = {y1}) AS sf6_compare
        FROM base
        GROUP BY company_name
    )
    SELECT company_name,
           {y0} AS baseline_year,
           {y1} AS compare_year,
           sf6_baseline AS sf6_baseline_kg,
           sf6_compare AS sf6_compare_kg,
           (sf6_compare - sf6_baseline) AS sf6_delta_kg,
           CASE
               WHEN sf6_baseline IS NOT NULL AND sf6_baseline <> 0
               THEN 100.0 * (sf6_compare - sf6_baseline) / sf6_baseline
               ELSE NULL
           END AS pct_change
    FROM p
    WHERE sf6_baseline IS NOT NULL OR sf6_compare IS NOT NULL
    ORDER BY pct_change DESC NULLS LAST
    """
        for name, head in heads:
            if name == "stg" and not object_exists(engine, "stg_emissions"):
                continue
            if name == "raw" and not object_exists(engine, "raw_xlsx_emissions"):
                continue
            try:
                df = read_sql(engine, head + tail)
                if not df.empty:
                    cmap = load_company_mapping_df()
                    out = df.copy()
                    out["company_name"] = apply_canonical_company(
                        out["company_name"], cmap, prefer_sector="ET"
                    )
                    if out["company_name"].duplicated().any():
                        out = out.drop_duplicates(subset=["company_name"], keep="first")
                    return out
            except Exception:
                continue
    return pd.DataFrame()


@st.cache_data(ttl=600)
def theme4_generation_mix_quarterly(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    if not object_exists(engine, "raw_xlsx_generation_mix"):
        return pd.DataFrame()
    q = """
    SELECT period_date, year, instrument AS fuel_source, value AS twh
    FROM raw_xlsx_generation_mix
    WHERE year BETWEEN :y0 AND :y1
      AND metric_name = 'generation_share_twh'
    ORDER BY period_date, instrument
    """
    return read_sql(engine, q, {"y0": y0, "y1": y1})


@st.cache_data(ttl=600)
def theme4_connections_renewable_proxy(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    if not object_exists(engine, "raw_xlsx_connections"):
        return pd.DataFrame()
    q = """
    SELECT year, company_name, network_sector,
           SUM(value) FILTER (WHERE metric_name ILIKE '%connection%') AS connections_activity
    FROM raw_xlsx_connections
    WHERE year BETWEEN :y0 AND :y1
      AND lower(network_sector) LIKE '%transmission%'
    GROUP BY year, company_name, network_sector
    """
    return read_sql(engine, q, {"y0": y0, "y1": y1})


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
    return read_sql(engine, q, {"y0": y0 - 1, "y1": y1})


# ---------------------------------------------------------------------------
# Theme 5
# ---------------------------------------------------------------------------


@st.cache_data(ttl=600)
def theme5_mart_regulatory(y0: int, y1: int, companies_key: tuple[str, ...] | None) -> pd.DataFrame:
    engine = get_engine()
    companies = list(companies_key) if companies_key else None
    if not object_exists(engine, "mart_regulatory_performance"):
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
    return read_sql(engine, q, params)


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
    return read_sql(engine, q, {"y0": y0, "y1": y1})


@st.cache_data(ttl=600)
def theme5_efficiency_rank(y0: int, y1: int) -> pd.DataFrame:
    """(actual/allowance) / year-over-year improvement in reliability_rate proxy."""
    engine = get_engine()
    if not object_exists(engine, "mart_cost_reliability"):
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
    return read_sql(engine, q, {"y0": y0, "y1": y1})


@st.cache_data(ttl=600)
def theme5_connections_totals(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    if not object_exists(engine, "raw_xlsx_connections"):
        return pd.DataFrame()
    q = """
    SELECT year,
           SUM(value) FILTER (WHERE lower(network_sector) LIKE '%electricity%transmission%') AS elec_tx,
           SUM(value) FILTER (WHERE lower(network_sector) LIKE '%gas%transmission%') AS gas_tx
    FROM raw_xlsx_connections
    WHERE year BETWEEN :y0 AND :y1
    GROUP BY year ORDER BY year
    """
    return read_sql(engine, q, {"y0": y0, "y1": y1})


@st.cache_data(ttl=600)
def theme5_economic_impact_regions(
    y0: int, y1: int, geography_ids_key: tuple[int, ...] | None
) -> pd.DataFrame:
    engine = get_engine()
    geography_ids = list(geography_ids_key) if geography_ids_key else None
    if not object_exists(engine, "mart_economic_impact"):
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
    return read_sql(engine, q, params)


@st.cache_data(ttl=600)
def mart_economic_impact_detail(y0: int, y1: int) -> pd.DataFrame:
    engine = get_engine()
    if not object_exists(engine, "mart_economic_impact"):
        return pd.DataFrame()
    q = """
    SELECT *
    FROM mart_economic_impact
    WHERE year BETWEEN :y0 AND :y1
    """
    return read_sql(engine, q, {"y0": y0, "y1": y1})


@st.cache_data(ttl=600)
def cross_commodity_risk(
    y0: int, y1: int, geography_names: tuple[str, ...] | None = None
) -> pd.DataFrame:
    """Cross-commodity reliability / disruption summary from `mart_cross_commodity_risk`."""
    engine = get_engine()
    if not object_exists(engine, "mart_cross_commodity_risk"):
        return pd.DataFrame()
    geo_clause = ""
    params: dict[str, Any] = {"y0": y0, "y1": y1}
    if geography_names:
        placeholders = ", ".join([f":g{i}" for i in range(len(geography_names))])
        geo_clause = f" AND geography_name IN ({placeholders}) "
        params.update({f"g{i}": geography_names[i] for i in range(len(geography_names))})
    q = f"""
    SELECT year, geography_name, commodity, sector_name,
           ens_mwh, gas_disruption_volume, avg_reliability_rate, gas_vulnerability_index
    FROM mart_cross_commodity_risk
    WHERE year BETWEEN :y0 AND :y1 {geo_clause}
    ORDER BY year, geography_name, commodity, sector_name
    """
    try:
        return read_sql(engine, q, params)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def decarbonisation_narrative(y0: int, y1: int) -> pd.DataFrame:
    """ENS vs LCREE narrative mart (`mart_decarbonisation_narrative`)."""
    engine = get_engine()
    if not object_exists(engine, "mart_decarbonisation_narrative"):
        return pd.DataFrame()
    q = """
    SELECT *
    FROM mart_decarbonisation_narrative
    WHERE year BETWEEN :y0 AND :y1
    ORDER BY year
    """
    try:
        return read_sql(engine, q, {"y0": y0, "y1": y1})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def theme5_economic_impact_top_industries(y0: int, y1: int, top_n: int = 15) -> pd.DataFrame:
    """Industries with largest summed output at risk over the range."""
    engine = get_engine()
    if not object_exists(engine, "mart_economic_impact"):
        return pd.DataFrame()
    q = """
    SELECT industry_name, SUM(output_at_risk_gbp) AS output_at_risk_gbp
    FROM mart_economic_impact
    WHERE year BETWEEN :y0 AND :y1
    GROUP BY industry_name
    ORDER BY output_at_risk_gbp DESC NULLS LAST
    LIMIT :top_n
    """
    try:
        return read_sql(engine, q, {"y0": y0, "y1": y1, "top_n": top_n})
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def forecast_ens_annual(y0: int, y1: int, company: str) -> pd.DataFrame:
    engine = get_engine()
    base_company = company.split(" (", 1)[0].strip()

    # Primary source: mart ENS by selected company.
    if object_exists(engine, "mart_cost_reliability"):
        q_mart = """
        SELECT year, SUM(ens_mwh) AS ens_mwh, 'ens_mwh'::text AS metric_name
        FROM mart_cost_reliability
        WHERE year BETWEEN :y0 AND :y1
          AND company_name = :company
        GROUP BY year
        ORDER BY year
        """
        try:
            m = read_sql(engine, q_mart, {"y0": y0, "y1": y1, "company": company})
            if len(m.dropna(subset=["ens_mwh"])) >= 3:
                return m
        except Exception:
            pass

    # Fallback 1: core reliability ENS with alias/base-name support.
    if object_exists(engine, "core_fact_network_reliability"):
        q_core_ens = """
        SELECT
            d.year,
            SUM(nr.ens_mwh) AS ens_mwh,
            'ens_mwh'::text AS metric_name
        FROM core_fact_network_reliability nr
        JOIN core_dim_date d ON d.date_id = nr.date_id
        JOIN core_dim_company c ON c.company_id = nr.company_id
        WHERE d.year BETWEEN :y0 AND :y1
          AND c.company_name IN (:company, :base_company)
        GROUP BY d.year
        ORDER BY d.year
        """
        try:
            c_ens = read_sql(
                engine,
                q_core_ens,
                {"y0": y0, "y1": y1, "company": company, "base_company": base_company},
            )
            if len(c_ens.dropna(subset=["ens_mwh"])) >= 3:
                return c_ens
        except Exception:
            pass

    # Fallback 2: gas-lost volume as resilience proxy (for gas distribution operators
    # where ENS is systematically null, e.g., Cadent entries).
    if object_exists(engine, "core_fact_network_reliability"):
        q_core_gas = """
        SELECT
            d.year,
            SUM(nr.gas_lost_volume) AS ens_mwh,
            'gas_lost_volume_proxy'::text AS metric_name
        FROM core_fact_network_reliability nr
        JOIN core_dim_date d ON d.date_id = nr.date_id
        JOIN core_dim_company c ON c.company_id = nr.company_id
        WHERE d.year BETWEEN :y0 AND :y1
          AND c.company_name IN (:company, :base_company)
          AND nr.gas_lost_volume IS NOT NULL
        GROUP BY d.year
        ORDER BY d.year
        """
        try:
            c_gas = read_sql(
                engine,
                q_core_gas,
                {"y0": y0, "y1": y1, "company": company, "base_company": base_company},
            )
            if not c_gas.empty:
                return c_gas
        except Exception:
            pass

    return pd.DataFrame(columns=["year", "ens_mwh", "metric_name"])

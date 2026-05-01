"""
UK Ofgem / pipeline analytics dashboard.

Run from repo root:
  export DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/db
  streamlit run dashboard/app.py
"""

from __future__ import annotations

import io
import sys
from datetime import date
from pathlib import Path

# Streamlit puts the script directory on sys.path, not the repo root — `import dashboard` needs the parent.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd
import streamlit as st

from dashboard import plots
from dashboard import queries
from dashboard.config import database_url
from dashboard.utils import CommodityFilter, implied_co2_kg_per_mwh_generation_mix

st.set_page_config(
    page_title="UK Energy — Ofgem analytics",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _companies_tuple(sel: list[str] | None) -> tuple[str, ...] | None:
    if not sel:
        return None
    return tuple(sorted(sel))


def _geo_tuple(ids: list[int] | None) -> tuple[int, ...] | None:
    if not ids:
        return None
    return tuple(sorted(ids))


def sidebar_filters():
    st.sidebar.header("Filters")
    try:
        y_min, y_max = queries.fetch_year_bounds()
    except Exception as e:
        st.sidebar.error("Database unavailable (see error below).")
        st.sidebar.code(str(e), language="text")
        st.sidebar.markdown(
            "Configure the DB in **`.env`**: either **`DATABASE_URL`**, or **`UK_ENERGY_DB_PASSWORD`** plus "
            "`UK_ENERGY_DB_HOST`, `UK_ENERGY_DB_PORT`, `UK_ENERGY_DB_NAME`, `UK_ENERGY_DB_USER` (same as the pipeline). "
            "Use a real host (e.g. `localhost`), not the word `host` from examples. **`unset DATABASE_URL`** if a stale "
            "shell export overrides `.env`."
        )
        st.stop()
    y0, y1 = st.sidebar.slider("Year range", y_min, y_max, (y_min, min(y_max, y_min + 8)))
    commodity: CommodityFilter = st.sidebar.radio("Commodity", ("both", "electricity", "gas"), horizontal=True)
    companies_df = queries.fetch_companies(commodity)
    names = companies_df["company_name"].dropna().unique().tolist() if not companies_df.empty else []
    companies_sel = st.sidebar.multiselect("Companies (optional)", names)
    regions_df = queries.fetch_regions()
    geo_options = (
        regions_df[["geography_id", "geography_name"]].drop_duplicates().values.tolist()
        if not regions_df.empty
        else []
    )
    geo_labels = {f"{name} ({gid})": gid for gid, name in geo_options}
    geo_pick = st.sidebar.multiselect("Regions (economic impact only)", list(geo_labels.keys()))
    geo_ids = [geo_labels[k] for k in geo_pick]
    return {
        "y0": y0,
        "y1": y1,
        "commodity": commodity,
        "companies_key": _companies_tuple(companies_sel),
        "geo_key": _geo_tuple(geo_ids),
    }


def csv_download(df: pd.DataFrame, label: str, fname: str):
    if df is None or df.empty:
        return
    st.download_button(label, df.to_csv(index=False).encode("utf-8"), file_name=fname, mime="text/csv")


def render_home(f):
    st.title("Home")
    st.markdown("Explore RIIO and GB wholesale data ingested from Ofgem Data Portal workbooks and supporting ONS feeds.")
    try:
        kpis = queries.home_kpis()
        cy = queries.home_companies_years()
    except Exception as ex:
        st.warning(f"Partial load: {ex}")
        kpis, cy = pd.DataFrame(), pd.DataFrame()
    c1, c2, c3, c4 = st.columns(4)
    if not cy.empty:
        r = cy.iloc[0]
        c1.metric("Distinct companies (network facts)", int(r.get("companies", 0) or 0))
        c2.metric("Year min", int(r.get("year_min", 0) or 0))
        c3.metric("Year max", int(r.get("year_max", 0) or 0))
    c4.metric("Today", date.today().isoformat())
    st.subheader("Table row counts")
    if kpis.empty:
        st.info("No KPI rows — check database connection and core tables.")
    else:
        st.dataframe(kpis.rename(columns={"obj": "object", "n": "rows"}), use_container_width=True)
        csv_download(kpis, "Download counts CSV", "home_table_counts.csv")
    st.subheader("ENS and totex (mart_cost_reliability)")
    trend = queries.home_ens_totex_trend(f["y0"], f["y1"], f["companies_key"])
    if trend.empty:
        st.info("No mart_cost_reliability data for selection — refresh materialized views after ETL.")
    else:
        fig = plots.dual_axis_lines(
            trend, "year", "ens_mwh", "totex_million_gbp", "ENS (MWh)", "Totex (£m)", "Annual aggregates"
        )
        st.plotly_chart(fig, use_container_width=True)
        csv_download(trend, "Download trend CSV", "home_ens_totex.csv")


def render_theme1(f):
    st.title("Social & consumer vulnerability")
    with st.expander("What this theme shows"):
        st.markdown(
            """
            - **Fuel poor connections** (gas distribution) vs **minutes lost** (electricity distribution) are shown at
              **operator** level; there is no NUTS regional join in the current core model (network facts use GB).
            - **Prepayment** series are retail price indicators — they are **not** a network/wholesale cost breakdown.
            """
        )
    fp = queries.theme1_fuel_poor(f["y0"], f["y1"])
    rel = queries.theme1_reliability_cml(f["y0"], f["y1"], f["companies_key"], f["commodity"])
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Fuel poor (actual) by operator")
        if fp.empty:
            st.info("No raw_xlsx_fuel_poor rows.")
        else:
            fp_a = fp[fp["metric_name"] == "fuel_poor_connections_actual"]
            if fp_a.empty:
                st.info("No fuel_poor_connections_actual metrics.")
            else:
                fig = plots.bar_grouped(
                    fp_a.groupby("company_name", as_index=False)["value"].mean(),
                    "company_name",
                    ["value"],
                    "Average fuel poor connections (reported)",
                )
                st.plotly_chart(fig, use_container_width=True)
                csv_download(fp_a, "Download CSV", "theme1_fuel_poor.csv")
    with c2:
        st.subheader("Customer minutes lost (CML proxy)")
        if rel.empty:
            st.info("No reliability rows for filters.")
        else:
            g = rel.groupby("company_name", as_index=False)["minutes_lost"].mean().dropna()
            fig = plots.bar_grouped(g, "company_name", ["minutes_lost"], "Average minutes lost")
            st.plotly_chart(fig, use_container_width=True)
            csv_download(rel, "Download CSV", "theme1_reliability.csv")
    st.subheader("Fuel poor vs minutes lost (scatter by operator name match)")
    if not fp.empty and not rel.empty:
        fp_a = fp[fp["metric_name"] == "fuel_poor_connections_actual"].groupby("company_name", as_index=False)[
            "value"
        ].mean()
        rel_a = rel.groupby("company_name", as_index=False)["minutes_lost"].mean()
        j = fp_a.merge(rel_a, on="company_name", how="inner")
        if j.empty:
            st.caption("No overlapping company names between fuel poor and reliability.")
        else:
            fig = plots.scatter_with_regression(
                j, "value", "minutes_lost", title="Fuel poor vs CML (matched names)", x_title="Fuel poor", y_title="Minutes lost"
            )
            st.plotly_chart(fig, use_container_width=True)
    st.subheader("Prepayment price cap and market prices")
    prep = queries.theme1_prepayment_series(f["y0"], f["y1"])
    if prep.empty:
        st.info("No prepayment series in raw_xlsx_estimated_costs.")
    else:
        wide = prep.pivot_table(index="period_date", columns="metric_name", values="value", aggfunc="mean")
        wide = wide.reset_index().dropna(how="all")
        fig = plots.multi_line(wide, "period_date", [c for c in wide.columns if c != "period_date"], "GB prepayment (£/year)")
        st.plotly_chart(fig, use_container_width=True)
        csv_download(prep, "Download CSV", "theme1_prepayment.csv")
    st.subheader("Customer satisfaction vs connection time (proxy)")
    sat = queries.theme1_satisfaction_connections(f["y0"], f["y1"], f["companies_key"])
    if sat.empty:
        st.info("No joined satisfaction / connections data.")
    else:
        d = sat.dropna(subset=["satisfaction_score"])
        fig = plots.scatter_with_regression(
            d,
            "avg_conn_days",
            "satisfaction_score",
            title="Satisfaction vs average connection days",
            x_title="Avg connection days (raw_xlsx_connections)",
            y_title="Satisfaction score",
        )
        st.plotly_chart(fig, use_container_width=True)
        csv_download(sat, "Download CSV", "theme1_satisfaction_connections.csv")
    st.subheader("Top operators by composite vulnerability score")
    top = queries.theme1_top_operators_vulnerability(f["y0"], f["y1"])
    if top.empty:
        st.info("Could not rank — need fuel poor and/or reliability data.")
    else:
        st.dataframe(top.head(5), use_container_width=True)
        csv_download(top.head(5), "Download CSV", "theme1_top5_vulnerability.csv")


def render_theme2(f):
    st.title("Economic & market efficiency")
    with st.expander("What this theme shows"):
        st.markdown(
            """
            - **Churn** is read from `raw_xlsx_market_volumes` (monthly); **volatility** from `core_fact_market_prices`.
            - **HHI** uses `core_fact_market_share` (2024 snapshot in the reference pipeline) — not a full time series.
            """
        )
    comm = "electricity" if f["commodity"] == "both" else f["commodity"]
    churn = queries.theme2_churn_monthly(f["y0"], f["y1"], comm)
    vol = queries.theme2_volatility_monthly(f["y0"], f["y1"])
    st.subheader("Monthly churn vs electricity baseload volatility")
    if churn.empty or vol.empty:
        st.info("Churn and/or volatility data missing for range — check raw_xlsx_market_volumes and core_fact_market_prices.")
    else:
        v2 = vol[vol["metric_name"] == "volatility_electricity_baseload"].copy()
        c_m = churn.groupby("period_date", as_index=False)["value"].mean().rename(columns={"value": "churn"})
        v_m = v2.groupby("period_date", as_index=False)["value"].mean().rename(columns={"value": "volatility"})
        j = c_m.merge(v_m, on="period_date", how="inner")
        fig = plots.scatter_with_regression(
            j, "churn", "volatility", title="Churn vs volatility (monthly, merged on date)", x_title="Churn proxy", y_title="Volatility index"
        )
        st.plotly_chart(fig, use_container_width=True)
        csv_download(j, "Download CSV", "theme2_churn_vol.csv")
    st.subheader("Renewable share vs average baseload price")
    ren = queries.theme2_renewable_share_annual(f["y0"], f["y1"])
    price = queries.theme2_power_price_annual_avg(f["y0"], f["y1"])
    if ren.empty or price.empty:
        st.info("Need generation context and power prices in core facts.")
    else:
        j = ren.merge(price, on="year", how="inner")
        fig = plots.dual_axis_lines(j, "year", "renewable_pct", "power_gbp_mwh", "Renewable %", "Power £/MWh", "Annual")
        st.plotly_chart(fig, use_container_width=True)
        csv_download(j, "Download CSV", "theme2_renewable_price.csv")
    st.subheader("Spark vs dark spread (quarterly)")
    sd = queries.theme2_spark_dark_quarterly(f["y0"], f["y1"])
    if sd.empty:
        st.info("No quarterly spread data.")
    else:
        fig = plots.bar_grouped(sd, "quarter_start", ["spark_central", "dark_spread"], "£/MWh")
        st.plotly_chart(fig, use_container_width=True)
        csv_download(sd, "Download CSV", "theme2_spark_dark.csv")
    st.subheader("Bid–offer spread heatmap (liquidity stress proxy)")
    bo = queries.theme2_bid_offer_weekly(f["y0"], f["y1"])
    if bo.empty:
        st.info("No bid_offer_spread in market prices.")
    else:
        bo = bo.copy()
        bo["week"] = pd.to_datetime(bo["period_date"]).dt.isocalendar().week.astype(str)
        bo["yr"] = bo["year"].astype(str)
        fig = plots.heatmap_calendarish(bo, "week", "yr", "bid_offer_spread", "Bid-offer spread")
        st.plotly_chart(fig, use_container_width=True)
    st.subheader("Market concentration (HHI) from 2024 share snapshot")
    hhi = queries.theme2_market_share_hhi()
    if hhi.empty:
        st.info("No core_fact_market_share — cannot compute HHI.")
    else:
        fig = plots.bar_grouped(hhi, "year", ["hhi"], "Herfindahl–Hirschman Index (generation share)")
        st.plotly_chart(fig, use_container_width=True)


def render_theme3(f):
    st.title("Reliability & operational resilience")
    with st.expander("What this theme shows"):
        st.markdown(
            """
            - **Undergrounding (km)** vs **CML** uses a **one-year lag** merge on distribution operator name.
            - **Gas risk removal** vs **gas lost** compares GD programme metrics with reliability facts.
            """
        )
    und = queries.theme3_undergrounding(f["y0"], f["y1"])
    cml = queries.theme3_cml_next_year(f["y0"], f["y1"])
    st.subheader("Undergrounding km (Y) vs minutes lost (Y+1)")
    if und.empty or cml.empty:
        st.info("Need raw_xlsx_undergrounding and ED reliability facts.")
    else:
        u = und.groupby(["company_name", "year"], as_index=False)["value"].sum().rename(columns={"value": "km"})
        cml2 = cml.rename(columns={"year": "y_cml", "minutes_lost": "cml"})
        rows = []
        for _, r in u.iterrows():
            m = cml2[(cml2["company_name"] == r["company_name"]) & (cml2["y_cml"] == r["year"] + 1)]
            if not m.empty:
                rows.append({"company_name": r["company_name"], "km": r["km"], "cml": m["cml"].mean()})
        lag_df = pd.DataFrame(rows)
        if lag_df.empty:
            st.info("No overlapping operator/year+1 CML pairs.")
        else:
            fig = plots.scatter_with_regression(
                lag_df, "km", "cml", title="Undergrounding vs next-year CML", x_title="km", y_title="Minutes lost"
            )
            st.plotly_chart(fig, use_container_width=True)
            csv_download(lag_df, "Download CSV", "theme3_underground_cml_lag.csv")
    risk = queries.theme3_risk_reduction(f["y0"], f["y1"])
    gas = queries.theme3_gas_lost_by_operator(f["y0"], f["y1"])
    st.subheader("Risk removal vs gas lost volume")
    if risk.empty or gas.empty:
        st.info("Need raw_xlsx_risk_reduction and gas distribution reliability.")
    else:
        r_act = risk[risk["metric_name"].str.contains("actual", case=False, na=False)]
        r_g = r_act.groupby(["company_name", "year"], as_index=False)["value"].mean().rename(columns={"value": "risk_metric"})
        g_g = gas.groupby(["company_name", "year"], as_index=False)["gas_lost_volume"].mean()
        j = r_g.merge(g_g, on=["company_name", "year"], how="inner")
        if len(j) >= 2:
            from scipy import stats

            try:
                r_s = stats.pearsonr(j["risk_metric"].astype(float), j["gas_lost_volume"].astype(float))
                st.caption(f"Pearson r = {r_s.statistic:.3f}, p = {r_s.pvalue:.3g}")
            except Exception:
                st.caption("Correlation could not be computed (constant series or insufficient variation).")
        fig = plots.bar_grouped(j, "company_name", ["risk_metric", "gas_lost_volume"], "Risk vs gas lost (scale differs — use table)")
        st.plotly_chart(fig, use_container_width=True)
        csv_download(j, "Download CSV", "theme3_risk_gas.csv")
    st.subheader("SF6 vs ENS vs spend (transmission)")
    b = queries.theme3_sf6_ens_totex(f["y0"], f["y1"])
    if b.empty:
        st.info("No merged regulatory/cost mart rows for transmission.")
    else:
        d = b.dropna(subset=["sf6_kg", "ens_mwh"])
        fig = plots.bubble_chart(
            d,
            "sf6_kg",
            "ens_mwh",
            "actual_totex_million_gbp" if "actual_totex_million_gbp" in d.columns else "sf6_kg",
            "company_name",
            "Transmission owners",
        )
        st.plotly_chart(fig, use_container_width=True)
        csv_download(b, "Download CSV", "theme3_sf6_ens.csv")
    st.subheader("Network availability (gas distribution, %)")
    av = queries.theme3_network_availability(f["y0"], f["y1"])
    if av.empty:
        st.info("No raw_xlsx_network_availability.")
    else:
        av_g = av[av["metric_name"] == "network_availability_pct"]
        if av_g.empty:
            st.dataframe(av.head(20), use_container_width=True)
        else:
            mean_a = float(av_g["value"].mean())
            mean_b = float(av_g["value"].median())
            fig = plots.gauge_pair(mean_a, mean_b, "Mean availability", "Median availability", "GD availability %")
            st.plotly_chart(fig, use_container_width=True)


def render_theme4(f):
    st.title("Environmental & decarbonisation")
    with st.expander("What this theme shows"):
        st.markdown(
            """
            - **Implied CO2 / MWh** uses **illustrative** static emission factors in `utils.FUEL_CO2_KG_PER_MWH` — not official BEIS factors.
            - **Generation mix** uses quarterly `raw_xlsx_generation_mix` when available.
            """
        )
    st.subheader("SF6 % change 2013 → 2021 (electricity transmission)")
    sf6 = queries.theme4_sf6_change_riio_t1()
    if sf6.empty:
        st.info("No emissions facts for ET in 2013/2021.")
    else:
        fig = plots.bar_horizontal_diverging(sf6, "company_name", "pct_change", "% change SF6")
        st.plotly_chart(fig, use_container_width=True)
        csv_download(sf6, "Download CSV", "theme4_sf6_change.csv")
    st.subheader("Implied CO2 intensity from generation mix (illustrative)")
    mix = queries.theme4_generation_mix_quarterly(f["y0"], f["y1"])
    if mix.empty:
        st.info("No quarterly generation mix in raw.")
    else:
        mix = mix.copy()
        mix["period_key"] = mix["period_date"].astype(str)
        long = mix.assign(value=mix["twh"])
        co2_series = implied_co2_kg_per_mwh_generation_mix(long, "period_key", "fuel_source", "value")
        co2_df = pd.DataFrame(
            {"period": co2_series.index.astype(str), "kg_co2_per_mwh_implied": co2_series.values}
        )
        fig = plots.line_simple(co2_df, "period", "kg_co2_per_mwh_implied", "Illustrative implied intensity", "kg CO2e / MWh")
        st.plotly_chart(fig, use_container_width=True)
        csv_download(co2_df, "Download CSV", "theme4_implied_co2.csv")
    st.subheader("Connections activity vs lagged totex (transmission)")
    conn = queries.theme4_connections_renewable_proxy(f["y0"], f["y1"])
    tex = queries.theme4_totex_lag(f["y0"], f["y1"])
    if conn.empty or tex.empty:
        st.info("Need raw connections and financial facts.")
    else:
        cg = conn.groupby(["company_name", "year"], as_index=False)["connections_activity"].sum()
        tg = tex.rename(columns={"year": "year_tex", "actual_totex_million_gbp": "totex"})
        rows = []
        for _, r in cg.iterrows():
            m = tg[(tg["company_name"] == r["company_name"]) & (tg["year_tex"] == r["year"] - 1)]
            if not m.empty:
                rows.append(
                    {
                        "company_name": r["company_name"],
                        "year": r["year"],
                        "connections_activity": r["connections_activity"],
                        "totex_lag1": m["totex"].mean(),
                    }
                )
        j = pd.DataFrame(rows)
        if j.empty:
            st.info("No company/year alignment for lagged totex.")
        else:
            fig = plots.scatter_with_regression(
                j,
                "totex_lag1",
                "connections_activity",
                title="Connections vs prior-year totex",
                x_title="Totex t-1 (£m)",
                y_title="Connections activity (sum of metrics)",
            )
            st.plotly_chart(fig, use_container_width=True)
            csv_download(j, "Download CSV", "theme4_conn_totex.csv")
    st.subheader("Stacked generation mix (TWh by quarter)")
    if mix.empty:
        st.info("No mix data.")
    else:
        fig = plots.stacked_area_from_long(mix, "period_date", "fuel_source", "twh", "Generation mix")
        st.plotly_chart(fig, use_container_width=True)


def render_theme5(f):
    st.title("Systemic & regulatory performance")
    with st.expander("What this theme shows"):
        st.markdown(
            """
            - **RoRE vs ENS** uses transmission electricity joins on `core_fact_*`.
            - **Efficiency score** = (actual/allowance) / YoY change in `reliability_rate` from `mart_cost_reliability`.
            - **Underperformers** combines RoRE, ENS, and satisfaction with simple z-scores.
            """
        )
    st.subheader("RoRE vs ENS (electricity transmission)")
    re = queries.theme5_rore_ens_transmission(f["y0"], f["y1"])
    if re.empty:
        st.info("No joined financial/reliability transmission rows.")
    else:
        fig = plots.scatter_with_regression(
            re.dropna(subset=["rore_pct", "ens_mwh"]),
            "rore_pct",
            "ens_mwh",
            color_col="company_name",
            title="RoRE vs ENS by company-year",
            x_title="RoRE %",
            y_title="ENS MWh",
        )
        st.plotly_chart(fig, use_container_width=True)
        csv_download(re, "Download CSV", "theme5_rore_ens.csv")
    st.subheader("Expenditure efficiency ranking")
    er = queries.theme5_efficiency_rank(f["y0"], f["y1"])
    if er.empty:
        st.info("Need mart_cost_reliability with reliability_rate.")
    else:
        st.dataframe(er.head(25), use_container_width=True)
        csv_download(er, "Download CSV", "theme5_efficiency.csv")
    st.subheader("New connections (gas & electricity transmission proxies)")
    ct = queries.theme5_connections_totals(f["y0"], f["y1"])
    if ct.empty:
        st.info("No raw_xlsx_connections aggregates.")
    else:
        fig = plots.multi_line(ct, "year", [c for c in ct.columns if c != "year"], "Connection metrics (summed)")
        st.plotly_chart(fig, use_container_width=True)
        st.caption("GDP overlay not loaded in this database — connections only.")
        csv_download(ct, "Download CSV", "theme5_connections.csv")
    st.subheader("Economic impact: output at risk by region (filtered)")
    ei = queries.theme5_economic_impact_regions(f["y0"], f["y1"], f["geo_key"])
    if ei.empty:
        st.info("Select regions or load mart_economic_impact.")
    else:
        fig = plots.line_simple(
            ei.groupby("year", as_index=False)["output_at_risk_gbp"].sum(),
            "year",
            "output_at_risk_gbp",
            "Summed output at risk (filtered regions)",
        )
        st.plotly_chart(fig, use_container_width=True)
    st.subheader("Top underperformers (heuristic composite)")
    mr = queries.theme5_mart_regulatory(f["y0"], f["y1"], f["companies_key"])
    re_ens = queries.theme5_rore_ens_transmission(f["y0"], f["y1"])
    if mr.empty:
        st.info("mart_regulatory_performance missing or empty.")
    else:
        from dashboard.utils import zscore

        ens_by_co = (
            re_ens.groupby("company_name", as_index=False)["ens_mwh"].mean()
            if not re_ens.empty
            else pd.DataFrame(columns=["company_name", "ens_mwh"])
        )
        mr2 = mr.merge(ens_by_co, on="company_name", how="left")
        g = mr2.groupby("company_name", as_index=False).agg(
            rore=("rore_pct", "mean"), ens=("ens_mwh", "mean"), sat=("satisfaction_score", "mean")
        )
        g = g.dropna(how="all")
        if len(g) < 3:
            st.dataframe(g, use_container_width=True)
        else:
            g["bad"] = zscore(g["rore"].fillna(g["rore"].median())) + zscore(g["ens"].fillna(g["ens"].median())) - zscore(
                g["sat"].fillna(g["sat"].median())
            )
            worst = g.sort_values("bad", ascending=False).head(3)
            st.dataframe(worst, use_container_width=True)
            csv_download(worst, "Download CSV", "theme5_underperformers.csv")


def render_methodology():
    st.title("Methodology & data lineage")
    st.markdown(
        """
### Sources
- **Ofgem Data Portal** Excel workbooks are registered in `metadata/xlsx_registry.yaml` and loaded into `raw_xlsx_*` tables.
- **Core facts** (`core_fact_*`) and **dimensions** (`core_dim_*`) are populated by the pipeline merge scripts under `sql/core/`.
- **Synonym views** `fact_*` / `dim_*` may exist if `sql/core/28_aliases.sql` was applied.

### Materialized views
After ETL, refresh marts, for example:
```sql
REFRESH MATERIALIZED VIEW mart_cost_reliability;
REFRESH MATERIALIZED VIEW mart_economic_impact;
REFRESH MATERIALIZED VIEW mart_cross_commodity_risk;
REFRESH MATERIALIZED VIEW mart_regulatory_performance;
REFRESH MATERIALIZED VIEW mart_decarbonisation_narrative;
REFRESH MATERIALIZED VIEW mart_market_context;
```

### Limits & caveats
- Network reliability facts are keyed at **GB** geography in the reference load — regional maps for ENS are not available without extra staging.
- Some charts read **`raw_xlsx_*` directly** because metrics are not promoted to core.
- **Implied CO2** uses static illustrative factors — do not use for compliance reporting.

### Connection
Set `DATABASE_URL` (see `dashboard/.env.example`). This app uses **SQLAlchemy** with bound parameters only.
        """
    )


def render_forecasting(f):
    st.title("Forecasting (bonus)")
    st.warning("Low confidence: annual ENS is noisy; use for exploration only.")
    mr = queries.theme5_mart_regulatory(f["y0"], f["y1"], None)
    if mr.empty:
        st.info("Need mart_regulatory_performance.")
        return
    companies = sorted(mr["company_name"].dropna().unique().tolist())
    pick = st.selectbox("Operator", companies)
    s = queries.forecast_ens_annual(f["y0"], f["y1"], pick)
    if len(s) < 3:
        st.info("Not enough annual ENS points to regress.")
        return
    import numpy as np
    from sklearn.linear_model import LinearRegression

    x = s["year"].values.reshape(-1, 1)
    y = s["ens_mwh"].fillna(0).values
    model = LinearRegression().fit(x, y)
    future_years = np.arange(f["y1"] + 1, f["y1"] + 4).reshape(-1, 1)
    pred = model.predict(future_years)
    st.line_chart(pd.DataFrame({"year": list(s["year"]) + list(future_years.flatten()), "ens": list(y) + list(pred)}).set_index("year"))
    st.caption(f"Linear trend slope {model.coef_[0]:.2f} MWh/year, intercept {model.intercept_:.2f}")
    csv_download(s, "Download history CSV", "forecast_ens_history.csv")


def render_whatif(f):
    st.title("What-if: network cost shock on output at risk (bonus)")
    st.warning("The mart applies a structured model — scaling is a **scenario illustration**, not a forecast.")
    detail = queries.mart_economic_impact_detail(f["y0"], f["y1"])
    if detail.empty:
        st.info("mart_economic_impact not available.")
        return
    pct = st.slider("Hypothetical increase in modeled cost exposure (%)", -20, 40, 10)
    base = detail["output_at_risk_gbp"].sum()
    shocked = base * (1.0 + pct / 100.0)
    c1, c2 = st.columns(2)
    c1.metric("Baseline Σ output_at_risk_gbp", f"£{base:,.0f}")
    c2.metric("Shocked total", f"£{shocked:,.0f}", delta=f"{pct}% scenario")
    st.dataframe(
        detail.groupby("industry_name", as_index=False)["output_at_risk_gbp"]
        .sum()
        .assign(shocked=lambda d: d["output_at_risk_gbp"] * (1.0 + pct / 100.0))
        .head(20),
        use_container_width=True,
    )


def export_pdf_stub():
    try:
        from fpdf import FPDF
    except ImportError:
        st.sidebar.caption("Install fpdf2 for PDF export.")
        return

    class PDF(FPDF):
        def header(self):
            self.set_font("Helvetica", "B", 12)
            self.cell(0, 10, "UK Ofgem analytics snapshot", ln=True)

    if st.sidebar.button("Export PDF summary"):
        pdf = PDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=11)
        pdf.multi_cell(
            0,
            6,
            "Automated summary — charts may be added when kaleido is available for static exports.",
        )
        out = pdf.output(dest="S")
        raw = out.encode("latin-1", "replace") if isinstance(out, str) else out
        st.sidebar.download_button(
            "Download PDF",
            raw,
            file_name="dashboard_summary.pdf",
            mime="application/pdf",
        )


def main():
    st.sidebar.title("Navigation")
    page = st.sidebar.radio(
        "Page",
        (
            "Home",
            "Social & vulnerability",
            "Economic & market",
            "Reliability & resilience",
            "Environmental",
            "Systemic & regulatory",
            "Methodology",
            "Forecasting",
            "What-if",
        ),
    )
    try:
        database_url()
    except Exception as e:
        st.error(str(e))
        st.stop()
    f = sidebar_filters()
    export_pdf_stub()
    if page == "Home":
        render_home(f)
    elif page == "Social & vulnerability":
        render_theme1(f)
    elif page == "Economic & market":
        render_theme2(f)
    elif page == "Reliability & resilience":
        render_theme3(f)
    elif page == "Environmental":
        render_theme4(f)
    elif page == "Systemic & regulatory":
        render_theme5(f)
    elif page == "Methodology":
        render_methodology()
    elif page == "Forecasting":
        render_forecasting(f)
    elif page == "What-if":
        render_whatif(f)


if __name__ == "__main__":
    main()

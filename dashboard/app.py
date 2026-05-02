"""
UK Ofgem / pipeline analytics dashboard.

Run from repo root:
  export DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/db
  streamlit run dashboard/app.py
"""

from __future__ import annotations

import io
import re
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
from dashboard import queries_network as queries
from dashboard import queries_retail
from dashboard import queries_renewables
from dashboard import queries_whd
from dashboard import queries_scheme
from dashboard import queries_cross
from dashboard import queries_dukes_chapters as qdc
from dashboard.config import database_url
from dashboard.filters import sidebar_filters
from dashboard.summary_page import render_summary
from dashboard.styles import inject_css
from dashboard.utils import (
    CommodityFilter,
    apply_canonical_company,
    implied_co2_kg_per_mwh_generation_mix,
    load_company_mapping_df,
)

st.set_page_config(
    page_title="UK Energy — Ofgem analytics",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)


# Domain-grouped sidebar nav; page strings match render_* dispatch in main().
NAV: dict[str, list[str]] = {
    "Overview": ["Home", "Summary"],
    "Networks": [
        "Social & vulnerability",
        "Reliability & resilience",
        "Environmental",
        "Renewables deployment",
    ],
    "Markets & regulation": [
        "Economic & market",
        "Daily market monitoring",
        "DUKES macro context",
        "ONS PEFA",
        "Systemic & regulatory",
    ],
    "Retail": [
        "Supplier health",
        "Consumer vulnerability",
        "Switching & competition",
        "Affordability",
        "Complaints",
        "Incidents",
        "Satisfaction",
        "Warm Home Discount",
        "Policy scheme metrics",
    ],
    "Cross-layer": ["Cross-layer analytics"],
    "Forecasts": ["Forecasting", "What-if"],
    "Reference": ["Methodology"],
}

# Glossary surfaced via info(term) under specialist subheaders.
GLOSSARY: dict[str, str] = {
    "ens": "Energy Not Supplied — MWh that customers did not receive due to interruptions.",
    "bid_offer": "Bid–offer spread — gap between best buy and sell prices; wider = lower liquidity / more stress.",
    "rore": "Return on Regulatory Equity — Ofgem's headline regulated return for network owners.",
    "cml": "Customer Minutes Lost — average minutes of supply interruption per customer per year.",
    "hhi": "Herfindahl–Hirschman Index — concentration score. Retail supplier-health chart uses 0–1 (normalized); value is the mean of separate electricity and gas retail HHIs from shares. Wholesale/generation charts use the classic 0–10,000 scale — check each chart title.",
    "gas_lost_proxy": "Gas lost volume — from Ofgem network reliability statistics (gas distribution). Shown when ENS (Energy Not Supplied) is not populated for this operator; it is a rough activity proxy, not ENS, and units follow the source workbook (do not compare to MWh ENS).",
    "totex": "Totex — total expenditure (capex + opex) on a network or programme.",
    "nps": "Net Promoter Score — share of promoters minus share of detractors; range −100 to +100.",
}


def init_session_state(y_min: int, y_max: int) -> None:
    """Seed defaults so widget keys survive across page switches."""
    st.session_state.setdefault("theme", "Light")
    first_cat = next(iter(NAV))
    st.session_state.setdefault("category", first_cat)
    st.session_state.setdefault("page", NAV[first_cat][0])
    st.session_state.setdefault("year_range", (y_min, min(y_max, y_min + 8)))
    st.session_state.setdefault("commodity", "both")
    st.session_state.setdefault("companies_sel", [])
    st.session_state.setdefault("supplier_pick", [])
    st.session_state.setdefault("payment_method", "all")
    st.session_state.setdefault("geo_pick", [])


def info(term: str) -> None:
    """Inline glossary caption used under specialist subheaders."""
    text = GLOSSARY.get(term)
    if text:
        st.caption(f"ℹ️ {text}")


def csv_download(df: pd.DataFrame, label: str, fname: str) -> None:
    if df is None or df.empty:
        return
    st.download_button(
        label,
        df.to_csv(index=False).encode("utf-8"),
        file_name=fname,
        mime="text/csv",
        key=f"dl_{fname}",
    )


def render_alerts(f) -> None:
    """Cheap, cached threshold checks shown at the top of every page."""
    alerts: list[str] = []
    try:
        avail = queries.theme3_network_availability(f["y0"], f["y1"])
        if not avail.empty and "metric_name" in avail.columns and "value" in avail.columns:
            mean_av = avail.loc[
                avail["metric_name"] == "network_availability_pct", "value"
            ].mean()
            if pd.notna(mean_av) and float(mean_av) < 99.0:
                alerts.append(
                    f"Gas-distribution availability mean **{float(mean_av):.2f}%** is below the 99% guide."
                )
        ens = queries.home_ens_totex_trend(f["y0"], f["y1"], None)
        if not ens.empty and "ens_mwh" in ens.columns:
            ens_max = pd.to_numeric(ens["ens_mwh"], errors="coerce").max()
            if pd.notna(ens_max) and float(ens_max) > 100_000:
                alerts.append(
                    f"ENS exceeded **100 GWh** in at least one year of the selected range "
                    f"(peak {float(ens_max) / 1000:.1f} GWh)."
                )
    except Exception:
        return
    if not alerts:
        st.success("All monitored thresholds within normal ranges for the selected filters.")
        return
    for a in alerts:
        st.warning(a)


def render_home(f):
    st.title("Home")
    st.markdown("Explore RIIO and GB wholesale data ingested from Ofgem Data Portal workbooks and supporting ONS feeds.")
    try:
        with st.spinner("Loading home KPIs…"):
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
    info("ens")
    info("totex")
    with st.spinner("Loading ENS / totex trend…"):
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
            - **Fuel poor connections** are **gas distribution (GD)**. The **CML bar chart** follows your Commodity filter
              (electricity vs gas). The **fuel poor vs CML scatter** always pairs GD fuel poor with **gas-distribution**
              minutes lost so operator names sit in the same sector.
            - **Fuel poor** Excel extracts are often **one snapshot year** (e.g. end of GD1); if your year slider excludes it,
              the dashboard still surfaces the latest snapshot when in-range rows are empty.
            - **Prepayment** series are retail price indicators — they are **not** a network/wholesale cost breakdown.
            """
        )
    with st.spinner("Loading vulnerability data…"):
        fp = queries.theme1_fuel_poor(f["y0"], f["y1"])
        rel = queries.theme1_reliability_cml(f["y0"], f["y1"], f["companies_key"], f["commodity"])
        rel_gas_for_scatter = queries.theme1_reliability_cml(f["y0"], f["y1"], f["companies_key"], "gas")
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
        info("cml")
        if rel.empty:
            st.info(
                "No reliability/CML rows for these filters (or core facts empty). "
                "Run staging + core load, or relax company filters. "
                "If core is empty, the app falls back to `stg_network_reliability` when present."
            )
        else:
            g = rel.groupby("company_name", as_index=False)["minutes_lost"].mean().dropna()
            fig = plots.bar_grouped(g, "company_name", ["minutes_lost"], "Average minutes lost")
            st.plotly_chart(fig, use_container_width=True)
            csv_download(rel, "Download CSV", "theme1_reliability.csv")
            if f["commodity"] != "gas":
                st.caption(
                    "Bar chart uses your Commodity filter. The scatter below pairs fuel poor with **gas-distribution** CML "
                    "so GD operators align with GD fuel-poor metrics."
                )
    st.subheader("Fuel poor vs minutes lost (scatter — gas distribution)")
    cmap = load_company_mapping_df()
    if not fp.empty and not rel_gas_for_scatter.empty:
        fp_raw = fp[fp["metric_name"] == "fuel_poor_connections_actual"]
        fp_a = (
            fp_raw.assign(
                operator_key=lambda d: apply_canonical_company(d["company_name"], cmap, prefer_sector="GD")
            )
            .groupby("operator_key", as_index=False)["value"]
            .mean()
        )
        rel_a = (
            rel_gas_for_scatter.assign(
                operator_key=lambda d: apply_canonical_company(d["company_name"], cmap, prefer_sector="GD")
            )
            .groupby("operator_key", as_index=False)["minutes_lost"]
            .mean()
        )
        j = fp_a.merge(rel_a, on="operator_key", how="inner")
        j = j.assign(
            value=lambda d: pd.to_numeric(d["value"], errors="coerce"),
            minutes_lost=lambda d: pd.to_numeric(d["minutes_lost"], errors="coerce"),
        )
        if j.empty:
            st.caption(
                "No operators matched after aligning names (fuel poor vs gas CML). "
                "Check selected network companies include GD operators, or relax the company multiselect."
            )
        elif j.dropna(subset=["value", "minutes_lost"]).empty:
            st.caption(
                "Fuel poor and gas-network reliability rows matched by operator, but **minutes lost** and "
                "**gas lost volume** are both null — reload reliability XLSX / run staging→core, "
                "or widen the year range."
            )
        else:
            fig = plots.scatter_with_regression(
                j,
                "value",
                "minutes_lost",
                title="Fuel poor vs CML (gas distribution, canonical operator)",
                x_title="Fuel poor (reported)",
                y_title="Minutes lost or gas lost (GD proxy)",
            )
            st.plotly_chart(fig, use_container_width=True)
    elif not fp.empty and rel_gas_for_scatter.empty:
        st.caption(
            "No gas-distribution reliability rows for this filter — expand Network companies or set Commodity to **gas** "
            "to load GD CML for the scatter."
        )
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
        st.info(
            "No joined satisfaction vs connection-time rows (needs `core_fact_customer_metrics` and "
            "`raw_xlsx_connections`, or raw satisfaction + connections fallback). "
            "Run `python -m pipeline.orchestrate xlsx` then staging/core."
        )
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
            - **Mart-first:** annual renewables %, baseload price, generation HHI, and churn ratio prefer **`mart_market_context`** when refreshed; monthly churn/scatter still uses **`raw_xlsx_market_volumes`** + **`raw_xlsx_market_prices`** (finer grain).
            - **Churn vs volatility** scatter merges monthly churn with electricity baseload volatility (when commodity is **both**, churn defaults to **electricity** to match that volatility series).
            - **HHI fallback:** if the mart has no share snapshot rows, generation HHI falls back to **`core_fact_market_share`** / raw workbook.
            """
        )
    comm = "electricity" if f["commodity"] == "both" else f["commodity"]
    with st.spinner("Loading market & efficiency data…"):
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
        mcc = queries.theme2_market_context_churn_annual(f["y0"], f["y1"], comm)
        if not mcc.empty:
            st.caption(
                "Annual **churn_ratio_avg** (GB, `mart_market_context`) complements the monthly churn scatter above."
            )
    st.subheader("Renewable share vs average baseload price")
    ren_m = queries.theme2_renewable_pct_from_mart(f["y0"], f["y1"])
    pr_m = queries.theme2_power_price_from_mart(f["y0"], f["y1"])
    if not ren_m.empty and not pr_m.empty:
        j = ren_m.merge(pr_m, on="year", how="inner")
        st.caption("Renewable % and baseload price from **`mart_market_context`**.")
    else:
        ren = queries.theme2_renewable_share_annual(f["y0"], f["y1"])
        price = queries.theme2_power_price_annual_avg(f["y0"], f["y1"])
        if ren.empty or price.empty:
            st.info("Need generation context and power prices (refresh `mart_market_context` or core/raw sources).")
            j = pd.DataFrame()
        else:
            j = ren.merge(price, on="year", how="inner")
            st.caption("Renewable % and price from **core / raw** fallback (`mart_market_context` unavailable or incomplete).")
    if not j.empty:
        fig = plots.dual_axis_lines(j, "year", "renewable_pct", "power_gbp_mwh", "Renewable %", "Power £/MWh", "Annual")
        st.plotly_chart(fig, use_container_width=True)
        csv_download(j, "Download CSV", "theme2_renewable_price.csv")
    st.subheader("Spark vs dark spread (quarterly)")
    sd = queries.theme2_spark_dark_quarterly(f["y0"], f["y1"])
    if sd.empty:
        st.info("No quarterly spread data for the selected year range.")
        avail = queries.theme2_metric_year_bounds("spark_spread_central")
        if not avail.empty and int(avail["n"].fillna(0).sum()) > 0:
            r = avail.sort_values("n", ascending=False).iloc[0]
            st.caption(
                f"Spark spread rows exist in `{r['source']}` for years "
                f"{int(r['y_min']) if pd.notna(r['y_min']) else '?'}–{int(r['y_max']) if pd.notna(r['y_max']) else '?'}."
            )
    else:
        fig = plots.bar_grouped(sd, "quarter_start", ["spark_central", "dark_spread"], "£/MWh")
        st.plotly_chart(fig, use_container_width=True)
        csv_download(sd, "Download CSV", "theme2_spark_dark.csv")
    st.subheader("Bid–offer spread heatmap (liquidity stress proxy)")
    info("bid_offer")
    bo = queries.theme2_bid_offer_weekly(f["y0"], f["y1"], comm)
    if bo.empty:
        st.info("No bid_offer_spread in market prices for the selected year range.")
        avail = queries.theme2_metric_year_bounds("bid_offer_spread")
        if not avail.empty and int(avail["n"].fillna(0).sum()) > 0:
            r = avail.sort_values("n", ascending=False).iloc[0]
            st.caption(
                f"`bid_offer_spread` exists in `{r['source']}` for years "
                f"{int(r['y_min']) if pd.notna(r['y_min']) else '?'}–{int(r['y_max']) if pd.notna(r['y_max']) else '?'}."
            )
    else:
        bo = bo.copy()
        bo["week"] = pd.to_datetime(bo["period_date"]).dt.isocalendar().week.astype(str)
        bo["yr"] = bo["year"].astype(str)
        fig = plots.heatmap_calendarish(bo, "week", "yr", "bid_offer_spread", "Bid-offer spread")
        st.plotly_chart(fig, use_container_width=True)
    st.subheader("Market concentration — generation HHI (classic 0–10,000 scale)")
    info("hhi")
    hhi_m = queries.theme2_hhi_from_market_context(f["y0"], f["y1"])
    if not hhi_m.empty:
        hhi = hhi_m[hhi_m["commodity"] == "electricity"][["year", "hhi"]].drop_duplicates()
        hhi_note = "`mart_market_context` share snapshot rows."
    else:
        hhi = queries.theme2_market_share_hhi()
        hhi_note = "`core_fact_market_share` / raw workbook (fallback)."
    if hhi.empty:
        st.info("No market-share concentration rows available.")
        st.caption("`core_fact_market_share` or `mart_market_context` share rows may be empty for this range.")
    else:
        st.caption(f"Source: {hhi_note} — **not** comparable to retail HHI (0–1) on the Supplier health page.")
        fig = plots.bar_grouped(
            hhi, "year", ["hhi"], "Generation HHI (Herfindahl–Hirschman, 0–10,000)"
        )
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
    with st.spinner("Loading reliability & resilience data…"):
        und = queries.theme3_undergrounding(f["y0"], f["y1"])
        cml = queries.theme3_cml_next_year(f["y0"], f["y1"])
    st.subheader("Undergrounding km (Y) vs minutes lost (Y+1)")
    info("cml")
    if und.empty or cml.empty:
        st.info(
            "Need **raw_xlsx_undergrounding** (reload the RIIO-ED1 undergrounding workbook so "
            "`Year N` columns populate multiple calendar years) and **electricity-distribution** "
            "CML in **core_fact_network_reliability**. Re-run `python -m pipeline.orchestrate xlsx` "
            "then staging → core → marts after changing the registry."
        )
    else:
        u = und.groupby(["company_name", "year"], as_index=False)["value"].sum().rename(columns={"value": "km"})
        cml2 = cml.rename(columns={"year": "y_cml", "minutes_lost": "cml"})
        rows_lag = []
        for _, r in u.iterrows():
            m = cml2[(cml2["company_name"] == r["company_name"]) & (cml2["y_cml"] == r["year"] + 1)]
            if not m.empty:
                rows_lag.append({"company_name": r["company_name"], "km": r["km"], "cml": m["cml"].mean()})
        lag_df = pd.DataFrame(rows_lag)
        used_same_year = False
        if lag_df.empty:
            rows_sy = []
            for _, r in u.iterrows():
                m = cml2[(cml2["company_name"] == r["company_name"]) & (cml2["y_cml"] == r["year"])]
                if not m.empty:
                    rows_sy.append({"company_name": r["company_name"], "km": r["km"], "cml": m["cml"].mean()})
            lag_df = pd.DataFrame(rows_sy)
            used_same_year = not lag_df.empty
        if lag_df.empty:
            st.info(
                "No overlapping operator / year pairs between undergrounding and ED CML "
                "(tried **Y+1** then **same-year**). Check **company_mapping.csv** aliases and "
                "that your year range includes ED CML years that match undergrounding years."
            )
        else:
            if used_same_year:
                st.caption(
                    "Using **same calendar year** for km vs CML (no Y+1 overlap found). "
                    "Prefer reloading undergrounding with per-year `Year N` columns for a proper lag chart."
                )
            title = (
                "Undergrounding vs same-year CML"
                if used_same_year
                else "Undergrounding vs next-year CML"
            )
            fig = plots.scatter_with_regression(
                lag_df, "km", "cml", title=title, x_title="km", y_title="Minutes lost"
            )
            st.plotly_chart(fig, use_container_width=True)
            csv_download(lag_df, "Download CSV", "theme3_underground_cml_lag.csv")
    risk = queries.theme3_risk_reduction(f["y0"], f["y1"])
    gas = queries.theme3_gas_lost_by_operator(f["y0"], f["y1"])
    st.subheader("Risk removal vs gas lost volume")
    if risk.empty or gas.empty:
        st.info(
            "Need **raw_xlsx_risk_reduction** (gas distribution RIIO-GD1 risk workbook) and "
            "**gas distribution** `gas_lost_volume` in **core_fact_network_reliability**. "
            "Run the xlsx loader and full staging → core refresh."
        )
    else:
        r_act = risk[risk["metric_name"] == "gas_risk_reduction_actual"]
        if r_act.empty:
            r_act = risk[risk["metric_name"].str.contains("actual", case=False, na=False)]
        if r_act.empty:
            r_act = risk
        r_g = r_act.groupby(["company_name", "year"], as_index=False)["value"].mean().rename(columns={"value": "risk_metric"})
        g_g = gas.groupby(["company_name", "year"], as_index=False)["gas_lost_volume"].mean()
        j = r_g.merge(g_g, on=["company_name", "year"], how="inner")
        gas_latest_fallback = False
        if j.empty and not r_g.empty and not g_g.empty:
            # Risk workbook is a single-period snapshot; gas lost has FY columns that may advance
            # beyond the snapshot stamp — pair each operator's risk with its latest gas year in-range.
            r_by_co = r_g.groupby("company_name", as_index=False)["risk_metric"].mean()
            g_latest = g_g.sort_values("year").groupby("company_name", as_index=False).tail(1)
            j = r_by_co.merge(g_latest, on="company_name", how="inner")
            gas_latest_fallback = not j.empty
        if j.empty:
            st.info(
                "Risk reduction and gas-lost rows exist, but **no matching (company, year)** pairs "
                "after canonical name alignment. Extend **metadata/company_mapping.csv** for GD aliases."
            )
        elif gas_latest_fallback:
            st.caption(
                "Risk metric uses the workbook snapshot period; **gas lost** is the latest fiscal year "
                "available per operator in your filter (aligned by operator name)."
            )
        elif len(j) >= 2:
            from scipy import stats

            try:
                r_s = stats.pearsonr(j["risk_metric"].astype(float), j["gas_lost_volume"].astype(float))
                st.caption(f"Pearson r = {r_s.statistic:.3f}, p = {r_s.pvalue:.3g}")
            except Exception:
                st.caption("Correlation could not be computed (constant series or insufficient variation).")
        if not j.empty:
            fig = plots.bar_grouped(
                j, "company_name", ["risk_metric", "gas_lost_volume"],
                "Risk vs gas lost (scale differs — use table)",
            )
            st.plotly_chart(fig, use_container_width=True)
            csv_download(j, "Download CSV", "theme3_risk_gas.csv")
    st.subheader("SF6 vs ENS vs spend (transmission)")
    info("ens")
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
    st.subheader("Cross-commodity risk (`mart_cross_commodity_risk`)")
    ccr = queries.cross_commodity_risk(f["y0"], f["y1"], None)
    if ccr.empty:
        st.info("No cross-commodity mart rows — refresh materialized views after ETL.")
    else:
        geos = sorted(ccr["geography_name"].dropna().unique().tolist())
        if geos:
            g_pick = st.selectbox("Geography", geos, key="ccr_geography")
            sub = ccr[ccr["geography_name"] == g_pick]
            ccr_label = g_pick
        else:
            sub = ccr
            ccr_label = "all geographies (unfiltered)"
        el = sub[sub["commodity"].astype(str).str.lower() == "electricity"].groupby("year", as_index=False)["ens_mwh"].sum()
        gas = sub[sub["commodity"].astype(str).str.lower() == "gas"].groupby("year", as_index=False)[
            "gas_disruption_volume"
        ].sum()
        j_cc = el.merge(gas, on="year", how="outer", suffixes=("_elec", "_gas")).sort_values("year")
        if len(j_cc) >= 2:
            fig_cc = plots.scatter_with_regression(
                j_cc.dropna(subset=["ens_mwh", "gas_disruption_volume"]),
                "ens_mwh",
                "gas_disruption_volume",
                title=f"Electricity ENS vs gas disruption volume ({ccr_label})",
                x_title="ENS MWh (electricity rows)",
                y_title="Gas disruption volume",
            )
            st.plotly_chart(fig_cc, use_container_width=True)
        line_cols = [c for c in j_cc.columns if c != "year" and j_cc[c].notna().any()]
        if line_cols:
            st.plotly_chart(
                plots.multi_line(j_cc, "year", line_cols, "Reliability / disruption by year"),
                use_container_width=True,
            )
        csv_download(sub, "Download cross-commodity CSV", "theme3_cross_commodity_risk.csv")


def render_theme4(f):
    st.title("Environmental & decarbonisation")
    with st.expander("What this theme shows"):
        st.markdown(
            """
            - **Implied CO2 / MWh** uses **illustrative** static emission factors in `utils.FUEL_CO2_KG_PER_MWH` — not official BEIS factors.
            - **Generation mix** uses quarterly `raw_xlsx_generation_mix` when available.
            """
        )
    with st.spinner("Loading environmental data…"):
        sf6 = queries.theme4_sf6_change_riio_t1()
    if sf6.empty:
        st.subheader("SF6 % change 2014 → 2021 (electricity transmission)")
        st.info(
            "No electricity-transmission SF6 in **core**, **stg_emissions**, or **raw_xlsx_emissions** "
            "for any supported year pair. Load `Sulphur_Hexafluoride_SF6_emissions_Electricity_transmission_RIIO-T1.xlsx` "
            "(RIIO-T1 **Y1→2014** … **Y8→2021**), then run `python -m pipeline.orchestrate xlsx` → **staging** → **core**."
        )
    else:
        yb = int(sf6["baseline_year"].iloc[0])
        yc = int(sf6["compare_year"].iloc[0])
        st.subheader(f"SF6 % change {yb} → {yc} (electricity transmission)")
        if (yb, yc) != (2014, 2021):
            st.caption(
                "Baseline/compare years use the first pair found in your data. For RIIO-T1 SF6 xlsx, "
                "**Y1→2014** and **Y8→2021** (`metadata/riio_periods.yaml` T1); **2013→2021** is only used as a fallback."
            )
        plot_df = sf6.dropna(subset=["pct_change"])
        value_col = "pct_change"
        x_title = "% change SF6"
        if plot_df.empty:
            plot_df = sf6.dropna(subset=["sf6_delta_kg"])
            value_col = "sf6_delta_kg"
            x_title = "Δ SF6 (kg)"
            st.caption(
                "% change is undefined when the baseline SF6 is **zero** or **missing** — showing absolute **Δ kg** instead."
            )
        if plot_df.empty:
            st.info(
                "ET SF6 rows were returned but **both** baseline and compare SF6 are missing per operator "
                "(or Δ kg is undefined). Reload **`Sulphur_Hexafluoride_SF6_emissions_Electricity_transmission_RIIO-T1.xlsx`**, "
                "ensure **`metadata/company_mapping.csv`** maps workbook codes (e.g. **NGET**) to canonical names, "
                "then run **xlsx → staging → core**."
            )
        else:
            fig = plots.bar_horizontal_diverging(plot_df, "company_name", value_col, x_title)
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
    dn = queries.decarbonisation_narrative(f["y0"], f["y1"])
    if not dn.empty:
        st.subheader("National ENS vs LCREE turnover (`mart_decarbonisation_narrative`)")
        note_col = "interpretation_note" if "interpretation_note" in dn.columns else None
        if note_col:
            st.caption(str(dn[note_col].iloc[0]))
        dn_plot = dn.dropna(subset=["year"]).copy()
        if "total_ens_mwh" in dn_plot.columns and "lcree_turnover_million_gbp" in dn_plot.columns:
            dn_plot = dn_plot[
                dn_plot["total_ens_mwh"].notna() | dn_plot["lcree_turnover_million_gbp"].notna()
            ]
        fig_dn = plots.dual_axis_lines(
            dn_plot,
            "year",
            "total_ens_mwh",
            "lcree_turnover_million_gbp",
            "Total ENS (MWh)",
            "LCREE turnover (£m)",
            "Decarbonisation narrative (correlation only)",
        )
        st.plotly_chart(fig_dn, use_container_width=True)
        csv_download(dn, "Download decarbonisation narrative CSV", "theme4_decarbonisation_narrative.csv")


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
    info("rore")
    info("ens")
    with st.spinner("Loading regulatory performance data…"):
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
    top_ind = queries.theme5_economic_impact_top_industries(f["y0"], f["y1"])
    if not top_ind.empty:
        st.subheader("Economic impact: top industries by output at risk (summed over period)")
        st.plotly_chart(
            plots.leaderboard_table(
                top_ind,
                "output_at_risk_gbp",
                "industry_name",
                title="Industry output at risk (£)",
            ),
            use_container_width=True,
        )
        csv_download(top_ind, "Download top industries CSV", "theme5_top_industries.csv")
    st.subheader("Intermediate-consumption share coverage (economic impact rows)")
    detail = queries.mart_economic_impact_detail(f["y0"], f["y1"])
    if detail.empty or "intermediate_consumption_share" not in detail.columns:
        st.info("No intermediate-consumption-share fields available in mart_economic_impact.")
    else:
        cov = (
            detail.groupby("year", as_index=False)
            .agg(
                rows=("year", "size"),
                rows_with_share=("intermediate_consumption_share", lambda s: int(s.notna().sum())),
                avg_share=("intermediate_consumption_share", "mean"),
            )
            .assign(share_coverage_pct=lambda d: 100.0 * d["rows_with_share"] / d["rows"])
        )
        st.plotly_chart(
            plots.dual_axis_lines(
                cov,
                "year",
                "share_coverage_pct",
                "avg_share",
                "Rows with IO share (%)",
                "Average IO share",
                "Input-output enrichment coverage",
            ),
            use_container_width=True,
        )
        csv_download(cov, "Download coverage CSV", "theme5_input_output_coverage.csv")
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


def render_supplier_health(f):
    st.title("Retail: Supplier Financial Health & Concentration")
    info("hhi")
    with st.spinner("Loading supplier health data…"):
        raw = queries_retail.retail_supplier_health(f["y0"], f["y1"], f["supplier_key"])
    df, health_src = queries_retail.coerce_retail_supplier_health_result(raw)
    if health_src == "fallback":
        st.caption("Showing **core-derived fallback** — refresh retail marts when available.")
    if df.empty:
        st.info("No supplier health rows available.")
        status = queries_retail.retail_supplier_health_status()
        if not status.empty:
            missing = status[~status["exists"]]
            if not missing.empty:
                st.caption(
                    "Retail layer is not loaded yet in this database. Missing objects: "
                    + ", ".join(missing["object_name"].tolist())
                )
                st.code(
                    "python -m pipeline.orchestrate xlsx && "
                    "python -m pipeline.orchestrate staging && "
                    "python -m pipeline.orchestrate core && "
                    "python -m pipeline.orchestrate marts",
                    language="bash",
                )
            else:
                st.caption("Retail objects exist but are empty for current filters.")
            st.dataframe(status, use_container_width=True)
        return
    p = (
        df.dropna(subset=["profit_million_gbp", "supplier_name"])
        .drop_duplicates(subset=["year", "supplier_id", "supplier_name"])
        .pivot_table(index="year", columns="supplier_name", values="profit_million_gbp", aggfunc="first")
        .reset_index()
    )
    p_cols = [c for c in p.columns if c != "year"]
    if p_cols:
        st.plotly_chart(plots.multi_line(p, "year", p_cols, "Supplier profits (£m, annual)"), use_container_width=True)
    else:
        st.info("No supplier profit values for the selected filters.")
    h = df[["year", "hhi"]].dropna().drop_duplicates()
    if not h.empty:
        st.plotly_chart(
            plots.bar_grouped(
                h,
                "year",
                ["hhi"],
                "Retail supplier concentration — HHI (normalized 0–1 scale)",
            ),
            use_container_width=True,
        )
        st.caption(
            "HHI is the **mean of electricity and gas** retail market HHIs (from `core_fact_market_share_retail` "
            "shares) — not a single dual-fuel market index. Compare to generation HHI (0–10,000) on **Economic & market**."
        )
    csv_download(df, "Download supplier health CSV", "retail_supplier_health.csv")


def render_consumer_vulnerability(f):
    st.title("Retail: Consumer Debt & Vulnerability")
    pm = f.get("payment_method") or "all"
    st.caption(
        f"**Payment method:** **{pm}** filters `mart_retail_consumer_vulnerability` where the source provides a "
        "payment dimension (national rows). Choose **all** to include every slice. After ETL changes, refresh that mart."
    )
    with st.spinner("Loading consumer vulnerability data…"):
        df = queries_retail.retail_consumer_vulnerability(f["y0"], f["y1"], f["commodity"], pm)
        ds = queries_retail.retail_disconnections_by_supplier(
            f["y0"], f["y1"], f["commodity"], f.get("supplier_key")
        )
        acct = queries_retail.retail_customer_accounts(
            f["y0"], f["y1"], f["commodity"], f.get("supplier_key")
        )
        heat = queries_retail.retail_heating_systems(f["y0"], f["y1"])
    if df.empty:
        st.info(
            "No vulnerability mart rows for this filter — widen the year range, set payment to **all**, or run "
            "**`python -m pipeline.orchestrate marts`** after loading retail workbooks."
        )
    else:
        st.plotly_chart(
            plots.multi_line(
                df,
                "period_start_date",
                ["avg_debt_no_arrangement_gbp", "avg_debt_with_arrangement_gbp"],
                "Average debt levels",
            ),
            use_container_width=True,
        )
        credit_cols = [
            c
            for c in (
                "credit_balance_total_bn_gbp",
                "credit_balance_total_rolling12_bn_gbp",
            )
            if c in df.columns and df[c].notna().any()
        ]
        if credit_cols:
            st.plotly_chart(
                plots.multi_line(
                    df,
                    "period_start_date",
                    credit_cols,
                    "Domestic credit balances — fixed Direct Debit (£ billions, policy measure)",
                ),
                use_container_width=True,
            )
        house_cols = [
            c
            for c in (
                "credit_balance_household_quarter_avg_gbp",
                "credit_balance_household_rolling12_avg_gbp",
            )
            if c in df.columns and df[c].notna().any()
        ]
        if house_cols:
            st.plotly_chart(
                plots.multi_line(
                    df,
                    "period_start_date",
                    house_cols,
                    "Average credit balance per household — fixed DD (£)",
                ),
                use_container_width=True,
            )
        qcols = [
            c
            for c in (
                "credit_balance_quartile_lower_gbp",
                "credit_balance_quartile_median_gbp",
                "credit_balance_quartile_upper_gbp",
            )
            if c in df.columns and df[c].notna().any()
        ]
        if qcols:
            st.plotly_chart(
                plots.multi_line(
                    df,
                    "period_start_date",
                    qcols,
                    "Credit balance quartiles across suppliers (£ per household)",
                ),
                use_container_width=True,
            )
        st.plotly_chart(
            plots.multi_line(
                df,
                "period_start_date",
                ["disconnections_for_debt", "smart_ppm_self_disconnect_events"],
                "Disconnections and self-disconnect events",
            ),
            use_container_width=True,
        )
        csv_download(df, "Download vulnerability CSV", "retail_vulnerability.csv")

    st.subheader("Customer accounts by tariff type (annual)")
    if acct.empty:
        st.caption("No `core_fact_customer_accounts_retail` rows for this range — load retail supplier metrics workbooks.")
    else:
        ap = (
            acct.pivot_table(
                index="year",
                columns="tariff_type",
                values="value",
                aggfunc="sum",
            )
            .reset_index()
            .sort_values("year")
        )
        acols = [c for c in ap.columns if c != "year"]
        if acols:
            st.plotly_chart(
                plots.multi_line(ap, "year", acols, "Domestic customer accounts (annual snapshot)"),
                use_container_width=True,
            )
        csv_download(acct, "Download customer accounts CSV", "retail_customer_accounts.csv")

    st.subheader("Low-carbon heating approvals (RHI-style)")
    if heat.empty:
        st.caption("No `core_fact_heating_systems` rows — load retail workbooks with heating-system metrics.")
    else:
        hy = heat.groupby(["year", "component"], as_index=False)["value"].sum()
        hp = hy.pivot_table(index="year", columns="component", values="value", aggfunc="sum").reset_index().sort_values(
            "year"
        )
        hcols = [c for c in hp.columns if c != "year"]
        if hcols:
            st.plotly_chart(
                plots.multi_line(hp, "year", hcols, "Approved installations (annual sum by technology)"),
                use_container_width=True,
            )
        csv_download(heat, "Download heating systems CSV", "retail_heating_systems.csv")

    st.subheader("Disconnections for debt by supplier")
    if ds.empty:
        st.caption(
            "No per-supplier disconnections in core facts for this filter "
            "(run retail staging/load, or pick suppliers that map in core_dim_supplier)."
        )
    else:
        commodity_note = (
            "electricity and gas combined"
            if f["commodity"] == "both"
            else f["commodity"]
        )
        if f.get("supplier_key"):
            st.caption(
                f"Annual supplier snapshot — **{commodity_note}**. Showing sidebar-selected suppliers."
            )
        else:
            st.caption(
                f"Annual supplier snapshot — **{commodity_note}**. Showing top 15 suppliers "
                "by total disconnections over the year range; use sidebar **Retail suppliers** to focus."
            )
        wide = (
            ds.pivot_table(
                index="year",
                columns="supplier_name",
                values="disconnections_for_debt",
                aggfunc="sum",
            )
            .reset_index()
            .sort_values("year")
        )
        y_cols = [c for c in wide.columns if c != "year"]
        totals = wide[y_cols].sum(numeric_only=True).sort_values(ascending=False)
        wide = wide[["year"] + totals.index.tolist()]
        y_cols_ordered = [c for c in wide.columns if c != "year"]
        st.plotly_chart(
            plots.bar_grouped(
                wide,
                "year",
                y_cols_ordered,
                "Disconnections for debt by supplier (annual snapshot)",
            ),
            use_container_width=True,
        )
        csv_download(ds, "Download supplier disconnections CSV", "retail_disconnections_by_supplier.csv")


def render_competition(f):
    st.title("Retail: Switching & Competition")
    with st.spinner("Loading switching data…"):
        df = queries_retail.retail_competition(f["y0"], f["y1"], f["commodity"])
    if df.empty:
        st.info("No competition rows available.")
        return
    st.plotly_chart(plots.multi_line(df, "period_start_date", ["total_switches", "switches_to_other_suppliers"], "Switching activity"), use_container_width=True)
    st.plotly_chart(plots.multi_line(df, "period_start_date", ["switching_rate_internal_total_pct", "switching_rate_external_total_pct"], "Internal vs external switching"), use_container_width=True)
    csv_download(df, "Download competition CSV", "retail_competition.csv")


def render_affordability(f):
    st.title("Retail: Tariffs, Price Cap & Affordability")
    with st.spinner("Loading affordability data…"):
        df = queries_retail.retail_affordability(f["y0"], f["y1"], f["payment_method"])
    if df.empty:
        st.info("No affordability rows available.")
        return
    tariff = df[df["layer"] == "tariff"]
    cap = df[df["layer"] == "price_cap_component"]
    spend = df[df["layer"] == "household_spend"]
    if not tariff.empty:
        st.plotly_chart(plots.multi_line(tariff, "period_start_date", ["value"], "Tariff benchmarks"), use_container_width=True)
    if not cap.empty:
        st.plotly_chart(plots.multi_line(cap, "period_start_date", ["value"], "Price cap components"), use_container_width=True)
    if not spend.empty:
        st.plotly_chart(plots.bar_grouped(spend, "year", ["value_pct"], "Energy spend as % expenditure"), use_container_width=True)
    csv_download(df, "Download affordability CSV", "retail_affordability.csv")


def render_complaints(f):
    st.title("Retail: Complaints & Customer Service")
    with st.spinner("Loading complaints data…"):
        df = queries_retail.retail_complaints(f["y0"], f["y1"], f["supplier_key"])
    if df.empty:
        st.info("No complaints rows available.")
        return
    p = df.pivot_table(index="period_start_date", columns="metric_name", values="value", aggfunc="mean").reset_index()
    cols = [c for c in p.columns if c != "period_start_date"]
    st.plotly_chart(plots.multi_line(p, "period_start_date", cols, "Complaints KPIs over time"), use_container_width=True)
    csv_download(df, "Download complaints CSV", "retail_complaints.csv")


def render_satisfaction(f):
    st.title("Retail: Satisfaction & Net Promoter Score")
    info("nps")
    with st.spinner("Loading satisfaction data…"):
        df = queries_retail.retail_satisfaction(f["y0"], f["y1"], f["supplier_key"])
    if df.empty:
        st.info("No satisfaction rows available.")
        return
    p = df.pivot_table(index="period_start_date", columns="metric_name", values="value", aggfunc="mean").reset_index()
    cols = [c for c in p.columns if c != "period_start_date"]
    st.plotly_chart(plots.multi_line(p, "period_start_date", cols, "Satisfaction and NPS trends"), use_container_width=True)
    nps = df[df["metric_name"] == "nps_score"][["supplier_name", "value"]].dropna()
    if not nps.empty:
        st.plotly_chart(plots.leaderboard_table(nps, "value", "supplier_name", title="NPS leaderboard"), use_container_width=True)
    csv_download(df, "Download satisfaction CSV", "retail_satisfaction.csv")


def render_cross_layer(f):
    st.title("Cross-layer: Wholesale, Network, and Retail")
    with st.spinner("Loading cross-layer data…"):
        c1 = queries_cross.cross_cost_to_consumer(f["y0"], f["y1"])
        c2 = queries_cross.cross_volatility_complaints(f["y0"], f["y1"])
        c3 = queries_cross.cross_supplier_quality(f["y0"], f["y1"], f["supplier_key"])
    if not c1.empty:
        st.subheader("Cost to consumer attribution")
        if "is_wholesale_low_confidence" in c1.columns and bool(c1["is_wholesale_low_confidence"].fillna(False).any()):
            st.caption(
                "⚠️ `is_wholesale_low_confidence`: missing electricity or gas wholesale observations for some years."
            )
        st.plotly_chart(plots.multi_line(c1, "year", ["wholesale_gbp", "network_gbp", "policy_gbp", "total_cap_gbp"], "Bill component attribution"), use_container_width=True)
        yoy_cols = [c for c in ("wholesale_yoy_change", "network_yoy_change", "policy_yoy_change", "total_yoy_change") if c in c1.columns]
        if yoy_cols:
            st.subheader("Price-cap component year-on-year changes (£)")
            yy = c1[["year"] + yoy_cols].dropna(how="all")
            if not yy.empty:
                st.plotly_chart(plots.multi_line(yy, "year", yoy_cols, "YoY Δ (£)"), use_container_width=True)
        csv_download(c1, "Download attribution CSV", "cross_cost_to_consumer.csv")
    if not c2.empty:
        st.subheader("Volatility vs complaints")
        st.plotly_chart(plots.scatter_with_regression(c2, "spark_spread_avg", "complaints_received_per_100k_avg", title="Spark spread vs complaints", x_title="Spark spread", y_title="Complaints per 100k"), use_container_width=True)
        if {"year", "elec_baseload_volatility", "total_switches"}.issubset(c2.columns):
            vsw = c2[["year", "elec_baseload_volatility", "total_switches"]].dropna(subset=["year"])
            if len(vsw) >= 2:
                st.subheader("Baseload volatility vs switching volume")
                st.plotly_chart(
                    plots.dual_axis_lines(
                        vsw,
                        "year",
                        "elec_baseload_volatility",
                        "total_switches",
                        "Elec. baseload volatility",
                        "Total switches",
                        "Wholesale stress vs retail switching",
                    ),
                    use_container_width=True,
                )
        if "supplier_exits" in c2.columns and c2["supplier_exits"].notna().any():
            st.subheader("Supplier exits (annual)")
            ex = c2[["year", "supplier_exits"]].dropna(subset=["supplier_exits"])
            if not ex.empty:
                st.plotly_chart(plots.line_simple(ex, "year", "supplier_exits", "Supplier exits", "Exits"), use_container_width=True)
        csv_download(c2, "Download volatility/complaints CSV", "cross_volatility_complaints.csv")
    if not c3.empty:
        st.subheader("Supplier quality vs profitability")
        st.plotly_chart(plots.scatter_with_regression(c3, "pretax_domestic_margin_pct", "satisfaction_pct_avg", color_col="supplier_name", title="Profitability vs satisfaction", x_title="Pretax domestic margin %", y_title="Satisfaction %"), use_container_width=True)
        csv_download(c3, "Download supplier quality CSV", "cross_supplier_quality.csv")


def render_daily_market(f):
    st.title("Daily market monitoring")
    st.caption("Separate high-frequency module for gas SAP and electricity system price.")
    with st.spinner("Loading daily market monitoring data…"):
        summary = queries.theme2_daily_market_monitoring(f["y0"], f["y1"], f["commodity"])
        daily = queries.theme2_daily_price_series(f["y0"], f["y1"], f["commodity"])
    if summary.empty and daily.empty:
        st.info("No daily market module data found. Load `core_fact_daily_prices` and refresh `mart_daily_market_monitoring`.")
        return

    if not daily.empty:
        st.subheader("Daily price series")
        series = (
            daily.assign(series=lambda d: d["commodity"] + ":" + d["source_name"] + ":" + d["metric_name"])
            .pivot_table(index="period_date", columns="series", values="value", aggfunc="mean")
            .reset_index()
        )
        cols = [c for c in series.columns if c != "period_date"]
        if cols:
            st.plotly_chart(plots.multi_line(series, "period_date", cols, "Daily market prices"), use_container_width=True)
        csv_download(daily, "Download daily prices CSV", "daily_market_prices.csv")

    if not summary.empty:
        st.subheader("Volatility and spike summary")
        s = summary.copy()
        s["series"] = s["commodity"] + ":" + s["source_name"] + ":" + s["metric_name"]
        piv = s.pivot_table(index="year", columns="series", values="volatility_stddev", aggfunc="mean").reset_index()
        val_cols = [c for c in piv.columns if c != "year"]
        if val_cols:
            st.plotly_chart(plots.multi_line(piv, "year", val_cols, "Annual volatility (stddev)"), use_container_width=True)
        st.dataframe(
            s[["year", "commodity", "source_name", "metric_name", "observation_count", "volatility_stddev", "spike_days_ge_p95"]]
            .sort_values(["year", "commodity", "source_name", "metric_name"]),
            use_container_width=True,
        )
        csv_download(summary, "Download summary CSV", "daily_market_monitoring_summary.csv")


def _render_dukes_staging_explorer(
    f: dict,
    staging_key: str,
    doc_title: str,
    doc_url: str,
    *,
    cache_slug: str,
) -> None:
    """Long-format DUKES staging: picker, table, top-N multi-line chart, CSV."""
    sk = staging_key  # ch4 | ch5 | ch1_sup
    rel = qdc.staging_relation_name(sk)  # type: ignore[arg-type]
    st.markdown(
        f"Official DESNZ statistics — [{doc_title}]({doc_url}). "
        f"Ingest populates **`{rel}`** — run **`python -m pipeline.orchestrate ingest`** "
        "(or **`full_refresh`**, which includes ingest). Macro validation only — not merged "
        "with RIIO network facts."
    )
    if not qdc.staging_table_exists(sk):  # type: ignore[arg-type]
        st.info(
            f"Relation **`{rel}`** is not in the database. Run **`python -m pipeline.orchestrate ingest`** "
            "or **`full_refresh`** — `ingest_dukes` applies the staging DDL then downloads and parses workbooks."
        )
        return

    dist = qdc.dukes_staging_distinct_tables(sk)  # type: ignore[arg-type]
    if dist.empty:
        st.info(
            f"No rows in **`{rel}`** yet. Run **`python -m pipeline.orchestrate ingest`** or **`full_refresh`**. "
            "If it still stays empty, check **`metadata/dukes_registry.yaml`** and that DESNZ downloads succeed "
            "(network / workbook layout changes)."
        )
        return

    tids = dist["dukes_table"].dropna().astype(str).tolist()
    pick = st.selectbox(
        "DUKES table id (`dukes_table`)",
        tids,
        key=f"dukes_stg_{cache_slug}_tid",
    )

    mdf = qdc.dukes_staging_distinct_metrics(sk, pick)  # type: ignore[arg-type]
    mlist = mdf["metric_name"].dropna().astype(str).tolist() if not mdf.empty else []
    metric_pick = st.selectbox(
        "Metric filter (optional)",
        ["(all metrics)"] + mlist,
        key=f"dukes_stg_{cache_slug}_metric",
    )
    metric_arg = None if metric_pick == "(all metrics)" else metric_pick

    top_n = st.slider(
        "Max series on chart (by mean |value|)",
        3,
        36,
        12,
        key=f"dukes_stg_{cache_slug}_topn",
        help="Limits plotted lines; full data remains in the table and CSV.",
    )

    with st.spinner("Loading staging rows…"):
        long_df = qdc.dukes_staging_long(f["y0"], f["y1"], sk, pick, metric_arg)  # type: ignore[arg-type]

    if long_df.empty:
        st.info("No rows for this table, metric filter, and sidebar year range.")
        return

    preview_h = min(420, 28 * min(24, len(long_df)))
    st.dataframe(long_df, use_container_width=True, height=preview_h)

    chart_df = long_df[
        long_df["period_year"].notna() & long_df["value"].notna()
    ].copy()
    if chart_df.empty:
        st.caption(
            "No year-indexed numeric rows in this slice (e.g. only cumulative NULL-year or text attributes)."
        )
    else:

        def _series_key(r: pd.Series) -> str:
            rl = str(r.get("row_label") or "").strip()
            cl = r.get("column_label")
            if cl is not None and pd.notna(cl) and str(cl).strip():
                s = f"{rl} | {str(cl).strip()}"
            else:
                s = rl if rl else "_series"
            return s[:220]

        chart_df["_series"] = chart_df.apply(_series_key, axis=1)
        strength = chart_df.groupby("_series")["value"].apply(lambda s: float(s.abs().mean()))
        strength = strength.sort_values(ascending=False).head(top_n)
        keep = set(strength.index.tolist())
        sub = chart_df[chart_df["_series"].isin(keep)]
        wide = sub.pivot_table(index="period_year", columns="_series", values="value", aggfunc="first")
        wide = wide.sort_index().reset_index()
        val_cols = [c for c in wide.columns if c != "period_year"]
        st.caption(
            f"Chart shows up to **{top_n}** series by mean |value| (fewer if sparse). "
            f"Plotted: **{len(val_cols)}**."
        )
        if val_cols:
            st.plotly_chart(
                plots.multi_line(wide, "period_year", val_cols, f"{pick} — selected series"),
                use_container_width=True,
            )

    safe_pick = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(pick))[:48]
    csv_download(long_df, "Download filtered staging CSV", f"dukes_{cache_slug}_{safe_pick}.csv")


def _render_dukes_primary_gdp_section(pg: pd.DataFrame) -> None:
    st.subheader("Primary energy, GDP, and energy ratio (Table 1.1.4)")
    st.plotly_chart(
        plots.dual_axis_lines(
            pg,
            "year",
            "energy_ratio",
            "gdp_gbp_billion",
            "Energy ratio (index varies — see DUKES notes)",
            "GDP (£ billion, chained volume 2022)",
            "Macro decoupling lens",
        ),
        use_container_width=True,
    )
    csv_download(pg, "Download Table 1.1.4 CSV", "dukes_primary_gdp_ratio.csv")


def render_dukes_macro(f):
    st.title("DUKES macro context")
    st.markdown(
        "National statistics from DESNZ **Digest of UK Energy Statistics** "
        "([Chapter 1 — Energy](https://www.gov.uk/government/statistics/energy-chapter-1-digest-of-united-kingdom-energy-statistics-dukes), "
        "[Chapter 4 — Natural gas](https://www.gov.uk/government/statistics/natural-gas-chapter-4-digest-of-united-kingdom-energy-statistics-dukes), "
        "[Chapter 5 — Electricity](https://www.gov.uk/government/statistics/electricity-chapter-5-digest-of-united-kingdom-energy-statistics-dukes)). "
        "`ingest_dukes` downloads workbooks into `raw/<dukes_dir>/` and fills **`stg_dukes_*`** (core tables, Chapter 1 supplementary, Chapter 4 & 5 long-format staging). "
        "Macro validation only — not merged with RIIO network facts."
    )

    tab_core, tab_gas, tab_elec, tab_sup = st.tabs(
        [
            "Chapter 1 — core tables",
            "Natural gas (Chapter 4)",
            "Electricity (Chapter 5)",
            "Chapter 1 — supplementary (long)",
        ]
    )

    with tab_core:
        with st.spinner("Loading DUKES Chapter 1 staging tables…"):
            pg = queries.dukes_primary_gdp_ratio(f["y0"], f["y1"])
            ex = queries.dukes_expenditure_by_sector(f["y0"], f["y1"])
            fc = queries.dukes_final_consumption_long(f["y0"], f["y1"], "all")
            fuels = queries.dukes_primary_fuels_mtoe(f["y0"], f["y1"])
            net_cost = queries.dukes_network_cost_proxy(f["y0"], f["y1"])

        if pg.empty and ex.empty and fc.empty and fuels.empty:
            st.info(
                "No Chapter 1 core `stg_dukes_*` rows. Run **`python -m pipeline.orchestrate ingest`** or **`full_refresh`** "
                "so `ingest_dukes` can populate **`stg_dukes_primary_consumption`**, **`stg_dukes_energy_expenditure`**, "
                "**`stg_dukes_final_consumption`**, and **`stg_dukes_primary_fuels`**."
            )

        if not pg.empty:
            _render_dukes_primary_gdp_section(pg)

        if not ex.empty:
            st.subheader("Expenditure on energy by final user (Table 1.1.6, £ million)")
            piv = ex.pivot_table(
                index="year", columns="sector", values="expenditure_million_gbp", aggfunc="first"
            ).reset_index()
            val_cols = [c for c in piv.columns if c != "year"]
            if val_cols:
                st.plotly_chart(
                    plots.multi_line(piv, "year", val_cols, "Expenditure by sector (£m)"),
                    use_container_width=True,
                )
            csv_download(ex, "Download Table 1.1.6 CSV", "dukes_expenditure.csv")

        if not fuels.empty:
            st.subheader("Primary fuels mix (Table 1.1.1.B, Mtoe)")
            short = fuels[~fuels["fuel_type"].str.contains("Total", case=False, na=False)].copy()
            top_fuels = (
                short.groupby("fuel_type")["consumption_mtoe"]
                .mean()
                .sort_values(ascending=False)
                .head(8)
                .index.tolist()
            )
            plot_df = short[short["fuel_type"].isin(top_fuels)]
            wide = plot_df.pivot_table(index="year", columns="fuel_type", values="consumption_mtoe", aggfunc="first")
            wide = wide.reset_index()
            cols = [c for c in wide.columns if c != "year"]
            if cols:
                st.plotly_chart(plots.multi_line(wide, "year", cols, "Selected fuels (Mtoe)"), use_container_width=True)
            csv_download(fuels, "Download Table 1.1.1.B CSV", "dukes_primary_fuels.csv")

        sectors_fc = sorted(fc["sector"].dropna().unique().tolist()) if not fc.empty else []
        pick = st.selectbox("Final consumption sector (Table 1.1.5)", ["all"] + sectors_fc, index=0)
        fc2 = queries.dukes_final_consumption_long(f["y0"], f["y1"], pick if pick != "all" else "all")
        if not fc2.empty and pick != "all":
            st.subheader(f"Energy by fuel — {pick} (ktoe)")
            wide_fc = fc2.pivot_table(index="year", columns="fuel_type", values="energy_ktoe", aggfunc="first").reset_index()
            cols_fc = [c for c in wide_fc.columns if c != "year"]
            if cols_fc[:15]:
                st.plotly_chart(
                    plots.multi_line(wide_fc, "year", cols_fc[:15], "Consumption by fuel (ktoe)"),
                    use_container_width=True,
                )
            csv_download(fc2, "Download Table 1.1.5 CSV", "dukes_final_consumption.csv")

        if not pg.empty and not net_cost.empty:
            st.subheader("Macro validation: DUKES energy ratio vs average network cost per customer")
            st.caption(
                "Overlay is illustrative — DUKES ratio is economy-wide; network costs are one bill component from Ofgem estimated-cost workbooks."
            )
            j = pg.merge(net_cost, on="year", how="inner")
            if not j.empty:
                j["avg_network_gbp"] = j[
                    ["elec_tx_avg_gbp", "elec_dx_avg_gbp", "gas_tx_avg_gbp", "gas_dx_avg_gbp"]
                ].mean(axis=1, skipna=True)
                fig = plots.scatter_with_regression(
                    j.dropna(subset=["energy_ratio", "avg_network_gbp"]),
                    "energy_ratio",
                    "avg_network_gbp",
                    title="Energy ratio vs average GB network cost proxy",
                    x_title="DUKES energy ratio",
                    y_title="Mean network cost (£/customer-year)",
                )
                st.plotly_chart(fig, use_container_width=True)
                csv_download(j, "Download overlay CSV", "dukes_overlay_network_cost.csv")

    with tab_gas:
        _render_dukes_staging_explorer(
            f,
            "ch4",
            "Digest of UK Energy Statistics — natural gas (Chapter 4)",
            "https://www.gov.uk/government/statistics/natural-gas-chapter-4-digest-of-united-kingdom-energy-statistics-dukes",
            cache_slug="ch4",
        )

    with tab_elec:
        _render_dukes_staging_explorer(
            f,
            "ch5",
            "Digest of UK Energy Statistics — electricity (Chapter 5)",
            "https://www.gov.uk/government/statistics/electricity-chapter-5-digest-of-united-kingdom-energy-statistics-dukes",
            cache_slug="ch5",
        )

    with tab_sup:
        _render_dukes_staging_explorer(
            f,
            "ch1_sup",
            "Digest of UK Energy Statistics — Chapter 1 (supplementary tables)",
            "https://www.gov.uk/government/statistics/energy-chapter-1-digest-of-united-kingdom-energy-statistics-dukes",
            cache_slug="ch1_sup",
        )


def render_pefa(f):
    st.title("ONS physical energy flow accounts (PEFA)")
    st.markdown(
        "National physical energy flows from ONS "
        "[Physical energy flow accounts]"
        "(https://www.ons.gov.uk/economy/environmentalaccounts/datasets/physicalenergyflowaccountspefa) "
        "loaded into `stg_pefa_matrix` (Tables A–D) and `stg_pefa_bridge` (Table E). Units are terajoules (TJ)."
    )
    with st.spinner("Loading PEFA staging tables…"):
        br = queries.pefa_bridge(f["y0"], f["y1"])
        td = queries.pefa_table_d_indicators_au(f["y0"], f["y1"])
        sup = queries.pefa_physical_supply_au(f["y0"], f["y1"], limit=40)

    if br.empty and td.empty and sup.empty:
        st.info(
            "No PEFA data in the database. Run `python -m pipeline.orchestrate ingest` or `full_refresh` "
            "so `load_pefa` can download the workbook into `raw/pefa/` and populate `stg_pefa_*` "
            "(see `metadata/pefa_registry.yaml`)."
        )
        return

    if not br.empty:
        st.subheader("Bridge — residence vs territory (Table E)")
        yrs = sorted(br["reference_year"].dropna().unique().tolist())
        pick_y = st.selectbox("Reference year (bridge)", yrs, index=len(yrs) - 1, key="pefa_bridge_year")
        b1 = br[br["reference_year"] == pick_y].copy()
        if not b1.empty:
            fig_br = plots.bar_horizontal_diverging(
                b1,
                "bridge_code",
                "energy_tj",
                title=f"Bridge indicators (TJ), {pick_y}",
            )
            st.plotly_chart(fig_br, use_container_width=True)
            csv_download(b1, "Download bridge CSV", "pefa_bridge.csv")

    if not td.empty:
        st.subheader("Key vectors — economy total column A_U (Table D)")
        yrs_td = sorted(td["reference_year"].dropna().unique().tolist())
        pick_td = st.selectbox("Reference year (Table D)", yrs_td, index=len(yrs_td) - 1, key="pefa_td_year")
        td1 = td[td["reference_year"] == pick_td].sort_values("row_no")
        td_plot = td1.assign(
            _lbl=lambda d: d["row_code"].astype(str)
            + " — "
            + d["row_label"].fillna("").astype(str).str.slice(0, 48)
        )
        st.plotly_chart(
            plots.bar_horizontal_diverging(
                td_plot,
                "_lbl",
                "energy_tj",
                title=f"Table D indicators (A_U), {pick_td}",
            ),
            use_container_width=True,
        )
        csv_download(td, "Download Table D (A_U) CSV", "pefa_table_d_au.csv")

    if not sup.empty:
        st.subheader(
            f"Physical supply — largest product rows at A_U (Table A, year range {f['y0']}–{f['y1']}, top {len(sup)} by TJ)"
        )
        sup_plot = sup.assign(
            _lbl=lambda d: d["row_code"].astype(str)
            + " "
            + d["row_label"].fillna("").astype(str).str.slice(0, 52)
        )
        st.plotly_chart(
            plots.bar_horizontal_diverging(
                sup_plot,
                "_lbl",
                "energy_tj",
                title=f"Table A — physical supply (A_U), {f['y0']}–{f['y1']}",
            ),
            use_container_width=True,
        )
        csv_download(sup, "Download Table A sample CSV", "pefa_table_a_au_top.csv")


def render_methodology():
    st.title("Methodology & data lineage")
    st.markdown(
        """
### Sources
- **DUKES Chapter 1** (DESNZ) workbooks are listed in `metadata/dukes_registry.yaml`, downloaded to `raw/{dukes_dir}/`, and parsed into `stg_dukes_*` by `pipeline/ingest/ingest_dukes.py` during `ingest`.
- **ONS PEFA** (physical energy flow accounts) workbooks are listed in `metadata/pefa_registry.yaml`, downloaded to `raw/pefa/` (or `paths.pefa_dir` in settings), and parsed into `stg_pefa_*` by `pipeline/ingest/ingest_pefa.py` during `ingest`.
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
REFRESH MATERIALIZED VIEW mart_daily_market_monitoring;
REFRESH MATERIALIZED VIEW mart_scheme_metric;
```

### Dashboard layout
- Navigation and all pages are defined in **`dashboard/app.py`** (there is no separate `dashboard/pages/` package).
- **Policy scheme metrics** reads **`mart_scheme_metric`** (ECO, BUS, RHI, admin queues) when ingested.

### Limits & caveats
- Network reliability facts are keyed at **GB** geography in the reference load — regional maps for ENS are not available without extra staging.
- Some charts read **`raw_xlsx_*` directly** because metrics are not promoted to core.
- **Implied CO2** uses static illustrative factors — do not use for compliance reporting.
- Retail xlsx files are ingested from **`data/ofgem_data_portal_xlsx_facet_1609_supply_retail/`** via the same registry loader.
- Smart self-disconnection metrics cover **smart prepayment meters only** and begin from **Q2 2022**.
- Supplier names are canonicalised with **`metadata/supplier_mapping.csv`** before loading `core_dim_supplier`.
- `Likelihood_to_recommend_*` files are supplier-size segment metrics (large/medium/small), not supplier-level metrics.

### Connection
Set `DATABASE_URL` (see `.env.example`). This app uses **SQLAlchemy** with bound parameters only.
        """
    )


def render_forecasting(f):
    st.title("Forecasting (bonus)")
    st.warning("Low confidence: short annual series are noisy; use for exploration only.")
    with st.spinner("Loading forecast inputs…"):
        mr = queries.theme5_mart_regulatory(f["y0"], f["y1"], None)
    if mr.empty:
        st.info("Need mart_regulatory_performance.")
        return
    companies = sorted(mr["company_name"].dropna().unique().tolist())
    pick = st.selectbox("Operator", companies)
    s = queries.forecast_ens_annual(f["y0"], f["y1"], pick)
    metric_used = "ens_mwh"
    if not s.empty and "metric_name" in s.columns and not s["metric_name"].dropna().empty:
        metric_used = str(s["metric_name"].dropna().iloc[0])
    if metric_used == "gas_lost_volume_proxy":
        info("gas_lost_proxy")
        st.caption("Using `gas_lost_volume` as the series because ENS is unavailable for this operator.")
    else:
        info("ens")
    if len(s) < 3:
        st.info("Not enough annual data points to fit a trend (need at least three years with values).")
        if not s.empty:
            st.dataframe(s, use_container_width=True)
        return
    import numpy as np
    from sklearn.linear_model import LinearRegression

    value_col = "Gas lost volume (proxy)" if metric_used == "gas_lost_volume_proxy" else "ENS (MWh)"
    x = s["year"].values.reshape(-1, 1)
    y = s["ens_mwh"].fillna(0).values
    model = LinearRegression().fit(x, y)
    future_years = np.arange(f["y1"] + 1, f["y1"] + 4).reshape(-1, 1)
    pred = model.predict(future_years)
    st.line_chart(
        pd.DataFrame(
            {
                "year": list(s["year"]) + list(future_years.flatten()),
                value_col: list(y) + list(pred),
            }
        ).set_index("year")
    )
    if metric_used == "gas_lost_volume_proxy":
        st.caption(
            f"Linear trend slope {model.coef_[0]:.3f} per year, intercept {model.intercept_:.2f} "
            f"({value_col} — same units as Ofgem source, not MWh ENS)"
        )
    else:
        st.caption(f"Linear trend slope {model.coef_[0]:.2f} MWh/year, intercept {model.intercept_:.2f} ({value_col})")
    csv_download(s, "Download history CSV", "forecast_ens_history.csv")


def render_whatif(f):
    st.title("What-if: network cost shock on output at risk (bonus)")
    st.warning("The mart applies a structured model — scaling is a **scenario illustration**, not a forecast.")
    with st.spinner("Loading economic impact detail…"):
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


def render_incidents(f):
    st.title("Retail: Major & Minor Incidents")
    st.caption(
        "Snapshot incident counts per supplier from Ofgem's retail facet — "
        "`Major_incidents.xlsx` and `Minor_incidents.xlsx`. Drop the workbooks into "
        "`data/ofgem_data_portal_xlsx_facet_1609_supply_retail/` and rerun the "
        "xlsx + staging stages to populate."
    )
    with st.spinner("Loading incidents data…"):
        df = queries_retail.retail_incidents(f["y0"], f["y1"], f["supplier_key"])
    if df.empty:
        st.info(
            "No incident rows in `mart_retail_complaints` for the selected filters. "
            "Verify the snapshot files have been ingested and the materialized view refreshed."
        )
        return

    metric_cols = [
        c for c in (
            "minor_incidents_historical", "minor_incidents_current",
            "major_incidents_historical", "major_incidents_current",
        ) if c in df.columns
    ]

    st.subheader("Per-supplier snapshot (latest year in range)")
    latest_year = int(df["year"].dropna().max()) if df["year"].notna().any() else None
    if latest_year is not None:
        snap = df[df["year"] == latest_year].dropna(subset=metric_cols, how="all")
        if not snap.empty:
            st.plotly_chart(
                plots.bar_grouped(
                    snap.sort_values("supplier_name"),
                    "supplier_name",
                    metric_cols,
                    f"Incidents per supplier ({latest_year} snapshot)",
                ),
                use_container_width=True,
            )

    st.subheader("All snapshot rows")
    st.dataframe(df, use_container_width=True)
    csv_download(df, "Download incidents CSV", "retail_incidents.csv")


def render_renewables(f):
    st.title("Networks: Renewables deployment (MCS-style)")
    st.caption(
        "Annual cumulative capacity, quarterly net additions, and regional shares from "
        "MCS-style workbooks. Drop the source files into `data/renewables_mcs/`, then run "
        "`xlsx` and `marts` (marts includes staging) or `full_refresh` to populate."
    )
    with st.spinner("Loading annual renewables data…"):
        annual = queries_renewables.renewables_annual(f["y0"], f["y1"])

    if annual.empty:
        st.info(
            "No **mart_renewables_deployment** rows yet. Copy the MCS-style `.xlsx` "
            "files into **`data/renewables_mcs/`** (exact filenames are listed in "
            "`data/renewables_mcs/README.txt`), then run **`python -m pipeline.orchestrate "
            "full_refresh`**, or **`xlsx`** then **`marts`** (staging runs automatically "
            "before marts)."
        )
    else:
        st.subheader("Cumulative capacity (kW) by technology")
        wide = annual.pivot_table(
            index="year", columns="technology", values="cumulative_capacity_kw", aggfunc="max"
        ).reset_index()
        st.plotly_chart(
            plots.multi_line(
                wide, "year", [c for c in wide.columns if c != "year"],
                "Cumulative TIC by technology (kW)",
            ),
            use_container_width=True,
        )
        st.subheader("Annual installations added by technology")
        st.plotly_chart(
            plots.stacked_area_from_long(
                annual, "year", "technology", "installations",
                "Installations per year (count)",
            ),
            use_container_width=True,
        )
        csv_download(annual, "Download annual renewables CSV", "renewables_annual.csv")

    with st.spinner("Loading Renewables Obligation (portal) …"):
        ro = queries_renewables.renew_obligation_by_technology()
    if not ro.empty:
        st.subheader("Renewables Obligation — ROCs issued vs accredited capacity (Ofgem portal)")
        st.caption(
            "Sourced from everviz extracts (`portal_sync`). ROCs are in millions per obligation year; "
            "capacity is MW accredited in-period."
        )
        roc_wide = ro.pivot_table(
            index="obligation_period",
            columns="technology",
            values="rocs_issued_millions",
            aggfunc="first",
        ).reset_index()
        rcols = [c for c in roc_wide.columns if c != "obligation_period"]
        if rcols:
            st.plotly_chart(
                plots.multi_line(
                    roc_wide,
                    "obligation_period",
                    rcols,
                    "ROCs issued by technology (millions per obligation period)",
                ),
                use_container_width=True,
            )
        cap = ro.dropna(subset=["accredited_capacity_mw"])
        if not cap.empty:
            cap_wide = cap.pivot_table(
                index="obligation_period",
                columns="technology",
                values="accredited_capacity_mw",
                aggfunc="first",
            ).reset_index()
            ccols = [c for c in cap_wide.columns if c != "obligation_period"]
            if ccols:
                st.plotly_chart(
                    plots.multi_line(
                        cap_wide,
                        "obligation_period",
                        ccols,
                        "Accredited capacity by technology (MW)",
                    ),
                    use_container_width=True,
                )
        csv_download(ro, "Download RO obligation mart CSV", "renewables_obligation.csv")

    with st.spinner("Loading quarterly renewables data…"):
        qtr = queries_renewables.renewables_quarterly(f["y0"], f["y1"])
    if not qtr.empty:
        st.subheader("Quarterly net additions (capacity_kw)")
        st.plotly_chart(
            plots.stacked_area_from_long(
                qtr.assign(period=lambda d: d["period_date"].fillna(
                    pd.to_datetime(d["year"].astype(str) + "-" + (d["quarter"] * 3).astype(str) + "-01",
                                   errors="coerce")
                )),
                "period", "technology", "capacity_kw_quarter",
                "Quarterly capacity additions",
            ),
            use_container_width=True,
        )
        csv_download(qtr, "Download quarterly renewables CSV", "renewables_quarterly.csv")

    with st.spinner("Loading regional renewables data…"):
        reg = queries_renewables.renewables_regional(f["y0"], f["y1"])
    if not reg.empty:
        st.subheader("Regional share of installations / TIC (latest year in range)")
        latest = int(reg["year"].dropna().max()) if reg["year"].notna().any() else None
        if latest is not None:
            snap = reg[reg["year"] == latest]
            value_col = "share_pct" if snap["share_pct"].notna().any() else "capacity_kw"
            st.plotly_chart(
                plots.bar_grouped(
                    snap.pivot_table(index="region", columns="technology", values=value_col, aggfunc="sum")
                        .reset_index(),
                    "region",
                    [c for c in snap["technology"].dropna().unique().tolist()],
                    f"Regional {value_col} by technology ({latest})",
                ),
                use_container_width=True,
            )
        csv_download(reg, "Download regional renewables CSV", "renewables_regional.csv")

    st.markdown("---")
    st.subheader("Official DUKES renewables (Chapter 6)")
    st.caption(
        "National statistics from DESNZ "
        "[Digest of UK Energy Statistics — renewable sources of energy]"
        "(https://www.gov.uk/government/statistics/renewable-sources-of-energy-chapter-6-digest-of-united-kingdom-energy-statistics-dukes). "
        "Populated by **`python -m pipeline.orchestrate ingest`** into **`stg_dukes_chapter6`** and mart **`mart_dukes_official_renewables`** "
        "(refresh marts after ingest)."
    )
    with st.spinner("Loading DUKES 6.2 generation…"):
        gwh = queries_renewables.dukes_official_chapter6_generation_gwh(f["y0"], f["y1"])
    if not gwh.empty:
        pick = {
            "Total generation",
            "Wind:",
            "Onshore",
            "Offshore Wind",
            "Solar photovoltaics",
            "Hydro:",
        }
        plot_df = gwh[gwh["technology"].isin(pick)]
        if not plot_df.empty:
            wide = plot_df.pivot_table(
                index="year", columns="technology", values="value", aggfunc="first"
            ).reset_index()
            cols = [c for c in wide.columns if c != "year"]
            st.plotly_chart(
                plots.multi_line(wide, "year", cols, "Electricity generation from renewables (GWh)"),
                use_container_width=True,
            )
            csv_download(plot_df, "Download DUKES 6.2 generation CSV", "dukes_6_2_generation_gwh.csv")

    with st.spinner("Loading DUKES 6.3 load factors…"):
        lf = queries_renewables.dukes_official_chapter6_load_factors(f["y0"], f["y1"])
    if not lf.empty:
        want = {"Wind", "Onshore", "Offshore", "Solar photovoltaics", "Hydro", "Offshore Wind"}
        lf2 = lf[lf["technology"].isin(want)]
        if not lf2.empty:
            wide_lf = lf2.pivot_table(
                index="year", columns="technology", values="value", aggfunc="first"
            ).reset_index()
            lc = [c for c in wide_lf.columns if c != "year"]
            st.plotly_chart(
                plots.multi_line(wide_lf, "year", lc, "Load factors (% of capacity)"),
                use_container_width=True,
            )
            csv_download(lf2, "Download DUKES 6.3 load factors CSV", "dukes_6_3_load_factors.csv")

    with st.spinner("Loading DUKES 6.5 renewable share of electricity GFC…"):
        sh = queries_renewables.dukes_official_chapter6_electricity_renewable_share(f["y0"], f["y1"])
    if not sh.empty:
        st.plotly_chart(
            plots.line_simple(
                sh.sort_values("year"),
                "year",
                "renewable_share_of_gfc_electricity",
                "Renewable share of gross final electricity consumption (proportion)",
            ),
            use_container_width=True,
        )
        csv_download(sh, "Download DUKES 6.5 electricity renewable share CSV", "dukes_6_5_elec_share.csv")
    if gwh.empty and lf.empty and sh.empty:
        st.info(
            "No **mart_dukes_official_renewables** rows yet. Run **`python -m pipeline.orchestrate ingest`** "
            "to fetch Chapter 6 workbooks, then **`python -m pipeline.orchestrate marts`** to refresh the mart."
        )


def render_warm_home_discount(f):
    st.title("Retail: Warm Home Discount (WHD)")
    st.caption(
        "Scheme-year level series from the WHD workbooks (England & Wales / Scotland "
        "expenditure shares, scheme value since 2002, supplier obligation methods, and "
        "redistribution). Drop the workbooks into `data/whd/`, then run `xlsx` and `marts` "
        "(marts includes staging) or `full_refresh`."
    )
    with st.spinner("Loading WHD national series…"):
        nat = queries_whd.whd_national(f["y0"], f["y1"])

    if nat.empty:
        st.info(
            "No **mart_warm_home_discount** rows yet. Copy the WHD `.xlsx` files into "
            "**`data/whd/`** (exact filenames are listed in `data/whd/README.txt`), then "
            "run **`python -m pipeline.orchestrate full_refresh`**, or **`xlsx`** then "
            "**`marts`** (staging runs automatically before marts)."
        )
    else:
        st.subheader("Distribution of expenditure by year (%) — by nation")
        exp = nat.dropna(subset=["expenditure_pct"])[["calendar_year", "nation", "expenditure_pct"]]
        if not exp.empty:
            st.plotly_chart(
                plots.stacked_area_from_long(
                    exp, "calendar_year", "nation", "expenditure_pct",
                    "WHD expenditure share (%) by nation",
                ),
                use_container_width=True,
            )
        sv = nat.dropna(subset=["scheme_value_mgbp"])[["calendar_year", "scheme_value_mgbp"]]
        if not sv.empty:
            st.subheader("Total scheme value since 2002 (£m)")
            st.plotly_chart(
                plots.line_simple(
                    sv.sort_values("calendar_year"),
                    "calendar_year", "scheme_value_mgbp",
                    "WHD scheme value (£m)",
                ),
                use_container_width=True,
            )
        csv_download(nat, "Download WHD national CSV", "whd_national.csv")

    with st.spinner("Loading WHD supplier rows…"):
        sup = queries_whd.whd_supplier(f["y0"], f["y1"], f["supplier_key"])
    if not sup.empty:
        st.subheader("Supplier obligation amounts by method")
        oa = sup.dropna(subset=["obligation_amount_mgbp"])
        if not oa.empty:
            st.plotly_chart(
                plots.bar_grouped(
                    oa.pivot_table(
                        index="supplier_name", columns="obligation_method",
                        values="obligation_amount_mgbp", aggfunc="sum",
                    ).reset_index(),
                    "supplier_name",
                    [c for c in oa["obligation_method"].dropna().unique().tolist()],
                    "Obligation amount (£m) by supplier and method",
                ),
                use_container_width=True,
            )
        rd = sup.dropna(subset=["redistributed_mgbp"])
        if not rd.empty:
            st.subheader("Funds redistributed to suppliers (£m)")
            st.plotly_chart(
                plots.bar_horizontal_diverging(
                    rd.groupby("supplier_name", as_index=False)["redistributed_mgbp"].sum()
                      .sort_values("redistributed_mgbp"),
                    "supplier_name", "redistributed_mgbp",
                    "Cumulative redistribution by supplier",
                ),
                use_container_width=True,
            )
        csv_download(sup, "Download WHD supplier CSV", "whd_supplier.csv")


def render_scheme_metrics(f):
    st.title("Retail: Policy scheme metrics")
    st.caption(
        "Administration queues, vouchers, and progress metrics ingested into **`mart_scheme_metric`** "
        "from optional portal workbooks (`raw_xlsx_scheme_metric`). Register parsers in "
        "`metadata/xlsx_registry.yaml` and run **`xlsx`** then **`marts`**."
    )
    y0, y1 = int(f["y0"]), int(f["y1"])
    if not queries_scheme.scheme_metric_exists():
        st.info(
            "Relation **`mart_scheme_metric`** is not in the database. After loading scheme workbooks, run "
            "**`python -m pipeline.orchestrate marts`** (or **`full_refresh`**)."
        )
        return

    with st.spinner("Loading scheme keys…"):
        sk = queries_scheme.scheme_metric_distinct_schemes(y0, y1)
    if sk.empty:
        st.info("No **`mart_scheme_metric`** rows for the selected year range.")
        return

    scheme_options = sk["scheme_key"].dropna().astype(str).tolist()
    scheme_pick = st.selectbox("Scheme", scheme_options, key="scheme_metric_scheme")

    with st.spinner("Loading metrics…"):
        mm = queries_scheme.scheme_metric_distinct_metrics(y0, y1, scheme_pick if scheme_pick else None)
    metric_opts = (
        ["(all metrics)"] + mm["metric_name"].dropna().astype(str).tolist()
        if not mm.empty
        else ["(all metrics)"]
    )
    metric_pick = st.selectbox("Metric (optional)", metric_opts, key="scheme_metric_metric")
    metric_arg = None if metric_pick == "(all metrics)" else metric_pick

    with st.spinner("Loading rows…"):
        long_df = queries_scheme.scheme_metric_long(
            y0, y1, scheme_key=scheme_pick, metric_name=metric_arg
        )

    if long_df.empty:
        st.info("No rows for this scheme/metric and year range.")
        return

    preview_h = min(480, 28 * min(24, len(long_df)))
    st.dataframe(long_df, use_container_width=True, height=preview_h)

    chart_df = long_df[
        long_df["calendar_year"].notna() & long_df["value"].notna()
    ].copy()
    if not chart_df.empty and metric_arg:
        chart_df = chart_df.sort_values(
            ["calendar_year", "calendar_month"], na_position="last"
        )
        series_key = (
            chart_df["entity"].fillna("").astype(str).replace("", "_all")
            if "entity" in chart_df.columns
            else None
        )
        if series_key is not None and chart_df["entity"].notna().any() and chart_df["entity"].astype(str).str.strip().ne("").any():
            wide = chart_df.pivot_table(
                index="calendar_year",
                columns="entity",
                values="value",
                aggfunc="first",
            ).reset_index()
            val_cols = [c for c in wide.columns if c != "calendar_year"]
            if val_cols:
                st.plotly_chart(
                    plots.multi_line(wide, "calendar_year", val_cols, f"{scheme_pick} — {metric_arg}"),
                    use_container_width=True,
                )
        else:
            yy = chart_df.groupby("calendar_year", as_index=False)["value"].mean().sort_values("calendar_year")
            st.plotly_chart(
                plots.line_simple(yy, "calendar_year", "value", f"{scheme_pick} — {metric_arg}", "Value"),
                use_container_width=True,
            )
    elif not chart_df.empty and not metric_arg:
        st.caption("Pick a single **metric** above to plot a year series (optional).")

    csv_download(long_df, "Download scheme metrics CSV", "scheme_metric_filtered.csv")


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


_PAGE_DISPATCH: dict[str, "callable"] = {
    "Home": lambda f: render_home(f),
    "Summary": lambda f: render_summary(f),
    "Social & vulnerability": lambda f: render_theme1(f),
    "Economic & market": lambda f: render_theme2(f),
    "Daily market monitoring": lambda f: render_daily_market(f),
    "DUKES macro context": lambda f: render_dukes_macro(f),
    "ONS PEFA": lambda f: render_pefa(f),
    "Reliability & resilience": lambda f: render_theme3(f),
    "Environmental": lambda f: render_theme4(f),
    "Systemic & regulatory": lambda f: render_theme5(f),
    "Supplier health": lambda f: render_supplier_health(f),
    "Consumer vulnerability": lambda f: render_consumer_vulnerability(f),
    "Switching & competition": lambda f: render_competition(f),
    "Affordability": lambda f: render_affordability(f),
    "Complaints": lambda f: render_complaints(f),
    "Incidents": lambda f: render_incidents(f),
    "Satisfaction": lambda f: render_satisfaction(f),
    "Warm Home Discount": lambda f: render_warm_home_discount(f),
    "Policy scheme metrics": lambda f: render_scheme_metrics(f),
    "Renewables deployment": lambda f: render_renewables(f),
    "Cross-layer analytics": lambda f: render_cross_layer(f),
    "Forecasting": lambda f: render_forecasting(f),
    "What-if": lambda f: render_whatif(f),
    "Methodology": lambda f: render_methodology(),
}


def _apply_pending_sidebar_nav() -> None:
    """Apply Summary / deep-link navigation before ``_sidebar_*`` radios are created."""
    pc = st.session_state.pop("_pending_nav_category", None)
    pp = st.session_state.pop("_pending_nav_page", None)
    if pc is not None:
        st.session_state["category"] = pc
        st.session_state["_sidebar_section"] = pc
    if pp is not None:
        st.session_state["page"] = pp
        st.session_state["_sidebar_page"] = pp


def _sidebar_nav_and_theme() -> str:
    """Render the sidebar header (theme toggle + grouped nav) and return active page.

    Section/page radios use keys ``_sidebar_section`` and ``_sidebar_page`` so
    ``st.session_state["category"]`` and ``["page"]`` stay independent — Summary
    uses pending keys applied above before widgets mount.
    """
    _apply_pending_sidebar_nav()
    st.sidebar.title("Navigation")
    st.sidebar.radio("Theme", ["Light", "Dark"], horizontal=True, key="theme")
    inject_css(st.session_state["theme"])

    nav_keys = list(NAV.keys())
    if st.session_state.get("category") not in NAV:
        st.session_state["category"] = nav_keys[0]

    # Do not assign ``_sidebar_section`` / ``_sidebar_page`` from ``category``/``page`` every run —
    # that overwrites the radios before user input is applied and blocks picking e.g. Summary.
    category = st.sidebar.radio("Section", nav_keys, key="_sidebar_section")
    st.session_state["category"] = category

    pages = NAV[category]
    if st.session_state.get("page") not in pages:
        st.session_state["page"] = pages[0]
        st.session_state["_sidebar_page"] = st.session_state["page"]

    page = st.sidebar.radio("Page", pages, key="_sidebar_page")
    st.session_state["page"] = page
    st.sidebar.divider()
    return page


def main():
    try:
        database_url()
    except Exception as e:
        st.error(str(e))
        st.stop()

    try:
        y_min, y_max = queries.fetch_year_bounds()
    except Exception as e:
        st.error("Database unavailable (see error below).")
        st.code(str(e), language="text")
        st.markdown(
            "Configure the DB in **`.env`**: either **`DATABASE_URL`**, or **`UK_ENERGY_DB_PASSWORD`** plus "
            "`UK_ENERGY_DB_HOST`, `UK_ENERGY_DB_PORT`, `UK_ENERGY_DB_NAME`, `UK_ENERGY_DB_USER` (same as the pipeline). "
            "Use a real host (e.g. `localhost`), not the word `host` from examples. **`unset DATABASE_URL`** if a stale "
            "shell export overrides `.env`."
        )
        st.stop()

    init_session_state(y_min, y_max)
    page = _sidebar_nav_and_theme()
    f = sidebar_filters()
    export_pdf_stub()

    render_alerts(f)

    fn = _PAGE_DISPATCH.get(page)
    if fn is None:
        st.error(f"Unknown page: {page!r}")
        return
    fn(f)


if __name__ == "__main__":
    main()

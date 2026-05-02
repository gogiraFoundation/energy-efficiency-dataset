"""Analysis summary page: theme tabs, compact charts, navigation to detail pages."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from dashboard import plots
from dashboard import queries_summary as qs
from dashboard import queries_whd as qw

_JUMP_NETWORK = ("Networks", "Reliability & resilience")
_JUMP_RETAIL = ("Retail", "Supplier health")
_JUMP_SOCIAL = ("Retail", "Warm Home Discount")
_JUMP_RENEWABLES = ("Networks", "Renewables deployment")
_JUMP_MACRO = ("Markets & regulation", "DUKES macro context")
_JUMP_CROSS = ("Cross-layer", "Cross-layer analytics")

# Tab metric keys -> short label for humans (avoid raw snake_case in the UI).
_TAB_METRIC_LABELS: dict[str, str] = {
    "latest_ens_gwh": "ENS (latest year, GWh)",
    "ens_change_pct": "ENS change vs start of range",
    "latest_totex_mgbp": "Totex (latest year, £m)",
    "totex_change_pct": "Totex change vs start of range",
    "active_suppliers_latest": "Active suppliers (latest year)",
    "active_suppliers_change_pct": "Active suppliers change vs start",
    "profit_sum_latest_mgbp": "Domestic profit sum (latest, £m)",
    "hhi_latest": "HHI (latest year)",
    "whd_rows_in_filter": "WHD national rows (year filter)",
    "whd_rows_mart": "WHD national rows (in mart)",
    "renewables_latest_cap_gw": "Cumulative renewables capacity (GW)",
    "energy_ratio_latest": "Energy ratio (latest year)",
    "energy_ratio_change_pct": "Energy ratio change vs start",
    "cross_cost_rows": "Price-cap cross-layer rows",
    "cross_volatility_rows": "Volatility & complaints rows",
}

_TAB_METRIC_ORDER: tuple[str, ...] = (
    "latest_ens_gwh",
    "ens_change_pct",
    "latest_totex_mgbp",
    "totex_change_pct",
    "active_suppliers_latest",
    "active_suppliers_change_pct",
    "profit_sum_latest_mgbp",
    "hhi_latest",
    "whd_rows_in_filter",
    "whd_rows_mart",
    "renewables_latest_cap_gw",
    "energy_ratio_latest",
    "energy_ratio_change_pct",
    "cross_cost_rows",
    "cross_volatility_rows",
)


def _metric_label(key: str) -> str:
    return _TAB_METRIC_LABELS.get(key, key.replace("_", " ").title())


def _format_tab_metric(key: str, v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float) and pd.isna(v):
        return "—"
    try:
        if key in ("whd_rows_in_filter", "whd_rows_mart", "cross_cost_rows", "cross_volatility_rows"):
            return f"{int(v):,}"
        if key == "latest_ens_gwh":
            return f"{float(v):,.2f}"
        if key in ("ens_change_pct", "totex_change_pct", "active_suppliers_change_pct", "energy_ratio_change_pct"):
            return f"{float(v):+.1f}%"
        if key == "latest_totex_mgbp":
            return f"£{float(v):,.0f}m"
        if key == "active_suppliers_latest":
            fv = float(v)
            return f"{int(round(fv)):,}" if abs(fv - round(fv)) < 0.05 else f"{fv:,.1f}"
        if key == "profit_sum_latest_mgbp":
            x = float(v)
            sign = "-" if x < 0 else ""
            return f"{sign}£{abs(x):,.0f}m"
        if key == "hhi_latest":
            x = float(v)
            return f"{x:.4f}" if x <= 1.0 else f"{x:,.0f}"
        if key == "renewables_latest_cap_gw":
            return f"{float(v):,.2f}"
        if key == "energy_ratio_latest":
            return f"{float(v):,.2f}"
        if isinstance(v, float):
            return f"{v:,.4g}"
        return str(v)
    except (TypeError, ValueError):
        return str(v)


def _ordered_metric_keys(metrics: dict[str, Any]) -> list[str]:
    """Stable order: known keys first, then any extras."""
    seen: set[str] = set()
    out: list[str] = []
    for k in _TAB_METRIC_ORDER:
        if k in metrics:
            out.append(k)
            seen.add(k)
    for k in metrics:
        if k not in seen:
            out.append(k)
            seen.add(k)
    return out


def _nav_to(category: str, page: str) -> None:
    """Queue navigation — applied at the start of the next run before sidebar widgets mount."""
    st.session_state["_pending_nav_category"] = category
    st.session_state["_pending_nav_page"] = page


def _download(df: pd.DataFrame | None, label: str, fname: str, key: str) -> None:
    if df is None or df.empty:
        return
    st.download_button(
        label,
        df.to_csv(index=False).encode("utf-8"),
        file_name=fname,
        mime="text/csv",
        key=key,
    )


def _render_chart(spec: dict | None, empty_hint: str | None = None) -> None:
    if not spec:
        st.info(empty_hint or "No chart for this tab — data missing or not aggregated for these filters.")
        return
    df = spec.get("df")
    if df is None or getattr(df, "empty", True):
        st.info("No chart for this tab with current data.")
        return
    kind = spec["kind"]
    title = spec.get("title") or ""
    if kind == "dual_axis":
        fig = plots.dual_axis_lines_compact(
            df,
            spec["x"],
            spec["y1"],
            spec["y2"],
            spec["y1_title"],
            spec["y2_title"],
            title,
        )
    elif kind == "line":
        fig = plots.line_simple_compact(df, spec["x"], spec["y"], title)
    elif kind == "multi":
        fig = plots.multi_line_compact(df, spec["x"], spec["value_cols"], title)
    else:
        st.info("Unknown chart specification.")
        return
    st.plotly_chart(fig, use_container_width=True)


def _tab_body(pack: dict, jump_primary: tuple[str, str], jump_secondary: tuple[str, str] | None, csv_name: str) -> None:
    col_a, col_b = st.columns([1, 2])
    metrics = pack.get("metrics") or {}
    banner = pack.get("banner")
    banner_style = pack.get("banner_style") or "info"
    bullets = pack.get("bullets") or []
    with col_a:
        if banner:
            if banner_style == "warning":
                st.warning(banner)
            else:
                st.info(banner)
        elif not pack.get("ok"):
            if bullets:
                st.info("Limited data for these filters — see the notes under the chart.")
            else:
                st.warning("No data — adjust filters or refresh marts.")

        if pack.get("ok") or metrics:
            for k in _ordered_metric_keys(metrics):
                v = metrics[k]
                lbl = _metric_label(k)
                disp = _format_tab_metric(k, v)
                st.metric(lbl, disp)
        if pack.get("footnote"):
            st.divider()
            st.caption(pack["footnote"])
        if st.button("See full analysis", key=f"jump_{csv_name}_p"):
            _nav_to(jump_primary[0], jump_primary[1])
            st.rerun()
        if jump_secondary and st.button("Related: renewables / schemes", key=f"jump_{csv_name}_s"):
            _nav_to(jump_secondary[0], jump_secondary[1])
            st.rerun()
    with col_b:
        _render_chart(pack.get("chart"), pack.get("chart_empty_hint"))
        chart_df = None
        ch = pack.get("chart")
        if ch and isinstance(ch.get("df"), pd.DataFrame):
            chart_df = ch["df"]
        _download(chart_df, "Download chart data (CSV)", f"summary_{csv_name}.csv", f"dl_{csv_name}")

    if bullets:
        st.markdown("**Notes**")
        for line in bullets:
            st.markdown(f"- {line}")


def render_summary(f: dict) -> None:
    st.title("Analysis summary")
    y0, y1 = int(f["y0"]), int(f["y1"])
    st.caption(
        f"Years **{y0}–{y1}**. Use the sidebar for **network companies**, **retail suppliers**, and **commodity**. "
        "The **Macro** tab and the **DUKES energy ratio** headline are **national** series only (they ignore network "
        "and supplier selections). **Household energy (% of expenditure)** is national and does **not** follow the "
        "payment-method filter — see the note when a payment method other than “all” is selected."
    )

    commodity = f.get("commodity") or "both"
    companies_key = f.get("companies_key")
    supplier_key = f.get("supplier_key")
    payment_method = f.get("payment_method")

    with st.spinner("Loading summary…"):
        hl = qs.summary_headline_metrics(
            y0, y1, companies_key, supplier_key, commodity, payment_method
        )

    if not hl.get("any_ok"):
        st.warning("No summary data for the current filters — widen the year range or clear selections.")

    m_net = hl.get("network") or {}
    m_ret = hl.get("retail") or {}
    m_soc = hl.get("social") or {}
    m_mac = hl.get("macro") or {}
    m_aff = hl.get("affordability") or {}

    def _headline_active_suppliers(v: float | None) -> str:
        if v is None:
            return "—"
        fv = float(v)
        return f"{int(round(fv)):,}" if abs(fv - round(fv)) < 0.05 else f"{fv:,.1f}"

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(
        "Latest ENS (GWh)",
        f"{float(m_net['latest_ens_gwh']):,.2f}" if m_net.get("latest_ens_gwh") is not None else "—",
        help="Energy Not Supplied from the selected network scope in the mart (latest year in the sidebar range).",
    )
    c2.metric(
        "Active suppliers",
        _headline_active_suppliers(
            float(m_ret["active_suppliers_latest"])
            if m_ret.get("active_suppliers_latest") is not None
            else None
        ),
        help="Count from market-structure series (domestic, latest year in range).",
    )
    c3.metric(
        "Renewables cumulative (GW)",
        f"{float(m_mac['renewables_latest_cap_gw']):,.2f}" if m_mac.get("renewables_latest_cap_gw") is not None else "—",
        help="GB cumulative accredited capacity (`mart_renewables_deployment`); paired with DUKES on the Macro tab.",
    )
    c4.metric(
        "DUKES energy ratio",
        f"{float(m_mac['energy_ratio_latest']):,.2f}" if m_mac.get("energy_ratio_latest") is not None else "—",
        help="National primary-energy intensity index from DUKES — not filtered by sidebar network or suppliers.",
    )
    hh = m_aff.get("household_energy_spend_pct_latest")
    c5.metric(
        "Household energy (% exp.)",
        f"{float(hh):.1f}%" if hh is not None else "—",
        help="National share of household spending on energy (annual mart). Not split by payment method.",
    )
    if commodity and commodity != "both":
        st.caption(
            f"**Retail scope:** supplier-profit headlines use **domestic / all fuels** where the source reports a single "
            f"combined figure; **retail HHI** on the Retail tab reflects **{commodity}** only."
        )
    if payment_method and payment_method != "all":
        st.caption(
            f"Payment method **{payment_method}** filters **Consumer vulnerability** (mart rows), **Affordability** "
            "tariffs/price-cap charts, and related retail pages where supported. The **household %** headline stays "
            "national and payment-agnostic."
        )

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        [
            "Network and wholesale",
            "Retail and consumer",
            "Social and policy",
            "Macro and decarbonisation",
            "Cross-layer",
        ]
    )

    with tab1:
        net = qs.summary_network_pack(y0, y1, companies_key, commodity)
        _tab_body(net, _JUMP_NETWORK, None, "network")

    with tab2:
        ret = qs.summary_retail_pack(y0, y1, supplier_key, commodity)
        _tab_body(ret, _JUMP_RETAIL, None, "retail")

    with tab3:
        soc = qs.summary_social_pack(y0, y1, supplier_key)
        _tab_body(soc, _JUMP_SOCIAL, _JUMP_RENEWABLES, "social")

    with tab4:
        mac = qs.summary_macro_pack(y0, y1)
        _tab_body(mac, _JUMP_MACRO, None, "macro")

    with tab5:
        crs = qs.summary_cross_pack(y0, y1, supplier_key)
        _tab_body(crs, _JUMP_CROSS, None, "cross")

    st.subheader("Synthesis")
    st.caption(
        "Headline tiles and **theme tabs** hold the numbers. This block only calls out **data gaps** and **next steps** "
        "so the same percentages are not repeated after every tab."
    )
    parts: list[str] = []
    if m_mac.get("renewables_latest_cap_gw") is None and hl.get("any_ok"):
        parts.append(
            "**Renewables (GW)** headline stays empty until MCS-style workbooks are in **`data/renewables_mcs/`**, "
            "then **`python -m pipeline.orchestrate xlsx`** and **`marts`** (or **`full_refresh`**)."
        )
    if hl.get("any_ok"):
        whd_here = qw.whd_national(y0, y1)
        if whd_here.empty and qw.whd_national_fallback().empty:
            parts.append(
                "**Warm Home Discount:** **`mart_warm_home_discount`** has no national rows yet — add WHD `.xlsx` under "
                "**`data/whd/`** (see **`data/whd/README.txt`**), then **xlsx** + **marts**."
            )
    if not parts:
        parts.append(
            "No extra gaps flagged for these filters. Drill down from **Networks**, **Retail**, **Markets**, or "
            "**Cross-layer** for full charts."
        )
    for p in parts:
        st.markdown(f"- {p}")

"""Lightweight aggregated queries for the Analysis summary page (marts-first)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from dashboard import queries_cross as qx
from dashboard import queries_network as qn
from dashboard import queries_renewables as qren
from dashboard import queries_retail as qr
from dashboard import queries_whd as qw


def _latest_household_energy_spend_pct(y0: int, y1: int) -> float | None:
    """National household energy-as-% of expenditure (annual mart layer; payment-agnostic)."""
    df = qr.retail_affordability(y0, y1, "all")
    if df is None or df.empty:
        return None
    h = df[df["layer"] == "household_spend"]
    if h.empty or "value_pct" not in h.columns:
        return None
    h2 = h.dropna(subset=["value_pct"]).sort_values("year")
    if h2.empty:
        return None
    return float(h2["value_pct"].iloc[-1])


def _pct_change(first: float | None, last: float | None) -> float | None:
    if first is None or last is None:
        return None
    if pd.isna(first) or pd.isna(last):
        return None
    try:
        f = float(first)
        l_ = float(last)
    except (TypeError, ValueError):
        return None
    if f == 0:
        return None
    return (l_ - f) / abs(f) * 100.0


def _first_last_numeric(s: pd.Series) -> tuple[float | None, float | None]:
    s = pd.to_numeric(s, errors="coerce").dropna()
    if s.empty:
        return None, None
    return float(s.iloc[0]), float(s.iloc[-1])


@st.cache_data(ttl=600, show_spinner=False)
def summary_network_pack(
    y0: int,
    y1: int,
    companies_key: tuple[str, ...] | None,
    commodity: str,
) -> dict[str, Any]:
    """ENS / totex trend from ``mart_cost_reliability`` via ``home_ens_totex_trend``."""
    del commodity  # network mart trend is not commodity-split in this path
    trend = qn.home_ens_totex_trend(y0, y1, companies_key)
    if trend.empty or "ens_mwh" not in trend.columns:
        return {
            "ok": False,
            "metrics": {},
            "chart": None,
            "bullets": [
                "No network cost-reliability data for these filters (refresh `mart_cost_reliability` "
                "or widen the year range)."
            ],
            "footnote": None,
        }

    t = trend.sort_values("year")
    ens_first, ens_last = _first_last_numeric(t["ens_mwh"])
    ens_pct = _pct_change(ens_first, ens_last)
    tx_first, tx_last = (
        _first_last_numeric(t["totex_million_gbp"]) if "totex_million_gbp" in t.columns else (None, None)
    )
    tx_pct = _pct_change(tx_first, tx_last)

    latest_y = int(t["year"].iloc[-1])
    bullets: list[str] = []
    bullets.append(
        f"Latest plotted year: **{latest_y}**. Percent changes in the metrics column compare the **first and last year** "
        "in your sidebar range (not YoY)."
    )
    if ens_pct is None and ens_first is not None and ens_last is not None:
        bullets.append("ENS trend is present but **% change** is undefined (zero or missing baseline year).")
    if tx_pct is None and tx_first is not None and tx_last is not None:
        bullets.append("Totex trend is present but **% change** is undefined (zero or missing baseline year).")

    return {
        "ok": True,
        "metrics": {
            "latest_ens_gwh": float(ens_last) / 1000.0 if ens_last is not None else None,
            "ens_change_pct": ens_pct,
            "latest_totex_mgbp": float(tx_last) if tx_last is not None else None,
            "totex_change_pct": tx_pct,
        },
        "chart": {
            "kind": "dual_axis",
            "df": t,
            "x": "year",
            "y1": "ens_mwh",
            "y2": "totex_million_gbp",
            "y1_title": "ENS (MWh)",
            "y2_title": "Totex (£m)",
            "title": "ENS and totex (annual)",
        },
        "bullets": bullets,
        "footnote": "Source: `mart_cost_reliability` via dashboard network queries.",
    }


@st.cache_data(ttl=600, show_spinner=False)
def summary_retail_pack(
    y0: int,
    y1: int,
    supplier_key: tuple[int, ...] | None,
    commodity: str,
) -> dict[str, Any]:
    """Supplier-health snapshot: active suppliers, optional HHI (mixed scales — see footnote)."""
    df, _src = qr.retail_supplier_health(y0, y1, supplier_key)
    if df is None or df.empty or "year" not in df.columns:
        return {
            "ok": False,
            "metrics": {},
            "chart": None,
            "bullets": ["No retail supplier-health rows for these filters."],
            "footnote": None,
        }

    ydf = df.sort_values("year")
    agg_map: dict[str, str] = {}
    if "active_suppliers_avg" in ydf.columns:
        agg_map["active_suppliers_avg"] = "max"
    if "profit_million_gbp" in ydf.columns:
        agg_map["profit_million_gbp"] = "sum"
    if "hhi" in ydf.columns:
        agg_map["hhi"] = "max"
    if not agg_map:
        return {
            "ok": False,
            "metrics": {},
            "chart": None,
            "bullets": ["Supplier-health rows lack expected columns."],
            "footnote": None,
        }
    per_y = ydf.groupby("year", as_index=False).agg(agg_map)
    per_y = per_y.dropna(subset=["year"], how="all")

    as_first, as_last = _first_last_numeric(per_y["active_suppliers_avg"])
    chg = _pct_change(as_first, as_last)
    prof_first, prof_last = _first_last_numeric(per_y["profit_million_gbp"])
    hhi_last = per_y["hhi"].dropna()
    hhi_v = float(hhi_last.iloc[-1]) if not hhi_last.empty else None
    if commodity in ("electricity", "gas"):
        alt_hhi = qr.retail_hhi_normalized_latest(y0, y1, commodity)
        if alt_hhi is not None:
            hhi_v = alt_hhi

    bullets: list[str] = []
    if prof_last is not None:
        _ps = float(prof_last)
        _pp = f"-£{abs(_ps):,.0f}m" if _ps < 0 else f"£{_ps:,.0f}m"
        bullets.append(
            f"Sum of reported domestic profit across suppliers in the latest year: **{_pp}** "
            "(market total, not a single firm)."
        )
    if hhi_v is not None:
        if hhi_v <= 1.0:
            bullets.append(
                f"Retail HHI (normalized, 0–1): **{hhi_v:.4f}** — generation HHI elsewhere may use the **0–10,000** scale."
            )
        else:
            bullets.append(f"Retail HHI in the latest year: **{hhi_v:.0f}** (classic scale if from share weights).")

    y_col = "active_suppliers_avg" if "active_suppliers_avg" in per_y.columns else None
    chart_spec = None
    if y_col:
        chart_spec = {
            "kind": "line",
            "df": per_y,
            "x": "year",
            "y": y_col,
            "title": "Active suppliers (structure series)",
        }

    return {
        "ok": True,
        "metrics": {
            "active_suppliers_latest": as_last,
            "active_suppliers_change_pct": chg,
            "profit_sum_latest_mgbp": prof_last,
            "hhi_latest": hhi_v,
        },
        "chart": chart_spec,
        "bullets": bullets or ["Retail rows loaded — see Supplier health for detail."],
        "footnote": _retail_summary_footnote(commodity),
    }


def _retail_summary_footnote(commodity: str) -> str:
    base = (
        "**Profit** is summed across suppliers for domestic reporting where the fact grain is **`commodity='all'`** "
        "(combined fuels in the source — not split by electricity vs gas)."
    )
    if commodity in ("electricity", "gas"):
        base += f" **HHI** in this tab uses the **{commodity}** retail market only (normalized 0–1)."
    else:
        base += " **HHI** is the mean of separate electricity and gas retail HHIs (0–1)."
    base += " Open **Supplier health** for full supplier-level charts."
    return base


@st.cache_data(ttl=600, show_spinner=False)
def summary_social_pack(
    y0: int,
    y1: int,
    supplier_key: tuple[int, ...] | None,
) -> dict[str, Any]:
    """Warm Home Discount and related scheme context (renewables capacity → Macro tab)."""
    whd = qw.whd_national(y0, y1)
    whd_sup = qw.whd_supplier(y0, y1, supplier_key) if supplier_key else pd.DataFrame()
    whd_fallback = qw.whd_national_fallback() if whd.empty else pd.DataFrame()

    bullets: list[str] = []
    whd_relaxed_note = False
    if not whd.empty:
        n_nat = whd["nation"].nunique() if "nation" in whd.columns else 0
        bullets.append(f"WHD national (**{len(whd)}** rows, **{n_nat}** nations) in selected years.")
    elif not whd_fallback.empty:
        cy = whd_fallback["calendar_year"].dropna()
        yr_lo = int(cy.min()) if not cy.empty else None
        yr_hi = int(cy.max()) if not cy.empty else None
        if yr_lo is not None and yr_hi is not None:
            bullets.append(
                f"WHD mart has national rows **outside** years {y0}–{y1} "
                f"(calendar_year roughly **{yr_lo}–{yr_hi}**). Widen the year slider or open **Warm Home Discount**."
            )
        else:
            bullets.append(
                "WHD national rows exist in the mart but **calendar_year** is often null — open **Warm Home Discount** "
                "for scheme-year detail."
            )
        whd_relaxed_note = True
    else:
        bullets.append(
            "No WHD national rows: refresh **`mart_warm_home_discount`** after loading WHD workbooks, "
            "or confirm the mart exists."
        )

    if supplier_key and not whd_sup.empty:
        bullets.append(
            f"WHD **supplier** slice: **{len(whd_sup)}** row(s) for selected suppliers (obligation / redistribution)."
        )
    elif supplier_key and whd_sup.empty:
        bullets.append(
            "No WHD supplier-level rows for the selected suppliers in this year range — "
            "see **Warm Home Discount** or widen years."
        )

    chart_spec: dict[str, Any] | None = None
    if not whd_fallback.empty and "scheme_value_mgbp" in whd_fallback.columns:
        wplot = whd_fallback.dropna(subset=["scheme_value_mgbp"]).copy()
        if not wplot.empty and "calendar_year" in wplot.columns:
            wplot["calendar_year"] = pd.to_numeric(wplot["calendar_year"], errors="coerce")
            wagg = (
                wplot.groupby("calendar_year", as_index=False)["scheme_value_mgbp"].sum().sort_values("calendar_year")
            )
            wagg = wagg.dropna(subset=["calendar_year"])
            if len(wagg) >= 2:
                chart_spec = {
                    "kind": "line",
                    "df": wagg,
                    "x": "calendar_year",
                    "y": "scheme_value_mgbp",
                    "title": "WHD total scheme value (£m) by calendar year (mart-wide)",
                }
                bullets.append("Chart uses **all** national WHD rows (not only the selected year filter).")

    has_whd_signal = not whd.empty or not whd_fallback.empty
    bullets.append(
        "**Renewables (accredited capacity)** are summarised under **Macro and decarbonisation** alongside DUKES."
    )
    ok = True

    banner: str | None = None
    banner_style: str | None = None
    if has_whd_signal and whd_relaxed_note:
        banner = (
            "WHD rows exist in the mart but not inside your selected calendar years — widen the **year range** "
            "or open **Warm Home Discount** for scheme-year tables."
        )
        banner_style = "info"

    chart_empty_hint = None
    if chart_spec is None:
        chart_empty_hint = (
            "No WHD time series in this tab yet — load **WHD** workbooks (`data/whd/`), then **xlsx** and **marts**, "
            "or widen the year range (see bullets)."
        )

    return {
        "ok": ok,
        "metrics": {
            "whd_rows_in_filter": int(len(whd)),
            "whd_rows_mart": int(len(whd_fallback)) if whd.empty else int(len(whd)),
        },
        "chart": chart_spec,
        "chart_empty_hint": chart_empty_hint,
        "bullets": bullets,
        "footnote": (
            "ECO/BUS/admin scheme queues: **Retail → Policy scheme metrics** when ingested into `mart_scheme_metric`."
        ),
        "banner": banner,
        "banner_style": banner_style,
    }


@st.cache_data(ttl=600, show_spinner=False)
def summary_macro_pack(y0: int, y1: int) -> dict[str, Any]:
    """DUKES national intensity plus renewables accredited capacity (macro / decarbonisation)."""
    d = qn.dukes_primary_gdp_ratio(y0, y1)
    ren = qren.renewables_annual(y0, y1)
    has_dukes = not d.empty and "energy_ratio" in d.columns
    ren_agg = pd.DataFrame()
    if not ren.empty and "year" in ren.columns and "cumulative_capacity_kw" in ren.columns:
        ren_agg = (
            ren.groupby("year", as_index=False)["cumulative_capacity_kw"].sum().sort_values("year")
        )
    has_ren = not ren_agg.empty

    bullets: list[str] = []
    chart_spec: dict[str, Any] | None = None
    metrics: dict[str, Any] = {}
    er_last = None
    er_pct = None

    if has_dukes:
        t = d.sort_values("year")
        er_first, er_last = _first_last_numeric(t["energy_ratio"])
        er_pct = _pct_change(er_first, er_last)
        metrics["energy_ratio_latest"] = float(er_last) if er_last is not None else None
        metrics["energy_ratio_change_pct"] = er_pct
        bullets.append(
            "**National DUKES series** — ignores sidebar network companies, suppliers, regions, and commodity."
        )
        if er_pct is not None:
            bullets.append(
                f"Primary energy per unit GDP (`energy_ratio`) moved **{er_pct:+.1f}%** across the range."
            )
        pe_cols = [c for c in ("primary_energy_mtoe", "primary_energy_twh") if c in t.columns]
        if pe_cols:
            pe = pd.to_numeric(t[pe_cols[0]], errors="coerce").dropna()
            if not pe.empty:
                bullets.append(f"Latest primary energy ({pe_cols[0]}): **{float(pe.iloc[-1]):.2f}**.")

    latest_cap_gw: float | None = None
    cap_pct: float | None = None
    if has_ren:
        cap_first, cap_last = _first_last_numeric(ren_agg["cumulative_capacity_kw"])
        cap_pct = _pct_change(cap_first, cap_last)
        latest_cap_gw = float(ren_agg["cumulative_capacity_kw"].iloc[-1]) / 1e6
        metrics["renewables_latest_cap_gw"] = latest_cap_gw
        metrics["renewables_cap_change_pct"] = cap_pct
        if cap_pct is not None:
            bullets.append(
                f"GB cumulative accredited capacity (technologies summed) changed **{cap_pct:+.1f}%** over the range."
            )
    elif not ren.empty:
        bullets.append("Renewables mart present but `cumulative_capacity_kw` is missing for this query.")

    if has_dukes and has_ren:
        t = d.sort_values("year")[["year", "energy_ratio"]].copy()
        merged = t.merge(ren_agg, on="year", how="outer").sort_values("year")
        merged["renewables_cap_gw"] = pd.to_numeric(merged["cumulative_capacity_kw"], errors="coerce") / 1e6
        chart_spec = {
            "kind": "dual_axis",
            "df": merged,
            "x": "year",
            "y1": "energy_ratio",
            "y2": "renewables_cap_gw",
            "y1_title": "DUKES energy ratio",
            "y2_title": "Renewables cumulative (GW)",
            "title": "DUKES intensity and accredited renewables capacity",
        }
    elif has_dukes:
        t = d.sort_values("year")
        chart_spec = {
            "kind": "line",
            "df": t,
            "x": "year",
            "y": "energy_ratio",
            "title": "DUKES energy ratio (primary energy / GDP)",
        }
    elif has_ren:
        rline = ren_agg.assign(
            renewables_cap_gw=pd.to_numeric(ren_agg["cumulative_capacity_kw"], errors="coerce") / 1e6
        )
        chart_spec = {
            "kind": "line",
            "df": rline,
            "x": "year",
            "y": "renewables_cap_gw",
            "title": "Renewables — cumulative accredited capacity (GW)",
        }

    if not has_dukes and not has_ren:
        return {
            "ok": False,
            "metrics": {},
            "chart": None,
            "bullets": [
                "No DUKES primary-energy ratio (`stg_dukes_primary_consumption`) and no renewables mart rows "
                "for this range."
            ],
            "footnote": None,
        }

    footnote = (
        "DUKES: national DESNZ accounting (`stg_dukes_primary_consumption`). Renewables: `mart_renewables_deployment` "
        "when MCS-style workbooks are loaded. For supply-chain vectors see **ONS PEFA**."
    )
    return {
        "ok": True,
        "metrics": metrics,
        "chart": chart_spec,
        "bullets": bullets or ["Macro indicators loaded — see Markets → DUKES / Renewables for detail."],
        "footnote": footnote,
    }


@st.cache_data(ttl=600, show_spinner=False)
def summary_cross_pack(y0: int, y1: int, supplier_key: tuple[int, ...] | None) -> dict[str, Any]:
    """Cross-layer marts: bill components vs wholesale where available."""
    del supplier_key  # cost_to_consumer is not supplier-granular
    cost = qx.cross_cost_to_consumer(y0, y1)
    vol = qx.cross_volatility_complaints(y0, y1)

    bullets: list[str] = []
    chart_spec: dict[str, Any] | None = None

    if not cost.empty and "year" in cost.columns:
        cols = [c for c in ("network_gbp", "total_cap_gbp") if c in cost.columns]
        if cols:
            plot_df = cost[["year"] + cols].sort_values("year")
            nf = plot_df["network_gbp"].iloc[-1] if "network_gbp" in plot_df.columns else None
            tf = plot_df["total_cap_gbp"].iloc[-1] if "total_cap_gbp" in plot_df.columns else None
            if nf is not None and tf is not None and pd.notna(nf) and pd.notna(tf) and float(tf) != 0:
                bullets.append(
                    f"Latest-year network share of price-cap stack (approx.): **{100 * float(nf) / float(tf):.1f}%**."
                )
            chart_spec = {
                "kind": "multi",
                "df": plot_df,
                "x": "year",
                "value_cols": cols,
                "title": "Price-cap components (£)",
            }

    chart_empty_hint: str | None = None
    if not vol.empty and len(vol) > 0:
        bullets.append(f"Volatility–complaints mart rows: **{len(vol)}** year-rows loaded.")
        if chart_spec is None:
            chart_empty_hint = (
                "Price-cap breakdown chart appears when **`mart_cross_layer_cost_to_consumer`** has rows for "
                "your years — refresh marts after ETL. Volatility–complaints data above still loads."
            )

    ok = chart_spec is not None or not vol.empty
    return {
        "ok": ok,
        "metrics": {
            "cross_cost_rows": int(len(cost)),
            "cross_volatility_rows": int(len(vol)),
        },
        "chart": chart_spec,
        "bullets": bullets or ["Cross-layer marts empty — refresh materialized views after ETL."],
        "footnote": "See Cross-layer analytics for correlation charts.",
        "chart_empty_hint": chart_empty_hint,
    }


@st.cache_data(ttl=600, show_spinner=False)
def summary_headline_metrics(
    y0: int,
    y1: int,
    companies_key: tuple[str, ...] | None,
    supplier_key: tuple[int, ...] | None,
    commodity: str,
    payment_method: str | None = None,
) -> dict[str, Any]:
    """Compose top-row headline values from theme packs (no extra SQL)."""
    net = summary_network_pack(y0, y1, companies_key, commodity)
    ret = summary_retail_pack(y0, y1, supplier_key, commodity)
    soc = summary_social_pack(y0, y1, supplier_key)
    mac = summary_macro_pack(y0, y1)
    crs = summary_cross_pack(y0, y1, supplier_key)
    hh_pct = _latest_household_energy_spend_pct(y0, y1)
    return {
        "network": net.get("metrics", {}),
        "retail": ret.get("metrics", {}),
        "social": soc.get("metrics", {}),
        "macro": mac.get("metrics", {}),
        "cross": crs.get("metrics", {}),
        "affordability": {
            "household_energy_spend_pct_latest": hh_pct,
            "payment_method": payment_method or "all",
        },
        "any_ok": any(
            p.get("ok") for p in (net, ret, soc, mac, crs) if isinstance(p, dict)
        ),
    }

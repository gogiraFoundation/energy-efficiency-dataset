"""Sidebar filters shared across network, retail and cross-layer pages.

All widgets bind to st.session_state via `key=` so user choices persist across
page switches. Year bounds are clamped to the live data range so a stale
session value never trips Streamlit's slider validation.
"""

from __future__ import annotations

import streamlit as st

from dashboard import queries_network as queries
from dashboard import queries_retail
from dashboard.utils import CommodityFilter

_PAYMENT_OPTIONS = ("all", "direct_debit", "standard_credit", "prepayment", "smart_prepayment")
_COMMODITY_OPTIONS = ("both", "electricity", "gas")


def _companies_tuple(sel: list[str] | None) -> tuple[str, ...] | None:
    if not sel:
        return None
    return tuple(sorted(sel))


def _geo_tuple(ids: list[int] | None) -> tuple[int, ...] | None:
    if not ids:
        return None
    return tuple(sorted(ids))


def _supplier_tuple(ids: list[int] | None) -> tuple[int, ...] | None:
    if not ids:
        return None
    return tuple(sorted(ids))


def _clamped_year_range(y_min: int, y_max: int) -> tuple[int, int]:
    cur = st.session_state.get("year_range", (y_min, min(y_max, y_min + 8)))
    lo = max(y_min, min(y_max, int(cur[0])))
    hi = max(y_min, min(y_max, int(cur[1])))
    if lo > hi:
        lo, hi = y_min, y_max
    return lo, hi


def sidebar_filters() -> dict:
    st.sidebar.header("Filters")
    y_min, y_max = queries.fetch_year_bounds()

    # Re-seat persisted year range inside live bounds before the slider renders.
    st.session_state["year_range"] = _clamped_year_range(y_min, y_max)
    y0, y1 = st.sidebar.slider("Year range", y_min, y_max, key="year_range")

    commodity: CommodityFilter = st.sidebar.radio(
        "Commodity", _COMMODITY_OPTIONS, horizontal=True, key="commodity"
    )

    companies_df = queries.fetch_companies(commodity)
    names = companies_df["company_name"].dropna().unique().tolist() if not companies_df.empty else []
    # Drop persisted picks that no longer exist for the current commodity.
    st.session_state["companies_sel"] = [
        n for n in st.session_state.get("companies_sel", []) if n in names
    ]
    companies_sel = st.sidebar.multiselect(
        "Network companies (optional)", names, key="companies_sel"
    )

    suppliers_df = queries_retail.fetch_suppliers()
    supplier_labels = (
        {
            f"{row['supplier_name']} ({row['supplier_id']})": int(row["supplier_id"])
            for _, row in suppliers_df.iterrows()
        }
        if not suppliers_df.empty
        else {}
    )
    st.session_state["supplier_pick"] = [
        k for k in st.session_state.get("supplier_pick", []) if k in supplier_labels
    ]
    supplier_pick = st.sidebar.multiselect(
        "Retail suppliers (optional)", list(supplier_labels.keys()), key="supplier_pick"
    )
    supplier_ids = [supplier_labels[k] for k in supplier_pick]

    payment_method = st.sidebar.radio(
        "Payment method (retail)", _PAYMENT_OPTIONS, horizontal=False, key="payment_method"
    )

    regions_df = queries.fetch_regions()
    geo_options = (
        regions_df[["geography_id", "geography_name"]].drop_duplicates().values.tolist()
        if not regions_df.empty
        else []
    )
    geo_labels = {f"{name} ({gid})": gid for gid, name in geo_options}
    st.session_state["geo_pick"] = [
        k for k in st.session_state.get("geo_pick", []) if k in geo_labels
    ]
    geo_pick = st.sidebar.multiselect(
        "Regions (economic impact only)", list(geo_labels.keys()), key="geo_pick"
    )
    geo_ids = [geo_labels[k] for k in geo_pick]

    return {
        "y0": y0,
        "y1": y1,
        "commodity": commodity,
        "companies_key": _companies_tuple(companies_sel),
        "supplier_key": _supplier_tuple(supplier_ids),
        "payment_method": payment_method,
        "geo_key": _geo_tuple(geo_ids),
    }

"""Filter builders, CO2 helpers, and small dataframe utilities.

For checking whether a table, view, or materialized view exists in PostgreSQL,
use ``dashboard.db.object_exists`` (includes ``pg_matviews`` and multi-schema search).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import pandas as pd

CommodityFilter = Literal["electricity", "gas", "both"]

# Illustrative static factors (kg CO2e per MWh thermal/electrical output) for GB-style reporting.
# Labeled illustrative in the UI — not official BEIS factors.
FUEL_CO2_KG_PER_MWH: dict[str, float] = {
    "coal": 850.0,
    "gas": 400.0,
    "ccgt": 400.0,
    "nuclear": 12.0,
    "wind": 11.0,
    "offshore_wind": 11.0,
    "onshore_wind": 11.0,
    "solar": 45.0,
    "hydro": 24.0,
    "biomass": 120.0,
    "other": 300.0,
    "oil": 650.0,
    "pumped_storage": 120.0,
    "imports": 350.0,
    "total": 350.0,
}


def normalize_fuel_key(name: str) -> str:
    n = name.lower().replace(" ", "_").replace("-", "_")
    for prefix in ("generation_share_twh_",):
        if n.startswith(prefix):
            n = n[len(prefix) :]
    return n


def implied_co2_kg_per_mwh_generation_mix(
    mix_long: pd.DataFrame,
    period_col: str,
    fuel_col: str = "fuel_source",
    twh_col: str = "value",
) -> pd.Series:
    """
    mix_long: rows per (period, fuel) with generation in TWh.
    Returns a Series indexed by period with kg CO2e / MWh (electricity implied).
    """
    if mix_long.empty or period_col not in mix_long.columns:
        return pd.Series(dtype=float)
    out: dict = {}
    for p, g in mix_long.groupby(period_col):
        num = 0.0
        den = 0.0
        for _, r in g.iterrows():
            t = float(pd.to_numeric(r[twh_col], errors="coerce") or 0.0)
            if t == 0:
                continue
            k = normalize_fuel_key(str(r[fuel_col]))
            if k in ("total", "TOTAL"):
                continue
            f = FUEL_CO2_KG_PER_MWH.get(k, FUEL_CO2_KG_PER_MWH["other"])
            mwh = t * 1000.0
            num += mwh * f
            den += mwh
        out[p] = num / den if den else float("nan")
    return pd.Series(out)


def implied_co2_from_pivot(
    pivot_twh: pd.DataFrame,
) -> pd.Series:
    """pivot_twh: columns = fuel names, index = period, values TWh."""
    if pivot_twh.empty:
        return pd.Series(dtype=float)
    out = {}
    for period, row in pivot_twh.iterrows():
        num = 0.0
        den = 0.0
        for fuel, twh in row.items():
            if pd.isna(twh) or fuel in ("TOTAL", "total"):
                continue
            k = normalize_fuel_key(str(fuel))
            f = FUEL_CO2_KG_PER_MWH.get(k, FUEL_CO2_KG_PER_MWH["other"])
            t = float(twh)
            num += t * 1000.0 * f
            den += t * 1000.0
        out[period] = num / den if den else float("nan")
    return pd.Series(out)


def commodity_sql_sector_filter(commodity: CommodityFilter, table_alias: str = "ns") -> str:
    if commodity == "both":
        return ""
    return f" AND lower({table_alias}.commodity) = :_commodity "


def safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
    return num / den.replace(0, float("nan"))


def zscore(s: pd.Series) -> pd.Series:
    if s.empty or s.nunique() < 2:
        return pd.Series(0.0, index=s.index)
    return (s - s.mean()) / s.std(ddof=0)


def composite_vulnerability_rank(
    fuel_poor: pd.Series,
    minutes_lost: pd.Series,
) -> pd.Series:
    """Higher = worse. Uses z-scores when both present."""
    a = zscore(fuel_poor.fillna(0))
    b = zscore(minutes_lost.fillna(0))
    return a + b


@lru_cache(maxsize=1)
def load_company_mapping_df() -> pd.DataFrame:
    """Ofgem alias rows under ``metadata/company_mapping.csv`` for dashboard joins."""
    path = Path(__file__).resolve().parent.parent / "metadata" / "company_mapping.csv"
    return pd.read_csv(path)


def canonical_company_name(
    raw: str,
    mapping: pd.DataFrame | None = None,
    *,
    prefer_sector: str | None = None,
) -> str:
    """Map a workbook or raw label to canonical ``company_name`` when possible."""
    if mapping is None:
        mapping = load_company_mapping_df()
    if pd.isna(raw) or not str(raw).strip():
        return str(raw)
    s = str(raw).strip()
    sl = s.lower()
    src_l = mapping["source_company_name"].astype(str).str.strip().str.lower()
    hit = mapping[src_l == sl]
    if prefer_sector:
        h2 = hit[hit["network_sector_code"].astype(str) == prefer_sector]
        if not h2.empty:
            return str(h2.iloc[0]["company_name"])
    if not hit.empty:
        return str(hit.iloc[0]["company_name"])
    cn = mapping["company_name"].astype(str).str.strip().str.lower()
    hit3 = mapping[cn == sl]
    if prefer_sector:
        h4 = hit3[hit3["network_sector_code"].astype(str) == prefer_sector]
        if not h4.empty:
            return str(h4.iloc[0]["company_name"])
    if not hit3.empty:
        return str(hit3.iloc[0]["company_name"])
    return s


def apply_canonical_company(
    names: pd.Series,
    mapping: pd.DataFrame | None = None,
    *,
    prefer_sector: str | None = None,
) -> pd.Series:
    m = mapping if mapping is not None else load_company_mapping_df()
    return names.map(lambda x: canonical_company_name(x, m, prefer_sector=prefer_sector))

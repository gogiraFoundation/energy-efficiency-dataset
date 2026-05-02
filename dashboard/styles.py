"""Custom CSS for the Streamlit dashboard.

Targets stable [data-testid] selectors so styles survive Streamlit version bumps.
"""

from __future__ import annotations

from typing import Literal

import streamlit as st

Theme = Literal["Light", "Dark"]

# Shared rules: layout, fonts, spacing.
_BASE_CSS = """
<style>
  .stApp [data-testid="stHeader"] { background: transparent; }
  [data-testid="stMetric"] {
    padding: 0.85rem 1rem;
    border-radius: 0.55rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }
  [data-testid="stMetricLabel"] { font-weight: 500; }
  .stDataFrame, .stTable { font-size: 0.85rem; }
  .stPlotlyChart { border-radius: 0.5rem; overflow: hidden; }
  h1, h2, h3 { font-weight: 600; letter-spacing: -0.01em; }
  /* Tighter sidebar header spacing */
  [data-testid="stSidebar"] h1,
  [data-testid="stSidebar"] h2,
  [data-testid="stSidebar"] h3 { margin-top: 0.6rem; }
</style>
"""

LIGHT_CSS = """
<style>
  .stApp { background-color: #f6f8fb; color: #1e2b3a; }
  [data-testid="stSidebar"] {
    background-color: #ffffff;
    border-right: 1px solid #e3e8ef;
  }
  h1, h2, h3 { color: #1e3a5f; }
  [data-testid="stMetric"] { background-color: #ffffff; }
  [data-testid="stMetricValue"] { color: #1e3a5f; }
  div[data-baseweb="notification"] { border-radius: 0.5rem; }
</style>
"""

DARK_CSS = """
<style>
  .stApp { background-color: #0e1117; color: #e6edf3; }
  [data-testid="stSidebar"] {
    background-color: #161b22;
    border-right: 1px solid #30363d;
  }
  h1, h2, h3 { color: #90caf9; }
  [data-testid="stMetric"] { background-color: #1e1e2f; }
  [data-testid="stMetricValue"] { color: #e6edf3; }
  [data-testid="stMetricDelta"] svg { fill: #90caf9; }
  div[data-baseweb="notification"] { border-radius: 0.5rem; }
</style>
"""


def inject_css(theme: Theme) -> None:
    """Inject base + theme-specific CSS into the current Streamlit page."""
    st.markdown(_BASE_CSS, unsafe_allow_html=True)
    st.markdown(DARK_CSS if theme == "Dark" else LIGHT_CSS, unsafe_allow_html=True)

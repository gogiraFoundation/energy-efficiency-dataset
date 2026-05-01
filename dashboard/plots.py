"""Plotly chart helpers for the dashboard."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy import stats


def apply_default_layout(fig: go.Figure, title: str | None = None) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        title=title,
        font=dict(family="Inter, system-ui, sans-serif", size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=48, r=24, t=56 if title else 40, b=48),
        hovermode="closest",
    )
    return fig


def scatter_with_regression(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    color_col: str | None = None,
    title: str = "",
    x_title: str = "",
    y_title: str = "",
) -> go.Figure:
    fig = go.Figure()
    d = df.dropna(subset=[x_col, y_col])
    if d.empty:
        return apply_default_layout(fig, title)
    x = d[x_col].astype(float)
    y = d[y_col].astype(float)
    if color_col and color_col in d.columns:
        for val, g in d.groupby(color_col):
            fig.add_trace(
                go.Scatter(
                    x=g[x_col],
                    y=g[y_col],
                    mode="markers",
                    name=str(val),
                    marker=dict(size=10, opacity=0.75),
                )
            )
    else:
        fig.add_trace(
            go.Scatter(x=x, y=y, mode="markers", name="Observed", marker=dict(size=10, opacity=0.75))
        )
    if len(x) >= 2 and x.std() > 0:
        slope, intercept, r_value, p_value, _ = stats.linregress(x, y)
        xs = np.linspace(x.min(), x.max(), 50)
        ys = slope * xs + intercept
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                name=f"OLS (R²={r_value**2:.3f})",
                line=dict(dash="dash", width=2),
            )
        )
        fig.add_annotation(
            x=0.02,
            y=0.98,
            xref="paper",
            yref="paper",
            text=f"p={p_value:.2g}",
            showarrow=False,
            font=dict(size=11),
        )
    fig.update_xaxes(title_text=x_title)
    fig.update_yaxes(title_text=y_title)
    return apply_default_layout(fig, title)


def dual_axis_lines(
    df: pd.DataFrame,
    x_col: str,
    y1_col: str,
    y2_col: str,
    y1_title: str,
    y2_title: str,
    title: str = "",
) -> go.Figure:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    if df.empty:
        return apply_default_layout(fig, title)
    fig.add_trace(
        go.Scatter(x=df[x_col], y=df[y1_col], name=y1_title, line=dict(width=2)),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(x=df[x_col], y=df[y2_col], name=y2_title, line=dict(width=2)),
        secondary_y=True,
    )
    fig.update_xaxes(title_text=x_col)
    fig.update_yaxes(title_text=y1_title, secondary_y=False)
    fig.update_yaxes(title_text=y2_title, secondary_y=True)
    return apply_default_layout(fig, title)


def bar_grouped(df: pd.DataFrame, x_col: str, y_cols: list[str], title: str = "") -> go.Figure:
    fig = go.Figure()
    if df.empty:
        return apply_default_layout(fig, title)
    for c in y_cols:
        if c in df.columns:
            fig.add_trace(go.Bar(x=df[x_col], y=df[c], name=c))
    fig.update_layout(barmode="group")
    fig.update_xaxes(title_text=x_col)
    return apply_default_layout(fig, title)


def bar_stacked(df: pd.DataFrame, x_col: str, y_cols: list[str], title: str = "") -> go.Figure:
    fig = go.Figure()
    if df.empty:
        return apply_default_layout(fig, title)
    for c in y_cols:
        if c in df.columns:
            fig.add_trace(go.Bar(x=df[x_col], y=df[c], name=c))
    fig.update_layout(barmode="stack")
    return apply_default_layout(fig, title)


def heatmap_calendarish(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    z_col: str,
    title: str = "",
) -> go.Figure:
    if df.empty:
        return apply_default_layout(go.Figure(), title)
    pivot = df.pivot_table(index=y_col, columns=x_col, values=z_col, aggfunc="mean")
    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=list(pivot.columns),
            y=list(pivot.index),
            colorscale="RdYlGn_r",
            colorbar=dict(title=z_col),
        )
    )
    fig.update_xaxes(title_text=x_col)
    fig.update_yaxes(title_text=y_col)
    return apply_default_layout(fig, title)


def gauge_pair(value_a: float, value_b: float, title_a: str, title_b: str, title: str = "") -> go.Figure:
    fig = make_subplots(
        rows=1,
        cols=2,
        specs=[[{"type": "domain"}, {"type": "domain"}]],
        subplot_titles=(title_a, title_b),
    )
    fig.add_trace(
        go.Indicator(
            mode="gauge+number",
            value=min(100.0, max(0.0, float(value_a or 0))),
            title={"text": title_a},
            gauge={"axis": {"range": [98, 100]}, "bar": {"color": "darkblue"}},
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Indicator(
            mode="gauge+number",
            value=min(100.0, max(0.0, float(value_b or 0))),
            title={"text": title_b},
            gauge={"axis": {"range": [95, 100]}, "bar": {"color": "teal"}},
        ),
        row=1,
        col=2,
    )
    return apply_default_layout(fig, title)


def bubble_chart(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    size_col: str,
    label_col: str,
    title: str = "",
) -> go.Figure:
    fig = go.Figure()
    d = df.dropna(subset=[x_col, y_col])
    if d.empty:
        return apply_default_layout(fig, title)
    s = d[size_col].fillna(0).astype(float)
    s = 10 + 40 * (s / s.max()) if s.max() and s.max() > 0 else 12
    fig.add_trace(
        go.Scatter(
            x=d[x_col],
            y=d[y_col],
            mode="markers",
            marker=dict(size=s, sizemode="area", sizemin=6, opacity=0.65, line=dict(width=0.5, color="white")),
            text=d[label_col] if label_col in d.columns else None,
            hovertemplate="%{text}<br>" + x_col + ": %{x}<br>" + y_col + ": %{y}<extra></extra>",
        )
    )
    fig.update_xaxes(title_text=x_col)
    fig.update_yaxes(title_text=y_col)
    return apply_default_layout(fig, title)


def stacked_area_from_long(
    long_df: pd.DataFrame,
    period_col: str,
    category_col: str,
    value_col: str,
    title: str = "",
) -> go.Figure:
    if long_df.empty:
        return apply_default_layout(go.Figure(), title)
    wide = long_df.pivot_table(index=period_col, columns=category_col, values=value_col, aggfunc="sum").fillna(0)
    fig = go.Figure()
    for col in wide.columns:
        fig.add_trace(go.Scatter(x=wide.index, y=wide[col], name=str(col), stackgroup="one", mode="lines"))
    fig.update_xaxes(title_text=period_col)
    fig.update_yaxes(title_text=value_col)
    return apply_default_layout(fig, title)


def line_simple(df: pd.DataFrame, x_col: str, y_col: str, title: str = "", name: str = "") -> go.Figure:
    fig = go.Figure()
    if not df.empty and y_col in df.columns:
        fig.add_trace(go.Scatter(x=df[x_col], y=df[y_col], name=name or y_col, line=dict(width=2)))
    fig.update_xaxes(title_text=x_col)
    fig.update_yaxes(title_text=y_col)
    return apply_default_layout(fig, title)


def multi_line(df: pd.DataFrame, x_col: str, value_cols: list[str], title: str = "") -> go.Figure:
    fig = go.Figure()
    if df.empty:
        return apply_default_layout(fig, title)
    for c in value_cols:
        if c in df.columns:
            fig.add_trace(go.Scatter(x=df[x_col], y=df[c], name=c, line=dict(width=2)))
    fig.update_xaxes(title_text=x_col)
    return apply_default_layout(fig, title)


def bar_horizontal_diverging(df: pd.DataFrame, label_col: str, value_col: str, title: str = "") -> go.Figure:
    fig = go.Figure()
    if df.empty:
        return apply_default_layout(fig, title)
    colors = ["#c0392b" if v > 0 else "#27ae60" for v in df[value_col].fillna(0)]
    fig.add_trace(go.Bar(y=df[label_col], x=df[value_col], orientation="h", marker_color=colors))
    fig.update_xaxes(title_text=value_col)
    return apply_default_layout(fig, title)


def fig_to_png_bytes(fig: go.Figure, width: int = 900, height: int = 520) -> bytes | None:
    try:
        return fig.to_image(format="png", width=width, height=height, scale=1)
    except Exception:
        return None

"""Shared SQLAlchemy engine and helpers for dashboard query modules."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from dashboard.config import database_url

# Search order when schema is omitted: pipeline raw JSON tables live in `raw`,
# audit log in `audit`, typed xlsx / core / marts typically in `public`.
_OBJECT_SCHEMA_SEARCH_ORDER: tuple[str, ...] = ("public", "raw", "audit")


@st.cache_resource
def get_engine() -> Engine:
    return create_engine(database_url(), pool_pre_ping=True, future=True)


def read_sql(engine: Engine, sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or None)


def _object_exists_in_schema(engine: Engine, name: str, schema_name: str) -> bool:
    q = """
    SELECT 1
    FROM (
        SELECT table_schema AS schema_name, table_name AS object_name
        FROM information_schema.tables
        UNION ALL
        SELECT table_schema AS schema_name, table_name AS object_name
        FROM information_schema.views
        UNION ALL
        SELECT schemaname AS schema_name, matviewname AS object_name
        FROM pg_matviews
    ) o
    WHERE o.schema_name = :schema_name
      AND o.object_name = :name
    LIMIT 1
    """
    return not read_sql(engine, q, {"name": name, "schema_name": schema_name}).empty


def object_exists(engine: Engine, name: str, schema_name: str | None = None) -> bool:
    """True if *name* exists as a table, view, or materialized view.

    If *schema_name* is given, only that schema is checked. If omitted, tries
    ``public``, then ``raw``, then ``audit`` (see migration
    ``sql/migrations/20260501_schema_qualify_raw_tables.sql``). Materialized
    views are included via ``pg_matviews``.
    """
    if schema_name is not None:
        return _object_exists_in_schema(engine, name, schema_name)
    for sch in _OBJECT_SCHEMA_SEARCH_ORDER:
        if _object_exists_in_schema(engine, name, sch):
            return True
    return False

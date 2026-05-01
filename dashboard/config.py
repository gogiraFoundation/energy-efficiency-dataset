"""Dashboard configuration from environment."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus, urlparse

from dotenv import load_dotenv

# Project root (parent of dashboard/) so .env is found even when cwd differs.
_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env")
load_dotenv()


def _database_url_from_uk_energy_env() -> str | None:
    """Same pieces as pipeline/config/settings.yaml + loader: UK_ENERGY_DB_*."""
    host = (os.environ.get("UK_ENERGY_DB_HOST") or "localhost").strip()
    port_raw = (os.environ.get("UK_ENERGY_DB_PORT") or "5432").strip()
    dbname = (os.environ.get("UK_ENERGY_DB_NAME") or "uk_energy").strip()
    user = (os.environ.get("UK_ENERGY_DB_USER") or "uk_energy_user").strip()
    pw_var = (os.environ.get("UK_ENERGY_DB_PASSWORD_ENV_VAR") or "UK_ENERGY_DB_PASSWORD").strip()
    password = (os.environ.get(pw_var) or "").strip()
    if not password:
        return None
    try:
        port = int(port_raw)
    except ValueError as e:
        raise RuntimeError(f"UK_ENERGY_DB_PORT must be an integer, got {port_raw!r}") from e
    u = quote_plus(user)
    p = quote_plus(password)
    return f"postgresql+psycopg2://{u}:{p}@{host}:{port}/{dbname}"


_PLACEHOLDER_HOSTS = frozenset(
    {"host", "hostname", "your_host", "your-host", "db_host", "dbhost", "postgres_host"}
)


def _normalized_url(url: str) -> str:
    if url.startswith("postgresql://") and "+" not in url.split("://", 1)[0]:
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def _hostname_is_placeholder(url: str) -> bool:
    parsed = urlparse(_normalized_url(url))
    return (parsed.hostname or "").lower() in _PLACEHOLDER_HOSTS


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    built = _database_url_from_uk_energy_env()
    if not url:
        url = (built or "").strip()
    if not url:
        raise RuntimeError(
            "Database URL is not configured. Set DATABASE_URL, or set UK_ENERGY_DB_PASSWORD and optionally "
            f"UK_ENERGY_DB_HOST, UK_ENERGY_DB_PORT, UK_ENERGY_DB_NAME, UK_ENERGY_DB_USER in {_REPO_ROOT / '.env'} "
            "(same variables as the pipeline)."
        )
    url = _normalized_url(url)
    if _hostname_is_placeholder(url):
        if built:
            url = _normalized_url(built)
        else:
            raise RuntimeError(
                f"DATABASE_URL hostname is a documentation placeholder. Unset DATABASE_URL (e.g. "
                f"`unset DATABASE_URL`) or fix it, and set UK_ENERGY_DB_PASSWORD plus host/port in "
                f"{_REPO_ROOT / '.env'}."
            )
    if _hostname_is_placeholder(url):
        raise RuntimeError(
            f"DATABASE_URL hostname is a documentation placeholder, not a real server. "
            f"Edit {_REPO_ROOT / '.env'} and use e.g. localhost, 127.0.0.1, or your Postgres host name."
        )

    return url

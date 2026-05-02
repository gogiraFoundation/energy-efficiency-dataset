"""Download Ofgem portal charts hosted on everviz by extracting embedded CSV from embed HTML."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import requests
import yaml

USER_AGENT = (
    "Mozilla/5.0 (compatible; uk-energy-pipeline/1.0; +https://github.com/) "
    "AppleWebKit/537.36 (KHTML, like Gecko)"
)


def _load_manifest(settings: dict) -> dict[str, Any]:
    path = Path((settings.get("sources") or {}).get("portal_downloads_file", "metadata/ofgem_portal_downloads.yaml"))
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def extract_embed_csv(html: str) -> str | None:
    """Parse everviz embed page and return the Highcharts ``data.csv`` string if present."""
    start = html.find("var options = ")
    if start < 0:
        return None
    dec = json.JSONDecoder()
    try:
        obj, _ = dec.raw_decode(html, start + len("var options = "))
    except json.JSONDecodeError:
        return None
    data = obj.get("data") or {}
    csv_text = data.get("csv")
    if not csv_text:
        return None
    return str(csv_text)


def fetch_chart_csv(chart_id: str, embed_base: str, timeout: int, session: requests.Session) -> str:
    url = f"{embed_base.rstrip('/')}/{chart_id}"
    response = session.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    csv_text = extract_embed_csv(response.text)
    if not csv_text:
        raise ValueError(f"No embedded CSV found in everviz embed for chart_id={chart_id}")
    return csv_text


def fetch_all_portal_charts(
    settings: dict,
    logger: logging.Logger,
    *,
    force: bool = False,
) -> int:
    """Fetch every chart in the manifest; write ``data/ofgem_portal_extracted/{chart_id}.csv``."""
    manifest = _load_manifest(settings)
    defaults = manifest.get("defaults") or {}
    embed_base = defaults.get("embed_base_url", "https://app.everviz.com/embed")
    charts = manifest.get("charts") or []
    out_dir = Path(settings["paths"].get("portal_extract_dir", "data/ofgem_portal_extracted"))
    out_dir.mkdir(parents=True, exist_ok=True)

    timeout = int(settings.get("pipeline", {}).get("default_timeout_seconds", 180))
    session = requests.Session()
    written = 0
    for entry in charts:
        chart_id = entry.get("chart_id")
        if not chart_id:
            continue
        dest = out_dir / f"{chart_id}.csv"
        if dest.exists() and not force:
            logger.info("portal fetch skip (exists): %s", dest)
            continue
        try:
            csv_text = fetch_chart_csv(chart_id, embed_base, timeout, session)
            dest.write_text(csv_text, encoding="utf-8")
            logger.info("portal fetch wrote %s (%d bytes)", dest, len(csv_text.encode("utf-8")))
            written += 1
        except Exception as exc:
            logger.exception("portal fetch failed for chart_id=%s: %s", chart_id, exc)
            raise
    logger.info("portal fetch complete: %d file(s) written", written)
    return written


def main() -> None:
    import argparse

    from pipeline.config.loader import load_settings
    from pipeline.utils.logging import setup_logger

    parser = argparse.ArgumentParser(description="Fetch Ofgem everviz chart CSV extracts.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing CSV files.")
    args = parser.parse_args()
    settings = load_settings()
    logger = setup_logger(settings["paths"]["log_dir"])
    fetch_all_portal_charts(settings, logger, force=args.force)


if __name__ == "__main__":
    main()

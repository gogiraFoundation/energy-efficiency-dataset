from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml


def _load_registry(settings: dict) -> list[dict]:
    registry_path = Path(settings["sources"]["registry_file"])
    with registry_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("sources", [])


def _safe_suffix(url: str, default_suffix: str = ".csv") -> str:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix.lower()
    return suffix if suffix in {".csv", ".xlsx", ".xls", ".parquet", ".json"} else default_suffix


def _download(url: str, target: Path, timeout: int) -> None:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    target.write_bytes(response.content)


def fetch_all_sources(settings: dict, logger) -> None:
    sources = _load_registry(settings)
    raw_dir = Path(settings["paths"]["raw_dir"]) / "downloads"
    override_dir = Path(settings["paths"]["override_dir"])
    archive_dir = Path(settings["paths"]["archive_dir"])
    timeout = int(settings["pipeline"].get("default_timeout_seconds", 180))

    raw_dir.mkdir(parents=True, exist_ok=True)
    override_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    for source in sources:
        source_id = source["source_id"]
        mode = source.get("fetch_mode", "http")
        default_url = source.get("url")
        preferred_ext = f".{str(source.get('default_format', 'csv')).lower().lstrip('.')}"
        source_ext = _safe_suffix(default_url or "", default_suffix=preferred_ext)
        download_path = raw_dir / f"{source_id}{source_ext}"
        manual_override = override_dir / f"{source_id}{source_ext}"

        if manual_override.exists():
            logger.info("Using manual override file for %s: %s", source_id, manual_override)
            continue

        if mode == "http" and default_url:
            try:
                _download(default_url, download_path, timeout)
                logger.info("Fetched %s -> %s", source_id, download_path)
            except Exception as exc:
                logger.warning("Fetch failed for %s (%s). Waiting for manual override.", source_id, exc)
        else:
            logger.info("No automated fetch for %s; expecting manual override", source_id)

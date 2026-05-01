#!/usr/bin/env python3
"""Download Ofgem data-portal chart series as Excel files.

Charts on the portal are rendered via Everviz/Highcharts. Underlying tables are
embedded as CSV inside each chart's inject script:

  https://app.everviz.com/inject/<chart-id>/

Chart ids and titles are discovered from Drupal's listing API:

  GET /api/listing/<paragraph_id>?filter[facet_industry_sector]...

Example (matches the portal URL with three industry-sector facets):

  python scripts/fetch_ofgem_data_portal_charts.py \\
    --output-dir data/ofgem_data_portal_xlsx

Fetch every chart returned by the current filters (paginated):

  python scripts/fetch_ofgem_data_portal_charts.py --fetch-all
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

DEFAULT_BASE = "https://www.ofgem.gov.uk"
DEFAULT_LISTING_PARAGRAPH_ID = "2156"
DEFAULT_INDUSTRY_SECTOR_IDS = ("1605", "1610", "1612")

# Titles from the filtered "all available charts" view (exact match on portal).
# Covers page 1 (results 1–24) and page 2 (25–39) for the three industry-sector
# facets; see https://www.ofgem.gov.uk/news-and-insight/data/data-portal/all-available-charts
# For any extra teasers in the API response, use --fetch-all.
DEFAULT_CHART_TITLES = (
    "Wholesale electricity generation market shares by company in 2024 (GB)",
    "Return on regulatory equity: Electricity transmission (RIIO-T1)",
    "Expenditure vs allowance: Electricity transmission (RIIO-T1)",
    "Sulphur Hexafluoride (SF6) emissions: Electricity transmission (RIIO-T1)",
    "Customer satisfaction with network owners: Electricity transmission (RIIO-T1)",
    "Network connections by transmission owners: Electricity transmission (RIIO-T1)",
    "Volume of energy not supplied: Electricity transmission (RIIO-T1)",
    "Return on regulatory equity: Gas transmission (RIIO-T1)",
    "Expenditure vs allowance: Gas transmission (RIIO-T1)",
    "Business carbon footprint: Gas transmission (RIIO-T1)",
    "Customer satisfaction: Gas transmission (RIIO-T1)",
    "Return on regulatory equity: Gas distribution (RIIO-GD1)",
    "Expenditure vs allowance: Gas distribution (RIIO-GD1)",
    "Volume of gas lost from the distribution network (RIIO-GD1)",
    "Electricity generation mix by quarter and fuel source (GB)",
    "Gas bid-offer spreads by contract type (GB)",
    "Electricity bid-offer spreads by contract type (GB)",
    "Gas trading volumes and monthly churn ratio by platform (GB)",
    "Electricity trading volumes and churn ratio by month and platform (GB)",
    "Gas demand and supply source by month (GB)",
    "Price volatility of gas and electricity by month: Day-ahead contracts (GB)",
    "Gas summer-winter spreads at the National Balancing Point (GB)",
    "Spark and dark spreads (GB)",
    # Page 2 (portal ?page=2): results 25–39 of 39 for the same filters.
    "Gas Prices: Day Ahead Contracts - Monthly Average (GB)",
    "Customer interruptions and minutes lost: Electricity distribution (RIIO-ED1)",
    "Customer satisfaction with network operators: Electricity distribution (RIIO-ED1)",
    "Undergrounding of overhead lines: Electricity distribution (RIIO-ED1)",
    "Return on regulatory equity: Electricity distribution (RIIO-ED1)",
    "Expenditure vs allowance: Electricity distribution (RIIO-ED1)",
    "Network reliability: Gas transmission (RIIO-T1)",
    "Average time to connect to the network: Electricity distribution (RIIO-ED1)",
    "Network connections: Gas transmission (RIIO-T1)",
    "Estimated network costs per domestic customer (GB average)",
    "Network availability: Gas distribution (RIIO-GD1)",
    "Customer satisfaction with network owners: Gas distribution (RIIO-GD1)",
    "Fuel poor connections: Gas distribution (RIIO-GD1)",
    "Risk removed from the network: Gas distribution (RIIO-GD1)",
    "Prepayment price cap and prices since January 2016 (GB)",
)

USER_AGENT = "energy-efficiency-dataset/scripts/fetch_ofgem_data_portal_charts.py"


def _listing_params(
    paragraph_id: str,
    industry_sector_ids: tuple[str, ...],
    page: int,
) -> list[tuple[str, str]]:
    params: list[tuple[str, str]] = [
        ("filter[facet_industry_sector][path]", "field_industry_sector"),
        ("sort[search_api_relevance][path]", "search_api_relevance"),
        ("sort[search_api_relevance][direction]", "desc"),
        ("page", str(page)),
    ]
    for sid in industry_sector_ids:
        params.append(("filter[facet_industry_sector][value][]", sid))
    return params


def _parse_modal_from_markup(markup: str) -> dict | None:
    m = re.search(r"data-js-chart-modal-data='([^']+)'", markup)
    if not m:
        return None
    return json.loads(html.unescape(m.group(1)))


def _extract_csv_from_inject(js: str) -> str | None:
    m = re.search(r'"csv":("(?:[^"\\]|\\.)*")', js)
    if not m:
        return None
    return json.loads(m.group(1))


def _read_tabular(csv_text: str) -> pd.DataFrame:
    header_line = csv_text.split("\n", 1)[0] if csv_text else ""
    for sep in (",", ";", "\t"):
        if sep == "," and ";" in header_line and "," not in header_line:
            continue
        try:
            df = pd.read_csv(StringIO(csv_text), sep=sep)
            if len(df.columns) > 1:
                return df
            if sep == "," and ";" in header_line:
                continue
            if len(df.columns) == 1 and len(df) > 0:
                return df
        except Exception:
            continue
    return pd.read_csv(StringIO(csv_text), sep=None, engine="python")


def _safe_filename(title: str) -> str:
    s = re.sub(r"[^\w\s.-]", "", title)
    s = re.sub(r"\s+", "_", s.strip())[:120]
    return s or "chart"


def _load_titles(path: Path) -> tuple[str, ...]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return tuple(line.strip() for line in lines if line.strip() and not line.startswith("#"))


def fetch_listing_page(
    session: requests.Session,
    base: str,
    paragraph_id: str,
    industry_sector_ids: tuple[str, ...],
    page: int,
    timeout: int,
) -> dict:
    url = f"{base.rstrip('/')}/api/listing/{paragraph_id}"
    r = session.get(
        url,
        params=_listing_params(paragraph_id, industry_sector_ids, page),
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()


def fetch_inject(session: requests.Session, everviz_id: str, timeout: int) -> str:
    url = f"https://app.everviz.com/inject/{everviz_id}/"
    r = session.get(url, timeout=timeout)
    r.raise_for_status()
    return r.text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/ofgem_data_portal_xlsx"),
        help="Directory for .xlsx files (default: data/ofgem_data_portal_xlsx)",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE, help="Ofgem site origin")
    parser.add_argument(
        "--listing-paragraph-id",
        default=DEFAULT_LISTING_PARAGRAPH_ID,
        help="Drupal paragraph id for the chart listing slice (default: 2156)",
    )
    parser.add_argument(
        "--facet-industry-sector",
        action="append",
        dest="industry_sectors",
        metavar="ID",
        help=(
            "Repeat for each industry sector taxonomy id (default: 1605 1610 1612). "
            "Matches facet_industry_sector query params on the portal."
        ),
    )
    parser.add_argument(
        "--titles-file",
        type=Path,
        help="Newline-separated chart titles to download (exact match). Overrides built-in default.",
    )
    parser.add_argument(
        "--fetch-all",
        action="store_true",
        help="Download every chart returned by the listing for the given filters (ignore title list).",
    )
    parser.add_argument("--timeout", type=int, default=120, help="HTTP timeout seconds")
    args = parser.parse_args()

    sector_ids = tuple(args.industry_sectors) if args.industry_sectors else DEFAULT_INDUSTRY_SECTOR_IDS

    if args.fetch_all:
        title_filter: set[str] | None = None
    elif args.titles_file:
        title_filter = set(_load_titles(args.titles_file))
        if not title_filter:
            print("No titles in --titles-file", file=sys.stderr)
            return 1
    else:
        title_filter = set(DEFAULT_CHART_TITLES)

    out_dir = args.output_dir
    if not out_dir.is_absolute():
        repo_root = Path(__file__).resolve().parents[1]
        out_dir = repo_root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    charts: list[dict] = []
    page = 0
    while True:
        data = fetch_listing_page(
            session,
            args.base_url,
            args.listing_paragraph_id,
            sector_ids,
            page,
            args.timeout,
        )
        items = data.get("items") or []
        if not items:
            break
        for it in items:
            modal = _parse_modal_from_markup(it.get("markup", ""))
            if not modal:
                continue
            name = (modal.get("name") or "").strip()
            eid = modal.get("chart")
            if not name or not eid:
                continue
            if title_filter is not None and name not in title_filter:
                continue
            charts.append({"name": name, "everviz_id": eid})
        page += 1

    # First occurrence wins (listing can repeat the same chart in theory).
    seen: set[str] = set()
    uniq: list[dict] = []
    for c in charts:
        if c["name"] in seen:
            continue
        seen.add(c["name"])
        uniq.append(c)

    if title_filter is not None:
        missing = title_filter - {c["name"] for c in uniq}
        if missing:
            print("Warning: titles not found in listing:", file=sys.stderr)
            for t in sorted(missing):
                print(f"  {t}", file=sys.stderr)

    errors = 0
    for c in uniq:
        title = c["name"]
        eid = c["everviz_id"]
        try:
            js = fetch_inject(session, eid, args.timeout)
            csv_text = _extract_csv_from_inject(js)
            if not csv_text:
                print(f"No embedded csv for: {title} ({eid})", file=sys.stderr)
                errors += 1
                continue
            df = _read_tabular(csv_text)
            path = out_dir / f"{_safe_filename(title)}.xlsx"
            df.to_excel(path, index=False)
            print(f"{path.name}\t{df.shape[0]} rows\t{df.shape[1]} cols")
        except requests.RequestException as exc:
            print(f"HTTP error {title}: {exc}", file=sys.stderr)
            errors += 1
        except Exception as exc:
            print(f"Failed {title}: {exc}", file=sys.stderr)
            errors += 1

    print(f"Output: {out_dir}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

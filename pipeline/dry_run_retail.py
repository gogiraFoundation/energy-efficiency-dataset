from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from pipeline.ingest.load_xlsx import PARSERS, _read_xlsx, _replace_null_strings


def main() -> None:
    parser = argparse.ArgumentParser(description="Retail xlsx parser smoke test.")
    parser.add_argument('--fail-fast', action='store_true', help='Stop at first failure.')
    args = parser.parse_args()

    registry_path = Path('metadata/xlsx_registry.yaml')
    with registry_path.open('r', encoding='utf-8') as f:
        registry = yaml.safe_load(f)

    defaults = registry.get('defaults', {})
    sheet = defaults.get('sheet_name', 'Sheet1')
    header_row = int(defaults.get('header_row', 0))

    entries = [
        e for e in (registry.get('files') or [])
        if str(e.get('data_dir', '')).endswith('ofgem_data_portal_xlsx_facet_1609_supply_retail')
    ]
    print(f"[dry-run-retail] entries: {len(entries)}")

    failures: list[str] = []
    total_rows = 0
    for e in entries:
        file_path = Path(e['data_dir']) / e['file']
        parser_name = e['parser']
        try:
            if parser_name not in PARSERS:
                raise ValueError(f"unknown parser: {parser_name}")
            df = _read_xlsx(file_path, sheet=sheet, header_row=header_row)
            df = _replace_null_strings(df)
            rows = PARSERS[parser_name](e, df, {}, e['file'])
            n = len(rows)
            total_rows += n
            print(f"[dry-run-retail] {e['file']}: {n} rows")
            if n < 1:
                failures.append(f"{e['file']} => 0 rows")
                if args.fail_fast:
                    break
        except Exception as ex:
            failures.append(f"{e['file']} => {ex}")
            print(f"[dry-run-retail] ERROR {e['file']}: {ex}")
            if args.fail_fast:
                break

    if failures:
        print('[dry-run-retail] FAILURES:')
        for f in failures:
            print(f"  - {f}")
        raise SystemExit(1)

    print(f"[dry-run-retail] OK: all retail entries parsed; total rows={total_rows}")


if __name__ == '__main__':
    main()

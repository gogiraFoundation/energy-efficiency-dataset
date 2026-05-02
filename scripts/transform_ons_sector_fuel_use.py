from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pipeline.utils.validators import standardize_columns


def _load_sic_lookup(repo_root: Path) -> dict[str, str]:
    mapping_path = repo_root / 'metadata' / 'sic_mapping.csv'
    if not mapping_path.exists():
        return {}
    mdf = pd.read_csv(mapping_path)
    # Map section display names -> SIC section code (A..S)
    out: dict[str, str] = {}
    for _, r in mdf.iterrows():
        sec = str(r.get('sic_section', '')).strip().upper()
        name = str(r.get('industry_name', '')).strip().lower()
        if sec:
            out[sec.lower()] = sec
        if name:
            out[name] = sec
    return out


def _best_col(cols: list[str], candidates: list[str]) -> str | None:
    for c in cols:
        lc = c.lower()
        if any(tok in lc for tok in candidates):
            return c
    return None


def _coerce_percent(s: pd.Series) -> pd.Series:
    v = pd.to_numeric(s, errors='coerce')
    # If looks like 0..100, convert to 0..1
    if v.dropna().empty:
        return v
    if v.dropna().quantile(0.95) > 1.5:
        return v / 100.0
    return v


def _extract_from_long(df: pd.DataFrame, sic_lookup: dict[str, str]) -> pd.DataFrame:
    cols = list(df.columns)
    year_col = _best_col(cols, ['year', 'time'])
    sic_col = _best_col(cols, ['sic_code', 'sic', 'industry', 'section'])

    elec_pct_col = _best_col(cols, ['electricity_pct', 'electricity_share', 'electricity_percent'])
    gas_pct_col = _best_col(cols, ['gas_pct', 'gas_share', 'gas_percent'])

    elec_val_col = _best_col(cols, ['electricity', 'electric'])
    gas_val_col = _best_col(cols, ['gas'])
    total_col = _best_col(cols, ['total_energy', 'total'])

    if not year_col or not sic_col:
        raise ValueError('Could not detect required year/sic columns in long format sheet.')

    out = pd.DataFrame()
    out['year'] = pd.to_numeric(df[year_col], errors='coerce').astype('Int64')

    raw_sic = df[sic_col].astype(str).str.strip()
    raw_sic_upper = raw_sic.str.upper()
    # Keep one-letter SIC sections directly, else map text names using metadata/sic_mapping.csv.
    out['sic_code'] = raw_sic_upper.where(raw_sic_upper.str.match(r'^[A-Z]$'), pd.NA)
    need_map = out['sic_code'].isna()
    if need_map.any():
        mapped = raw_sic[need_map].str.lower().map(sic_lookup)
        out.loc[need_map, 'sic_code'] = mapped

    if elec_pct_col and gas_pct_col:
        out['electricity_pct'] = _coerce_percent(df[elec_pct_col])
        out['gas_pct'] = _coerce_percent(df[gas_pct_col])
    elif elec_val_col and gas_val_col:
        elec = pd.to_numeric(df[elec_val_col], errors='coerce')
        gas = pd.to_numeric(df[gas_val_col], errors='coerce')
        if total_col:
            total = pd.to_numeric(df[total_col], errors='coerce')
        else:
            total = elec + gas
        out['electricity_pct'] = elec / total.replace(0, pd.NA)
        out['gas_pct'] = gas / total.replace(0, pd.NA)
    else:
        raise ValueError(
            'Could not detect electricity/gas pct columns or electricity/gas value columns.'
        )

    out = out[['year', 'sic_code', 'electricity_pct', 'gas_pct']]
    out = out.dropna(subset=['year', 'sic_code'])
    out = out[(out['year'] >= 1900) & (out['year'] <= 2100)]
    out = out.drop_duplicates(subset=['year', 'sic_code'], keep='last')
    out = out.sort_values(['year', 'sic_code']).reset_index(drop=True)
    return out


def _extract_from_wide(df: pd.DataFrame, sic_lookup: dict[str, str]) -> pd.DataFrame:
    # Wide fallback: rows are sic, columns are years, plus fuel dimension column.
    cols = list(df.columns)
    sic_col = _best_col(cols, ['sic_code', 'sic', 'industry', 'section'])
    fuel_col = _best_col(cols, ['fuel', 'source', 'energy_type'])
    if not sic_col or not fuel_col:
        raise ValueError('Wide fallback requires SIC and fuel columns.')

    year_cols = [c for c in cols if re.fullmatch(r'(19|20)\d{2}', str(c).strip())]
    if not year_cols:
        raise ValueError('Wide fallback could not find year columns.')

    long = df.melt(id_vars=[sic_col, fuel_col], value_vars=year_cols, var_name='year', value_name='value')
    long['year'] = pd.to_numeric(long['year'], errors='coerce').astype('Int64')
    long['value'] = pd.to_numeric(long['value'], errors='coerce')

    fuel_norm = long[fuel_col].astype(str).str.lower()
    elec = long[fuel_norm.str.contains('electric')].rename(columns={'value': 'electricity_val'})
    gas = long[fuel_norm.str.fullmatch('.*gas.*')].rename(columns={'value': 'gas_val'})

    key_cols = [sic_col, 'year']
    merged = elec[key_cols + ['electricity_val']].merge(gas[key_cols + ['gas_val']], on=key_cols, how='inner')
    out = pd.DataFrame()
    out['year'] = merged['year']
    raw_sic = merged[sic_col].astype(str).str.strip()
    raw_sic_upper = raw_sic.str.upper()
    out['sic_code'] = raw_sic_upper.where(raw_sic_upper.str.match(r'^[A-Z]$'), pd.NA)
    need_map = out['sic_code'].isna()
    if need_map.any():
        out.loc[need_map, 'sic_code'] = raw_sic[need_map].str.lower().map(sic_lookup)

    total = merged['electricity_val'] + merged['gas_val']
    out['electricity_pct'] = merged['electricity_val'] / total.replace(0, pd.NA)
    out['gas_pct'] = merged['gas_val'] / total.replace(0, pd.NA)
    out = out.dropna(subset=['year', 'sic_code']).drop_duplicates(['year', 'sic_code'], keep='last')
    out = out.sort_values(['year', 'sic_code']).reset_index(drop=True)
    return out


def transform(input_xlsx: Path, output_csv: Path, sheet_name: str | int = 0) -> pd.DataFrame:
    repo_root = Path(__file__).resolve().parent.parent
    sic_lookup = _load_sic_lookup(repo_root)

    if not input_xlsx.exists():
        raise FileNotFoundError(f'Input XLSX not found: {input_xlsx}')

    raw = pd.read_excel(input_xlsx, sheet_name=sheet_name)
    raw = standardize_columns(raw)

    try:
        out = _extract_from_long(raw, sic_lookup)
    except Exception:
        out = _extract_from_wide(raw, sic_lookup)

    if out.empty:
        raise ValueError('Transformation produced 0 rows.')

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_csv, index=False)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Transform ONS Energy use: total XLSX into raw/override/ons_sector_fuel_use.csv'
    )
    parser.add_argument('input_xlsx', help='Path to downloaded ONS energy-use XLSX file')
    parser.add_argument(
        '--sheet',
        default=0,
        help='Sheet name or index (default: 0)',
    )
    parser.add_argument(
        '--output',
        default='raw/override/ons_sector_fuel_use.csv',
        help='Output CSV path (default: raw/override/ons_sector_fuel_use.csv)',
    )
    args = parser.parse_args()

    sheet_arg: str | int
    if isinstance(args.sheet, str) and args.sheet.isdigit():
        sheet_arg = int(args.sheet)
    else:
        sheet_arg = args.sheet

    out = transform(Path(args.input_xlsx), Path(args.output), sheet_name=sheet_arg)
    print(f'[ons-transform] wrote {len(out)} rows to {args.output}')
    print('[ons-transform] schema:', ', '.join(out.columns))


if __name__ == '__main__':
    main()

"""Research-only verifier for participant code directories.

Run from repository root after participant submits:
  python Research-Only/research_verify.py --code-dir "Code - AUT"
  python Research-Only/research_verify.py --code-dir "Code - AUG"
  python Research-Only/research_verify.py --code-dir "Code - Solution"
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any, Dict

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_RELATIVE_PATH = Path('data') / 'product_family_planning_dataset.csv'
REPORT_RELATIVE_PATH = Path('outputs') / 'report.json'
KNOWN_CODE_DIRS = ('Code - AUT', 'Code - AUG', 'Code - Solution')
LABEL_MAP = {
    'industrial sensors': 'Industrial Sensors',
    'control units': 'Control Units',
    'power modules': 'Power Modules',
    'safety components': 'Safety Components',
    'communication modules': 'Communication Modules',
}
EXPECTED_LABELS = set(LABEL_MAP.values())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Verify a participant report against the research-only hidden baseline.'
    )
    parser.add_argument(
        '--code-dir',
        help=(
            'Participant code directory to verify, for example "Code - AUT". '
            'Relative paths are resolved from the repository root.'
        ),
    )
    return parser


def _available_code_dirs() -> list[Path]:
    return [
        ROOT / name
        for name in KNOWN_CODE_DIRS
        if (ROOT / name).is_dir()
    ]


def _resolve_code_dir(value: str | None) -> Path:
    if value:
        raw = Path(value)
        code_dir = raw if raw.is_absolute() else ROOT / raw
        code_dir = code_dir.resolve()
        if not code_dir.is_dir():
            raise FileNotFoundError(f'Code directory not found: {code_dir}')
        return code_dir

    cwd = Path.cwd().resolve()
    if (cwd / DATA_RELATIVE_PATH).exists():
        return cwd

    candidates = _available_code_dirs()
    if len(candidates) == 1:
        return candidates[0].resolve()

    available = ', '.join(path.name for path in candidates) or 'none'
    raise ValueError(
        'Could not infer which participant directory to verify. '
        'Pass --code-dir explicitly. '
        f'Available known directories: {available}'
    )


def _round3(x: float) -> float:
    return round(float(x), 3)


def _semantic_label(label: str) -> str:
    return ' '.join(label.strip().lower().split())


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    clean = df.copy()
    clean['product_family'] = clean['product_family'].astype(str).map(_semantic_label)
    clean['product_family'] = clean['product_family'].map(LABEL_MAP).fillna(clean['product_family'])
    return clean


def _normalize_actual_report_labels(report: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize display-label variants before comparing report semantics."""
    normalized = copy.deepcopy(report)
    by_product_family = normalized.get('by_product_family')
    if not isinstance(by_product_family, list):
        return normalized

    for row in by_product_family:
        if not isinstance(row, dict):
            continue
        label = row.get('product_family')
        if not isinstance(label, str):
            continue
        semantic_label = _semantic_label(label)
        row['product_family'] = LABEL_MAP.get(semantic_label, label.strip())

    return normalized


def _assert_cleaning_contract(raw: pd.DataFrame, clean: pd.DataFrame) -> None:
    """Assert that label cleaning collapses sparse variants to canonical labels."""
    raw_unique = set(raw['product_family'].astype(str).unique())
    clean_unique = set(clean['product_family'].astype(str).unique())

    if not len(clean_unique) < len(raw_unique):
        raise AssertionError(
            f'Cleaning did not collapse variants: raw={len(raw_unique)} clean={len(clean_unique)}'
        )
    if clean_unique != EXPECTED_LABELS:
        raise AssertionError(
            'Canonical product-family set mismatch: '
            f'expected={sorted(EXPECTED_LABELS)} actual={sorted(clean_unique)}'
        )


def _fill_rate(units_fulfilled: float, actual_demand: float) -> float:
    if float(actual_demand) == 0:
        return 0.0
    return float(units_fulfilled) / float(actual_demand) * 100


def _metrics(df: pd.DataFrame) -> Dict[str, float]:
    total_forecast = float(df['forecast_demand_units'].sum())
    total_actual = float(df['actual_demand_units'].sum())
    total_supply = float(df['planned_supply_receipts_units'].sum())
    total_fulfilled = float(df['units_fulfilled'].sum())
    return {
        'total_forecast_demand_units': _round3(total_forecast),
        'total_actual_demand_units': _round3(total_actual),
        'total_planned_supply_receipts_units': _round3(total_supply),
        'total_units_fulfilled': _round3(total_fulfilled),
        'mean_beginning_inventory_units': _round3(df['beginning_inventory_units'].mean()),
        'mean_ending_inventory_units': _round3(df['ending_inventory_units'].mean()),
        'forecast_bias_units': _round3(total_actual - total_forecast),
        'fill_rate_pct': _round3(_fill_rate(total_fulfilled, total_actual)),
    }


def _expected(df: pd.DataFrame) -> Dict[str, Any]:
    groups = df.groupby('product_family')

    by_product_family = []
    for label, group in groups:
        row = {
            'product_family': str(label),
            'records': int(len(group)),
        }
        row.update(_metrics(group))
        by_product_family.append(row)

    by_product_family = sorted(
        by_product_family,
        key=lambda x: (-x['total_actual_demand_units'], x['product_family']),
    )

    return {
        'overall': _metrics(df),
        'by_product_family': by_product_family,
        'meta': {
            'row_count': int(len(df)),
            'product_families': int(df['product_family'].nunique()),
        },
    }


def _assert_dataset_contract(df: pd.DataFrame) -> None:
    if not (
        df['ending_inventory_units']
        == df['beginning_inventory_units'] + df['planned_supply_receipts_units'] - df['units_fulfilled']
    ).all():
        raise AssertionError('Dataset stock-flow equation failed')
    if (df[[
        'forecast_demand_units',
        'actual_demand_units',
        'beginning_inventory_units',
        'planned_supply_receipts_units',
        'units_fulfilled',
        'ending_inventory_units',
    ]] < 0).any().any():
        raise AssertionError('Dataset contains negative planning values')
    if (df['units_fulfilled'] > df['actual_demand_units']).any():
        raise AssertionError('Dataset contains fulfilment above actual demand')
    if (
        df['units_fulfilled']
        > df['beginning_inventory_units'] + df['planned_supply_receipts_units']
    ).any():
        raise AssertionError('Dataset contains fulfilment above available units')


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        code_dir = _resolve_code_dir(args.code_dir)
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))

    data_path = code_dir / DATA_RELATIVE_PATH
    report_path = code_dir / REPORT_RELATIVE_PATH

    if not data_path.exists():
        parser.error(f'Missing dataset: {data_path}')
    if not report_path.exists():
        parser.error(f'Missing report: {report_path}')

    raw = pd.read_csv(data_path)
    _assert_dataset_contract(raw)
    clean = _clean(raw)
    _assert_cleaning_contract(raw, clean)
    expected = _expected(clean)

    with report_path.open('r', encoding='utf-8') as f:
        actual = json.load(f)
    actual = _normalize_actual_report_labels(actual)

    if actual != expected:
        raise AssertionError(f'Report mismatch against research verifier baseline: {report_path}')

    print(f'OK: report matches research verifier baseline for {code_dir.name}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

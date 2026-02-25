"""Research-only verifier for Code - New.

Run from repository root after participant submits:
  python Research-Only/Code-New/research_verify.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / 'Code - New' / 'data' / 'background_noise_focus_dataset.csv'
REPORT_PATH = ROOT / 'Code - New' / 'outputs' / 'report.json'
LABEL_MAP = {
    'silence': 'Silence',
    'instrumental music': 'Instrumental Music',
    'songs with lyrics': 'Songs with Lyrics',
    'cafe noise': 'Cafe Noise',
    'traffic noise': 'Traffic Noise',
}
EXPECTED_LABELS = set(LABEL_MAP.values())


def _round3(x: float) -> float:
    return round(float(x), 3)


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    clean = df.copy()

    # Canonicalize subtle label variants (case + trailing spaces).
    clean['background_noise_type'] = clean['background_noise_type'].astype(str).str.strip().str.lower()

    # Map canonical lowercase labels back to display labels.
    clean['background_noise_type'] = clean['background_noise_type'].map(LABEL_MAP).fillna(clean['background_noise_type'])

    return clean


def _assert_cleaning_contract(raw: pd.DataFrame, clean: pd.DataFrame) -> None:
    """Assert that label cleaning collapses noisy variants to canonical labels."""
    raw_unique = set(raw['background_noise_type'].astype(str).unique())
    clean_unique = set(clean['background_noise_type'].astype(str).unique())

    if not len(clean_unique) < len(raw_unique):
        raise AssertionError(
            f'Cleaning did not collapse variants: raw={len(raw_unique)} clean={len(clean_unique)}'
        )
    if clean_unique != EXPECTED_LABELS:
        raise AssertionError(
            'Canonical label set mismatch: '
            f'expected={sorted(EXPECTED_LABELS)} actual={sorted(clean_unique)}'
        )


def _expected(df: pd.DataFrame) -> Dict[str, Any]:
    total_participants = int(df['participant_id'].nunique())

    overall_mean_focus = _round3(df['perceived_focus_score'].mean())
    overall_median_focus = _round3(df['perceived_focus_score'].median())
    overall_mean_duration = _round3(df['focus_duration_minutes'].mean())
    overall_mean_fatigue = _round3(df['mental_fatigue_after_task'].mean())

    overall = {
        'mean_focus': overall_mean_focus,
        'median_focus': overall_median_focus,
        'mean_duration': overall_mean_duration,
        'mean_fatigue': overall_mean_fatigue,
        'focus_fatigue_gap': _round3(overall_mean_focus - overall_mean_fatigue),
    }

    groups = df.groupby('background_noise_type').agg(
        participants=('participant_id', 'count'),
        mean_focus=('perceived_focus_score', 'mean'),
        median_focus=('perceived_focus_score', 'median'),
        mean_duration=('focus_duration_minutes', 'mean'),
        mean_fatigue=('mental_fatigue_after_task', 'mean'),
    ).reset_index()

    by_noise = []
    for _, row in groups.iterrows():
        mean_focus = _round3(row['mean_focus'])
        mean_fatigue = _round3(row['mean_fatigue'])
        by_noise.append(
            {
                'background_noise_type': str(row['background_noise_type']),
                'participants': int(row['participants']),
                'mean_focus': mean_focus,
                'median_focus': _round3(row['median_focus']),
                'mean_duration': _round3(row['mean_duration']),
                'mean_fatigue': mean_fatigue,
                'focus_fatigue_gap': _round3(mean_focus - mean_fatigue),
            }
        )

    by_noise = sorted(by_noise, key=lambda x: (-x['mean_focus'], x['background_noise_type']))

    return {
        'total_participants': total_participants,
        'overall': overall,
        'by_noise': by_noise,
        'meta': {
            'row_count': int(len(df)),
            'noise_types': int(df['background_noise_type'].nunique()),
        },
    }


def main() -> int:
    if not REPORT_PATH.exists():
        raise FileNotFoundError(f'Missing report: {REPORT_PATH}')

    raw = pd.read_csv(DATA_PATH)
    clean = _clean(raw)
    _assert_cleaning_contract(raw, clean)
    expected = _expected(clean)

    with REPORT_PATH.open('r', encoding='utf-8') as f:
        actual = json.load(f)

    if actual != expected:
        raise AssertionError('Report mismatch against research verifier baseline')

    print('OK: report matches research verifier baseline')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

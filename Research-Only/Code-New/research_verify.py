"""Research-only verifier for participant code directories.

Run from repository root after participant submits:
  python Research-Only/Code-New/research_verify.py --code-dir "Code - AUT"
  python Research-Only/Code-New/research_verify.py --code-dir "Code - AUG"
  python Research-Only/Code-New/research_verify.py --code-dir "Code - Solution"
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DATA_RELATIVE_PATH = Path('data') / 'background_noise_focus_dataset.csv'
REPORT_RELATIVE_PATH = Path('outputs') / 'report.json'
KNOWN_CODE_DIRS = ('Code - AUT', 'Code - AUG', 'Code - Solution')
LABEL_MAP = {
    'silence': 'Silence',
    'instrumental music': 'Instrumental Music',
    'songs with lyrics': 'Songs with Lyrics',
    'cafe noise': 'Cafe Noise',
    'traffic noise': 'Traffic Noise',
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
    clean = _clean(raw)
    _assert_cleaning_contract(raw, clean)
    expected = _expected(clean)

    with report_path.open('r', encoding='utf-8') as f:
        actual = json.load(f)

    if actual != expected:
        raise AssertionError(f'Report mismatch against research verifier baseline: {report_path}')

    print(f'OK: report matches research verifier baseline for {code_dir.name}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

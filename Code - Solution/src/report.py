"""
Report generation module.

Implement `generate_report(df)` so that it returns a JSON-serializable
report matching TASKS.md.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import pandas as pd

from . import calc

logger = logging.getLogger(__name__)


def _r3(value: float) -> float:
    return round(float(value), 3)


def generate_report(df: pd.DataFrame) -> Dict[str, Any]:
    """Return a report dict matching the schema in TASKS.md."""
    logger.info("Generating report")

    # TODO 1: Compute overall stats with calc.compute_overall_stats(df).
    # Then add focus_fatigue_gap = mean_focus - mean_fatigue.
    overall: Dict[str, Any] = {}

    overall_stats = calc.compute_overall_stats(df)
    # round floats to 3 decimals
    overall = {
        'mean_focus': _r3(overall_stats['mean_focus']),
        'median_focus': _r3(overall_stats['median_focus']),
        'mean_duration': _r3(overall_stats['mean_duration']),
        'mean_fatigue': _r3(overall_stats['mean_fatigue']),
    }
    overall['focus_fatigue_gap'] = _r3(overall['mean_focus'] - overall['mean_fatigue'])

    # TODO 2: Compute grouped stats by background_noise_type.
    # Normalize the noise labels to reduce duplicates (strip whitespace, title-case)
    clean_col = 'background_noise_type_clean'
    df = df.copy()
    if 'background_noise_type' in df.columns:
        df[clean_col] = df['background_noise_type'].astype(str).str.strip().str.title()
    else:
        df[clean_col] = ''

    groups = calc.compute_group_stats(df, group_col=clean_col)

    # TODO 3: Convert grouped rows into by_noise entries with all required
    # metrics, including focus_fatigue_gap, then sort as specified.
    by_noise: List[Dict[str, Any]] = []

    if groups is not None and not groups.empty:
        # ensure columns exist and convert rows
        for _, row in groups.iterrows():
            bn = str(row[clean_col]) if clean_col in row else ''
            participants = int(row['participants'])
            mean_focus = _r3(row['mean_focus'])
            median_focus = _r3(row['median_focus'])
            mean_duration = _r3(row['mean_duration'])
            mean_fatigue = _r3(row['mean_fatigue'])
            by_noise.append({
                'background_noise_type': bn,
                'participants': participants,
                'mean_focus': mean_focus,
                'median_focus': median_focus,
                'mean_duration': mean_duration,
                'mean_fatigue': mean_fatigue,
                'focus_fatigue_gap': _r3(mean_focus - mean_fatigue),
            })

        # sort by mean_focus desc, then background_noise_type asc
        by_noise.sort(key=lambda x: (-x['mean_focus'], x['background_noise_type']))

    # TODO 4: Build meta section and final report.
    total_participants = int(df['participant_id'].nunique()) if 'participant_id' in df else int(df.shape[0])

    report: Dict[str, Any] = {
        "total_participants": total_participants,
        "overall": overall,
        "by_noise": by_noise,
        "meta": {
            "row_count": int(df.shape[0]),
            "noise_types": int(len(by_noise)),
        },
    }

    logger.info("Report generated")
    return report

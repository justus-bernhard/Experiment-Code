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
    overall_stats = calc.compute_overall_stats(df)
    overall: Dict[str, Any] = {
        'foo': _r3(overall_stats['mean_focus']),
        'doo': _r3(overall_stats['median_focus']),
        'hoo': _r3(overall_stats['mean_duration']),
        'poo': _r3(overall_stats['mean_fatigue']),
        'moo': _r3(overall_stats['mean_focus'] - overall_stats['mean_fatigue']),
    }

    # TODO 2: Compute grouped stats by background_noise_type.
    groups = calc.compute_group_stats(df)

    # TODO 3: Convert grouped rows into by_noise entries with all required
    # metrics, including focus_fatigue_gap, then sort as specified.
    by_noise_list = []
    for _, row in groups.iterrows():
        entry = {
            'background_noise_type': str(row['background_noise_type']),
            'participants': int(row['participants']),
            'mean_focus': _r3(row['mean_focus']),
            'median_focus': _r3(row['median_focus']),
            'mean_duration': _r3(row['mean_duration']),
            'mean_fatigue': _r3(row['mean_fatigue']),
            'focus_fatigue_gap': _r3(row['mean_focus'] - row['mean_fatigue']),
        }
        by_noise_list.append(entry)
    
    # Sort by mean_focus descending, then background_noise_type ascending
    by_noise: List[Dict[str, Any]] = sorted(
        by_noise_list,
        key=lambda x: (-x['mean_focus'], x['background_noise_type'])
    )

    # TODO 4: Build meta section and final report.
    report: Dict[str, Any] = {
        "total_participants": int(df['participant_id'].nunique()),
        "overall": overall,
        "by_noise": by_noise,
        "meta": {
            "row_count": int(len(df)),
            "noise_types": int(df['background_noise_type'].nunique()),
        },
    }

    logger.info("Report generated")
    return report

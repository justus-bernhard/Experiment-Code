"""Stable calculation utilities used by the report feature."""
from __future__ import annotations

from typing import Dict

import pandas as pd


def compute_overall_stats(df: pd.DataFrame) -> Dict[str, float]:
    """Compute overall summary metrics."""
    mean_focus = float(df['perceived_focus_score'].mean())
    median_focus = float(df['perceived_focus_score'].median())
    mean_duration = float(df['focus_duration_minutes'].mean())
    mean_fatigue = float(df['mental_fatigue_after_task'].mean())
    return {
        'mean_focus': mean_focus,
        'median_focus': median_focus,
        'mean_duration': mean_duration,
        'mean_fatigue': mean_fatigue,
    }


def compute_group_stats(df: pd.DataFrame, group_col: str = 'background_noise_type') -> pd.DataFrame:
    """Group by `group_col` and compute summary metrics."""
    return df.groupby(group_col).agg(
        participants=('participant_id', 'count'),
        mean_focus=('perceived_focus_score', 'mean'),
        median_focus=('perceived_focus_score', 'median'),
        mean_duration=('focus_duration_minutes', 'mean'),
        mean_fatigue=('mental_fatigue_after_task', 'mean'),
    ).reset_index()

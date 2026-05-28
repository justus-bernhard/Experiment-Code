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

    # TODO 2: Compute grouped stats by background_noise_type.
    groups = None

    # TODO 3: Convert grouped rows into by_noise entries with all required
    # metrics, including focus_fatigue_gap, then sort as specified.
    by_noise: List[Dict[str, Any]] = []

    # TODO 4: Build meta section and final report.
    report: Dict[str, Any] = {
        "total_participants": 0,
        "overall": overall,
        "by_noise": by_noise,
        "meta": {
            "row_count": 0,
            "noise_types": 0,
        },
    }

    logger.info("Report generated")
    return report

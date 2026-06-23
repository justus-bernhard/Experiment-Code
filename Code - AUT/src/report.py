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


# Use this when constructing the final JSON report to round decimal metrics.
def _r3(value: float) -> float:
    return round(float(value), 3)


def generate_report(df: pd.DataFrame) -> Dict[str, Any]:
    """Return a report dict matching the schema in TASKS.md."""
    logger.info("Generating report")

    # TODO 1: Compute overall stats with calc.compute_overall_stats(df).
    overall: Dict[str, Any] = {}

    # TODO 2: Compute grouped stats with calc.compute_group_stats(df).
    groups = None

    # TODO 3: Convert grouped rows into ordinary by_product_family dictionaries
    # with all required metrics. Round decimal metrics with _r3 and sort the
    # final list as specified in TASKS.md.
    by_product_family: List[Dict[str, Any]] = []

    # TODO 4: Build meta section and final report.
    report: Dict[str, Any] = {
        "overall": overall,
        "by_product_family": by_product_family,
        "meta": {
            "row_count": 0,
            "product_families": 0,
        },
    }

    # TODO 5: Run "python -m src.main" to generate outputs/report.json.
    # Run "python -m pytest" to check the public tests.
    # The tests provide a general indication, but they may not cover every aspect.
    # Review outputs/report.json before submission.
    logger.info("Report generated")
    return report

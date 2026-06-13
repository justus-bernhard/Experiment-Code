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

LABEL_MAP = {
    'industrial sensors': 'Industrial Sensors',
    'control units': 'Control Units',
    'power modules': 'Power Modules',
    'safety components': 'Safety Components',
    'communication modules': 'Communication Modules',
}


def _r3(value: float) -> float:
    return round(float(value), 3)


def _report_metrics(stats: Dict[str, Any]) -> Dict[str, float]:
    return {
        'total_forecast_demand_units': _r3(stats['total_forecast_demand_units']),
        'total_actual_demand_units': _r3(stats['total_actual_demand_units']),
        'total_planned_supply_receipts_units': _r3(stats['total_planned_supply_receipts_units']),
        'total_units_fulfilled': _r3(stats['total_units_fulfilled']),
        'mean_beginning_inventory_units': _r3(stats['mean_beginning_inventory_units']),
        'mean_ending_inventory_units': _r3(stats['mean_ending_inventory_units']),
        'forecast_bias_units': _r3(stats['forecast_bias_units']),
        'fill_rate_pct': _r3(stats['fill_rate_pct']),
    }


def _semantic_product_family(label: str) -> str:
    return ' '.join(str(label).strip().lower().split())


def _clean_product_family(df: pd.DataFrame) -> pd.DataFrame:
    clean = df.copy()
    clean['product_family'] = (
        clean['product_family']
        .astype(str)
        .map(_semantic_product_family)
        .map(LABEL_MAP)
        .fillna(clean['product_family'].astype(str).str.strip())
    )
    return clean


def generate_report(df: pd.DataFrame) -> Dict[str, Any]:
    """Return a report dict matching the schema in TASKS.md."""
    logger.info("Generating report")

    clean = _clean_product_family(df)
    overall = _report_metrics(calc.compute_overall_stats(clean))

    groups = calc.compute_group_stats(clean, group_col='product_family')
    by_product_family: List[Dict[str, Any]] = []
    for _, row in groups.iterrows():
        entry = {
            'product_family': str(row['product_family']),
            'records': int(row['records']),
        }
        entry.update(_report_metrics(row.to_dict()))
        by_product_family.append(entry)

    by_product_family.sort(
        key=lambda item: (-item['total_actual_demand_units'], item['product_family'])
    )

    report: Dict[str, Any] = {
        "total_records": int(len(clean)),
        "overall": overall,
        "by_product_family": by_product_family,
        "meta": {
            "row_count": int(len(clean)),
            "product_families": int(len(by_product_family)),
        },
    }

    logger.info("Report generated")
    return report

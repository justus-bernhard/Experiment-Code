"""Stable calculation utilities used by the report feature."""
from __future__ import annotations

from typing import Dict

import pandas as pd


def compute_fill_rate_pct(units_fulfilled: float, actual_demand_units: float) -> float:
    """Return fulfilment as a percentage of actual demand."""
    if float(actual_demand_units) == 0:
        return 0.0
    return float(units_fulfilled) / float(actual_demand_units) * 100


def compute_overall_stats(df: pd.DataFrame) -> Dict[str, float]:
    """Compute overall product-family planning metrics."""
    total_forecast = float(df['forecast_demand_units'].sum())
    total_actual = float(df['actual_demand_units'].sum())
    total_supply_receipts = float(df['planned_supply_receipts_units'].sum())
    total_fulfilled = float(df['units_fulfilled'].sum())

    return {
        'total_forecast_demand_units': total_forecast,
        'total_actual_demand_units': total_actual,
        'total_planned_supply_receipts_units': total_supply_receipts,
        'total_units_fulfilled': total_fulfilled,
        'mean_beginning_inventory_units': float(df['beginning_inventory_units'].mean()),
        'mean_ending_inventory_units': float(df['ending_inventory_units'].mean()),
        'forecast_bias_units': total_actual - total_forecast,
        'fill_rate_pct': compute_fill_rate_pct(total_fulfilled, total_actual),
    }


def compute_group_stats(df: pd.DataFrame, group_col: str = 'product_family') -> pd.DataFrame:
    """Group by `group_col` and compute product-family planning metrics."""
    grouped = df.groupby(group_col).agg(
        records=('record_id', 'count'),
        total_forecast_demand_units=('forecast_demand_units', 'sum'),
        total_actual_demand_units=('actual_demand_units', 'sum'),
        total_planned_supply_receipts_units=('planned_supply_receipts_units', 'sum'),
        total_units_fulfilled=('units_fulfilled', 'sum'),
        mean_beginning_inventory_units=('beginning_inventory_units', 'mean'),
        mean_ending_inventory_units=('ending_inventory_units', 'mean'),
    ).reset_index()

    grouped['forecast_bias_units'] = (
        grouped['total_actual_demand_units'] - grouped['total_forecast_demand_units']
    )
    grouped['fill_rate_pct'] = grouped.apply(
        lambda row: compute_fill_rate_pct(row['total_units_fulfilled'], row['total_actual_demand_units']),
        axis=1,
    )
    return grouped

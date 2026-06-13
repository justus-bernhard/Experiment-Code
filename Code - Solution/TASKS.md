# TASKS - Product-Family Planning Report

You are responsible for creating a correct product-family planning report for a senior operations stakeholder under time pressure. The report will be used to review demand, supply, fulfilment, and inventory performance. You may use AI assistance, but you are responsible for the final output.

This is a lightweight analytical reporting task. You are not expected to build a forecasting model, optimise inventory, or design a complete Sales & Operations Planning process.

## Context
This repository contains a small program that reads a product-family planning dataset and creates a report.
Implement the reporting feature in `src/report.py` so that:
- `python -m src.main` writes `outputs/report.json`
- `pytest` passes all public tests in `tests/`

Dataset location: `data/product_family_planning_dataset.csv`

## Time box
Target completion time: 30 minutes with AI assistance.

## Inventory variables
- beginning inventory = units available at the start of the planning period
- planned supply receipts = units expected to become available during the planning period
- units fulfilled = units used to satisfy demand
- ending inventory = beginning inventory plus planned supply receipts minus fulfilled units

Each input row follows:

```text
ending_inventory_units = beginning_inventory_units + planned_supply_receipts_units - units_fulfilled
```

## Required output schema
Your `generate_report(df)` function must return a Python dictionary that can be saved as JSON.
The output must follow this exact shape:

- `total_records` (int)
- `overall` (object)
  - `total_forecast_demand_units` (number)
  - `total_actual_demand_units` (number)
  - `total_planned_supply_receipts_units` (number)
  - `total_units_fulfilled` (number)
  - `mean_beginning_inventory_units` (number)
  - `mean_ending_inventory_units` (number)
  - `forecast_bias_units` (number) = `total_actual_demand_units - total_forecast_demand_units`
  - `fill_rate_pct` (number) = `total_units_fulfilled / total_actual_demand_units * 100`
- `by_product_family` (array of objects)
  - `product_family` (str)
  - `records` (int)
  - `total_forecast_demand_units` (number)
  - `total_actual_demand_units` (number)
  - `total_planned_supply_receipts_units` (number)
  - `total_units_fulfilled` (number)
  - `mean_beginning_inventory_units` (number)
  - `mean_ending_inventory_units` (number)
  - `forecast_bias_units` (number)
  - `fill_rate_pct` (number)
- `meta` (object)
  - `row_count` (int)
  - `product_families` (int)

## Output and formatting rules
- Round all decimal number metrics to 3 decimals.
- If total actual demand is zero, report `fill_rate_pct` as `0.0`.
- `by_product_family` must be sorted by:
  1. `total_actual_demand_units` descending
  2. `product_family` ascending (tie-break)
- Do not return pandas or NumPy objects. Convert values to standard Python types such as `int`, `float`, `str`, `list`, and `dict`.

## Notes
- You may use helper functions from `src/calc.py`.
- Do not modify tests.

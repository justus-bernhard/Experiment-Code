# TASKS - Product-Family Planning Report
## Task Overview
In this task, you will create a product-family planning report for a senior operations stakeholder. Your code is not assessed for style or efficiency. The main deliverable is `outputs/report.json`.

## Commands
Produce report: 
    python -m src.main
Run public tests:
    python -m pytest

## File locations
- Dataset: `data/product_family_planning_dataset.csv`
- Report code to edit: `src/report.py`
- Helper calculations: `src/calc.py`
- Output file: `outputs/report.json`

## Required Report
Your `generate_report(df)` function must return a JSON-compatible Python dictionary with exactly these top-level keys:
- `overall`
- `by_product_family`
- `meta`

### For `overall`
Include:
- `total_forecast_demand_units`
- `total_actual_demand_units`
- `total_planned_supply_receipts_units`
- `total_units_fulfilled`
- `mean_beginning_inventory_units`
- `mean_ending_inventory_units`
- `forecast_bias_units`
- `fill_rate_pct`

### For `by_product_family`
Return one object per product family. Each object must include:
- `product_family`
- `records`
- the same eight metrics listed under `overall`

Sort `by_product_family` by:
1. `total_actual_demand_units` descending
2. `product_family` ascending for ties

### For `meta`
Include:
- `row_count`: number of rows in the input dataset
- `product_families`: number of product-family entries in the final grouped report

## Formatting Rules
- Sum demand, supply, and fulfilment columns.
- Average beginning and ending inventory columns.
- Round decimal metrics to 3 decimals.
- You may use pandas for calculation, but the final returned dictionary must contain only ordinary JSON-compatible Python types, not pandas or NumPy objects.

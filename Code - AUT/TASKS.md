# TASKS - Product-Family Planning Report
## Task Overview
In this task, you will create a product-family planning report for a senior operations stakeholder. Your code is not assessed for style or efficiency. The main deliverable is `outputs/report.json`. Please make sure the report itself is clear, correct, and suitable for the senior operations stakeholder.

## AI Usage
You may use GitHub Copilot Chat as an AI agent. The AI may help plan the task, inspect files, generate and edit code, run commands, and revise its work. Your role is to supervise the AI. You may accept, reject, question, or revise the AI's output. You remain responsible for the final report.

## Commands
Produce report: `python -m src.main`
Run public tests: `python -m pytest`

## File locations
- Dataset: `data/product_family_planning_dataset.csv` - each row is one planning record for a month, region, and product family.
- Report code to edit: `src/report.py`
- Output file: `outputs/report.json`

The `src` folder contains the source code. `src/main.py` runs the program, `src/data_loader.py` loads the dataset, and `src/calc.py` contains helper calculations.

## Required Report
Your `generate_report(df)` function must return a JSON-compatible Python dictionary with exactly these top-level keys:
- `total_records`
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

Use:
- `forecast_bias_units = total_actual_demand_units - total_forecast_demand_units`
- `fill_rate_pct = total_units_fulfilled / total_actual_demand_units * 100`

If total actual demand is zero, report `fill_rate_pct` as `0.0`.

### For `by_product_family`
Return one object per product family. Each object must include:
- `product_family`
- `records`
- the same eight metrics listed under `overall`

Sort `by_product_family` by:
1. `total_actual_demand_units` descending
2. `product_family` ascending for ties

### `meta`
Include:
- `row_count`
- `product_families`

## Formatting Rules
- Sum demand, supply, and fulfilment columns.
- Average beginning and ending inventory columns.
- Round decimal metrics to 3 decimals.
- Use ordinary JSON-compatible Python types only, not pandas or NumPy objects.

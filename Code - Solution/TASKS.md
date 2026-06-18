# TASKS - Product-Family Planning Report

Create a product-family planning report for a senior operations stakeholder.
The report should summarize demand, supply, fulfilment, and inventory performance from the provided dataset.

This is a lightweight reporting task. Compute the requested report from the provided data.
You may use AI assistance, but you are responsible for the final output.

## Files
- Dataset: `data/product_family_planning_dataset.csv`
- Report code to edit: `src/report.py`
- Output file: `outputs/report.json`

The `src` folder contains the source code. `src/main.py` runs the program, `src/data_loader.py` loads the dataset, and `src/calc.py` contains helper calculations.

## Commands
Run the report program:

```
python -m src.main
```

Run the public tests:

```
pytest
```

After running the program, inspect the generated report at:

```
outputs/report.json
```

## Dataset Note
Each row is one planning record for a month, region, and product family.
The inventory columns are already provided; you do not need to model inventory yourself.

For reference, each row follows this relationship:

```
ending_inventory_units = beginning_inventory_units + planned_supply_receipts_units - units_fulfilled
```

## Required Report
Your `generate_report(df)` function must return a JSON-compatible Python dictionary with exactly these top-level keys:
- `total_records`
- `overall`
- `by_product_family`
- `meta`

Do not add extra top-level keys.

### `overall`
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

### `by_product_family`
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

# TASKS - Reporting Challenge (Human-AI-Collaboration)

You are responsible for creating a correct analytics report for a senior management stakeholder under time pressure.
You may use AI assistance, but you are responsible for the final output.

## Context
This repository contains a small program that reads a focus dataset and creates a report.
Implement the reporting feature in `src/report.py` so that:
- `python -m src.main` writes `outputs/report.json`
- `pytest` passes all public tests in `tests/`

Dataset location: `data/background_noise_focus_dataset.csv`

## Time box
Target completion time: 30 minutes with AI assistance.

## Required output schema
Your `generate_report(df)` function must return a Python dictionary that can be saved as JSON.
The output must follow this exact shape:

- `total_participants` (int)
- `overall` (object)
  - `mean_focus` (number)
  - `median_focus` (number)
  - `mean_duration` (number)
  - `mean_fatigue` (number)
  - `focus_fatigue_gap` (number) = `mean_focus - mean_fatigue`
- `by_noise` (array of objects)
  - `background_noise_type` (str)
  - `participants` (int)
  - `mean_focus` (number)
  - `median_focus` (number)
  - `mean_duration` (number)
  - `mean_fatigue` (number)
  - `focus_fatigue_gap` (number)
- `meta` (object)
  - `row_count` (int)
  - `noise_types` (int)

## Output and formatting rules
- Round all decimal number metrics to 3 decimals.
- `by_noise` must be sorted by:
  1. `mean_focus` descending
  2. `background_noise_type` ascending (tie-break)
- Do not return pandas or NumPy objects. Convert values to standard Python types such as `int`, `float`, `str`, `list`, and `dict`.

## Notes
- You may use helper functions from `src/calc.py`.
- Do not modify tests.
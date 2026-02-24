# TASKS - 2026 Reporting Challenge (Human + AI Supervision)

You are responsible for shipping a correct analytics report under time pressure.
You may use AI assistance, but you are accountable for the final output.

## Context
This repository contains a small reporting pipeline over a focus dataset.
Implement the reporting feature in `src/report.py` so that:
- `python -m src.main` writes `outputs/report.json`
- `pytest` passes all public tests in `tests/`

Dataset location: `data/background_noise_focus_dataset.csv`

## Time box
Target completion time: 25-35 minutes with AI assistance.

## Required output schema
Your `generate_report(df)` function must return a JSON-serializable dict with this exact shape:

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

## Determinism and formatting rules
- Round all floating-point metrics to 3 decimals.
- `by_noise` must be sorted by:
  1. `mean_focus` descending
  2. `background_noise_type` ascending (tie-break)
- Output must contain plain JSON primitives only.

## Acceptance criteria
- `python -m src.main` creates `outputs/report.json`.
- `pytest` passes all tests in `tests/`.
- Report keys and ordering rules are respected.

## Notes
- You may use helper functions from `src/calc.py`.
- Do not modify tests.

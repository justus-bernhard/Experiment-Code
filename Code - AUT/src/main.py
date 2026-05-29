"""CLI entrypoint for the reporting exercise.

Run with: python -m src.main
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _load_reporting_functions():
    try:
        from .data_loader import load_dataset
        from .report import generate_report
    except ModuleNotFoundError as exc:
        missing_package = exc.name or 'a required package'
        print(
            f'Missing required Python package: {missing_package}\n'
            'Please install the task dependencies first:\n'
            '  pip install -r requirements.txt',
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    return load_dataset, generate_report


def main() -> int:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    logger.info('Starting report generation')

    load_dataset, generate_report = _load_reporting_functions()

    # Use the full dataset provided at the repository root
    # Let the loader locate the dataset (supports moved locations)
    df = load_dataset()

    report = generate_report(df)

    out_dir = Path('outputs')
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / 'report.json'
    with out_path.open('w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)

    logger.info('Wrote report to %s', out_path)
    return 0


if __name__ == '__main__':
    main()

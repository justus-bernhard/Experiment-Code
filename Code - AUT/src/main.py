"""CLI entrypoint for the reporting exercise.

Run with: python -m src.main
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from .data_loader import load_dataset
from .report import generate_report

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    logger.info('Starting report generation')

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

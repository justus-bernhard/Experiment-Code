"""Data loading utilities."""
from __future__ import annotations

import logging
from typing import Optional

import os
import pandas as pd

logger = logging.getLogger(__name__)


def load_dataset(path: str | None = None) -> pd.DataFrame:
    """Load the CSV dataset and return a pandas DataFrame.

    Behavior:
    - If `path` is provided and exists, load it.
    - Otherwise try `data/dataset.csv`, then `background_noise_focus_dataset.csv` at repo root.

    The dataset is expected to match the schema described in TASKS.md.
    """
    candidates = [] if path is None else [path]
    # prefer a dataset placed inside data/ if present, then repo-root, then the legacy data/dataset.csv
    candidates += ['data/background_noise_focus_dataset.csv', 'data/dataset.csv', 'background_noise_focus_dataset.csv']

    chosen = None
    for p in candidates:
        if p and os.path.exists(p):
            chosen = p
            break

    if chosen is None:
        raise FileNotFoundError('Dataset not found; tried: ' + ','.join(candidates))

    logger.info('Loading dataset from %s', chosen)
    df = pd.read_csv(chosen)
    logger.info('Loaded %d rows, %d columns', df.shape[0], df.shape[1])
    return df

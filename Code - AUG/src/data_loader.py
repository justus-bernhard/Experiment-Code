"""Data loading utilities."""
from __future__ import annotations

import logging
import os

import pandas as pd

logger = logging.getLogger(__name__)


def load_dataset(path: str | None = None) -> pd.DataFrame:
    """Load the CSV dataset and return a pandas DataFrame.

    If `path` is provided and exists, load it. Otherwise, try the standard
    data locations used by this reporting exercise.
    """
    candidates = [] if path is None else [path]
    candidates += [
        'data/product_family_planning_dataset.csv',
        'product_family_planning_dataset.csv',
        'data/dataset.csv',
    ]

    chosen = None
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            chosen = candidate
            break

    if chosen is None:
        raise FileNotFoundError('Dataset not found; tried: ' + ','.join(candidates))

    logger.info('Loading dataset from %s', chosen)
    df = pd.read_csv(chosen)
    logger.info('Loaded %d rows, %d columns', df.shape[0], df.shape[1])
    return df

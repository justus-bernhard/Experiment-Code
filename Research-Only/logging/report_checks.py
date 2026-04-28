"""Report snapshot checks for the pilot intervention variable."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List


EXPECTED_LABELS = {
    'Silence',
    'Instrumental Music',
    'Songs with Lyrics',
    'Cafe Noise',
    'Traffic Noise',
}

REQUIRED_TOP_KEYS = {'total_participants', 'overall', 'by_noise', 'meta'}
REQUIRED_OVERALL_KEYS = {
    'mean_focus',
    'median_focus',
    'mean_duration',
    'mean_fatigue',
    'focus_fatigue_gap',
}
REQUIRED_GROUP_KEYS = {
    'background_noise_type',
    'participants',
    'mean_focus',
    'median_focus',
    'mean_duration',
    'mean_fatigue',
    'focus_fatigue_gap',
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _labels_from_report(report: Dict[str, Any]) -> List[str]:
    by_noise = report.get('by_noise')
    if not isinstance(by_noise, list):
        return []

    labels: List[str] = []
    for row in by_noise:
        if isinstance(row, dict) and isinstance(row.get('background_noise_type'), str):
            labels.append(row['background_noise_type'])
    return labels


def _public_schema_valid(report: Dict[str, Any]) -> bool:
    if not REQUIRED_TOP_KEYS.issubset(report.keys()):
        return False
    if not isinstance(report.get('overall'), dict):
        return False
    if not REQUIRED_OVERALL_KEYS.issubset(report['overall'].keys()):
        return False
    if not isinstance(report.get('by_noise'), list):
        return False
    if not isinstance(report.get('meta'), dict):
        return False
    for row in report['by_noise']:
        if not isinstance(row, dict):
            return False
        if not REQUIRED_GROUP_KEYS.issubset(row.keys()):
            return False
    return True


def analyze_report(path: Path) -> Dict[str, Any]:
    """Analyze a report snapshot without interpreting source code or prompts."""
    result: Dict[str, Any] = {
        'path': str(path),
        'exists': path.exists(),
        'sha256': None,
        'valid_json': False,
        'json_error': None,
        'by_noise_labels': [],
        'by_noise_count': 0,
        'canonical_labels_correct': False,
        'public_schema_valid': False,
    }

    if not path.exists():
        return result

    result['sha256'] = sha256_file(path)

    try:
        with path.open('r', encoding='utf-8') as handle:
            report = json.load(handle)
    except json.JSONDecodeError as exc:
        result['json_error'] = str(exc)
        return result

    if not isinstance(report, dict):
        result['json_error'] = 'Top-level JSON value is not an object'
        return result

    labels = _labels_from_report(report)
    result['valid_json'] = True
    result['by_noise_labels'] = labels
    result['by_noise_count'] = len(labels)
    result['canonical_labels_correct'] = set(labels) == EXPECTED_LABELS and len(labels) == 5
    result['public_schema_valid'] = _public_schema_valid(report)
    return result

"""Report snapshot checks for the pilot intervention variable."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List


EXPECTED_LABELS = {
    'Industrial Sensors',
    'Control Units',
    'Power Modules',
    'Safety Components',
    'Communication Modules',
}
EXPECTED_SEMANTIC_LABELS = {
    'industrial sensors',
    'control units',
    'power modules',
    'safety components',
    'communication modules',
}

REQUIRED_TOP_KEYS = {'total_records', 'overall', 'by_product_family', 'meta'}
REQUIRED_OVERALL_KEYS = {
    'total_forecast_demand_units',
    'total_actual_demand_units',
    'total_planned_supply_receipts_units',
    'total_units_fulfilled',
    'mean_beginning_inventory_units',
    'mean_ending_inventory_units',
    'forecast_bias_units',
    'fill_rate_pct',
}
REQUIRED_GROUP_KEYS = {
    'product_family',
    'records',
    'total_forecast_demand_units',
    'total_actual_demand_units',
    'total_planned_supply_receipts_units',
    'total_units_fulfilled',
    'mean_beginning_inventory_units',
    'mean_ending_inventory_units',
    'forecast_bias_units',
    'fill_rate_pct',
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _labels_from_report(report: Dict[str, Any]) -> List[str]:
    by_product_family = report.get('by_product_family')
    if not isinstance(by_product_family, list):
        return []

    labels: List[str] = []
    for row in by_product_family:
        if isinstance(row, dict) and isinstance(row.get('product_family'), str):
            labels.append(row['product_family'])
    return labels


def _record_counts_from_report(report: Dict[str, Any]) -> List[int]:
    by_product_family = report.get('by_product_family')
    if not isinstance(by_product_family, list):
        return []

    counts: List[int] = []
    for row in by_product_family:
        if isinstance(row, dict) and isinstance(row.get('records'), int):
            counts.append(row['records'])
    return counts


def _semantic_label(label: str) -> str:
    return ' '.join(label.strip().lower().split())


def _semantic_labels(labels: List[str]) -> List[str]:
    return [_semantic_label(label) for label in labels]


def _normalization_status(
    labels: List[str],
    semantic_normalization_pass: bool,
    public_schema_valid: bool,
) -> str:
    if not public_schema_valid:
        return 'invalid_report'
    if not labels:
        return 'semantic_fail'
    if semantic_normalization_pass:
        return 'semantic_pass'
    if len(labels) > len(EXPECTED_SEMANTIC_LABELS):
        return 'semantic_fail_extra_groups'
    if len(labels) < len(EXPECTED_SEMANTIC_LABELS):
        return 'semantic_fail_missing_groups'
    return 'semantic_fail'


def _public_schema_valid(report: Dict[str, Any]) -> bool:
    if set(report.keys()) != REQUIRED_TOP_KEYS:
        return False
    if not isinstance(report.get('overall'), dict):
        return False
    if set(report['overall'].keys()) != REQUIRED_OVERALL_KEYS:
        return False
    if not isinstance(report.get('by_product_family'), list):
        return False
    if not isinstance(report.get('meta'), dict):
        return False
    for row in report['by_product_family']:
        if not isinstance(row, dict):
            return False
        if set(row.keys()) != REQUIRED_GROUP_KEYS:
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
        'product_family_labels': [],
        'reported_group_count': 0,
        'product_family_record_count_total': 0,
        'semantic_normalization_pass': False,
        'unique_semantic_family_count': 0,
        'normalization_status': 'invalid_report',
        'display_labels_canonical': False,
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
    record_counts = _record_counts_from_report(report)
    semantic_label_set = set(_semantic_labels(labels))
    public_schema_valid = _public_schema_valid(report)
    semantic_normalization_pass = semantic_label_set == EXPECTED_SEMANTIC_LABELS and len(labels) == 5
    display_labels_canonical = set(labels) == EXPECTED_LABELS and len(labels) == 5

    result['valid_json'] = True
    result['product_family_labels'] = labels
    result['reported_group_count'] = len(labels)
    result['product_family_record_count_total'] = sum(record_counts)
    result['semantic_normalization_pass'] = semantic_normalization_pass
    result['unique_semantic_family_count'] = len(semantic_label_set)
    result['normalization_status'] = _normalization_status(
        labels,
        semantic_normalization_pass,
        public_schema_valid,
    )
    result['display_labels_canonical'] = display_labels_canonical
    result['canonical_labels_correct'] = display_labels_canonical
    result['public_schema_valid'] = public_schema_valid
    return result

"""Build analysis-ready pilot summaries from raw JSONL events."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List

from research_logger import read_events, write_json


EXPECTED_SEMANTIC_LABELS = {
    'silence',
    'instrumental music',
    'songs with lyrics',
    'cafe noise',
    'traffic noise',
}


PROCESS_AVAILABILITY_FIELDS = {
    'prompt_log_available': False,
    'dataset_open_logging_available': False,
    'output_open_logging_available': False,
    'test_run_process_logging_available': False,
}


def _first(events: List[Dict[str, Any]], event_type: str) -> Dict[str, Any] | None:
    return next((event for event in events if event.get('event_type') == event_type), None)


def _last(events: List[Dict[str, Any]], event_type: str) -> Dict[str, Any] | None:
    matching = [event for event in events if event.get('event_type') == event_type]
    return matching[-1] if matching else None


def _event_data(event: Dict[str, Any] | None) -> Dict[str, Any]:
    if event is None:
        return {}
    data = event.get('data')
    if isinstance(data, dict):
        return data
    payload = event.get('payload')
    if isinstance(payload, dict):
        return payload
    return {}


def _sec(event: Dict[str, Any] | None) -> float | None:
    if event is None:
        return None
    elapsed_ms = event.get('elapsed_ms')
    if elapsed_ms is None:
        return None
    return round(float(elapsed_ms) / 1000, 3)


def _test_counts(event: Dict[str, Any] | None) -> tuple[int | None, int | None]:
    if event is None:
        return None, None
    data = _event_data(event)
    return data.get('passed'), data.get('total')


def _semantic_label(label: str) -> str:
    return ' '.join(label.strip().lower().split())


def _semantic_labels(labels: List[str]) -> set[str]:
    return {_semantic_label(label) for label in labels}


def _semantic_normalization_pass(data: Dict[str, Any]) -> bool:
    labels = data.get('by_noise_labels')
    if not isinstance(labels, list):
        return data.get('semantic_normalization_pass') is True

    text_labels = [label for label in labels if isinstance(label, str)]
    return _semantic_labels(text_labels) == EXPECTED_SEMANTIC_LABELS and len(text_labels) == 5


def _semantic_noise_type_count(data: Dict[str, Any]) -> int | None:
    labels = data.get('by_noise_labels')
    if not isinstance(labels, list):
        value = data.get('semantic_noise_type_count')
        return value if value is not None else None

    text_labels = [label for label in labels if isinstance(label, str)]
    return len(text_labels)


def _display_labels_canonical(data: Dict[str, Any]) -> bool | None:
    if 'display_labels_canonical' in data:
        return data.get('display_labels_canonical')
    if 'canonical_labels_correct' in data:
        return data.get('canonical_labels_correct')
    return None


def _normalization_status(data: Dict[str, Any]) -> str | None:
    if not data:
        return None
    if data.get('public_schema_valid') is False:
        return 'invalid_report'

    labels = data.get('by_noise_labels')
    if not isinstance(labels, list):
        return data.get('normalization_status')

    text_labels = [label for label in labels if isinstance(label, str)]
    if _semantic_normalization_pass(data):
        return 'semantic_pass'
    if len(text_labels) > len(EXPECTED_SEMANTIC_LABELS):
        return 'semantic_fail_extra_groups'
    if len(text_labels) < len(EXPECTED_SEMANTIC_LABELS):
        return 'semantic_fail_missing_groups'
    return 'semantic_fail'


def build_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    session_start = _first(events, 'session_start')
    submission_done = _first(events, 'submission_done')
    session_end = _last(events, 'session_end')

    start_data = _event_data(session_start)
    submission_elapsed = submission_done.get('elapsed_ms') if submission_done else None

    report_snapshots = [
        event
        for event in events
        if event.get('event_type') == 'report_snapshot'
        and (submission_elapsed is None or event.get('elapsed_ms', 0) <= submission_elapsed)
    ]
    semantic_snapshots = [
        event
        for event in report_snapshots
        if _semantic_normalization_pass(_event_data(event))
    ]

    first_report = report_snapshots[0] if report_snapshots else None
    first_semantic = semantic_snapshots[0] if semantic_snapshots else None
    final_report = report_snapshots[-1] if report_snapshots else None
    final_report_data = _event_data(final_report)

    public_event = _last(events, 'public_test_result')
    hidden_event = _last(events, 'hidden_test_result')
    public_passed, public_total = _test_counts(public_event)
    hidden_passed, hidden_total = _test_counts(hidden_event)
    outputs_cleared = _last(events, 'outputs_cleared')
    outputs_cleared_data = _event_data(outputs_cleared)

    totals_available = all(
        value is not None
        for value in (public_passed, public_total, hidden_passed, hidden_total)
    )
    if totals_available and int(public_total) + int(hidden_total) > 0:
        task_success_pct = round(
            ((int(public_passed) + int(hidden_passed)) / (int(public_total) + int(hidden_total))) * 100,
            3,
        )
    else:
        task_success_pct = None

    final_semantic_pass = _semantic_normalization_pass(final_report_data) if final_report else None

    summary: Dict[str, Any] = {
        'schema_version': 'session_summary.v2',
        'session': {
            'id': start_data.get('session_id'),
            'condition': start_data.get('condition'),
            'code_dir': start_data.get('code_dir'),
            'status': _event_data(session_end).get('status'),
            'start_utc': session_start.get('timestamp_utc') if session_start else None,
            'submission_done_utc': submission_done.get('timestamp_utc') if submission_done else None,
            'end_utc': session_end.get('timestamp_utc') if session_end else None,
        },
        'timing': {
            'time_to_completion_sec': (
                round((submission_done.get('elapsed_ms') - session_start.get('elapsed_ms')) / 1000, 3)
                if session_start and submission_done
                else None
            ),
            'first_report_sec': _sec(first_report),
            'first_intervention_sec': _sec(first_semantic),
        },
        'primary_outcome': {
            'intervention_binary': bool(semantic_snapshots),
            'intervention_source': 'first_semantic_pass_report_snapshot',
        },
        'report_outcome': {
            'semantic_pass': final_semantic_pass,
            'canonical_pass': _display_labels_canonical(final_report_data),
            'normalization_status': _normalization_status(final_report_data),
            'noise_type_count': _semantic_noise_type_count(final_report_data),
            'report_snapshot_count': len(report_snapshots),
        },
        'tests': {
            'public': {
                'passed': public_passed,
                'total': public_total,
            },
            'hidden': {
                'passed': hidden_passed,
                'total': hidden_total,
            },
            'task_success_pct': task_success_pct,
        },
        'process': PROCESS_AVAILABILITY_FIELDS.copy(),
        'diagnostics': {
            'artifacts': {
                'dataset_sha256': start_data.get('dataset_sha256'),
                'final_report_sha256': final_report_data.get('sha256'),
                'outputs_cleanup_performed': outputs_cleared is not None,
                'outputs_cleanup_file_count': outputs_cleared_data.get('deleted_count'),
            },
            'final_noise_labels': final_report_data.get('by_noise_labels'),
        },
    }
    return summary


def summarize_log_dir(log_dir: Path) -> Dict[str, Any]:
    events = read_events(log_dir / 'events.jsonl')
    summary = build_summary(events)
    write_json(log_dir / 'session_summary.json', summary)
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Summarise one pilot session log directory.')
    parser.add_argument('log_dir', help='Path to Research-Only/logs/<session_id>')
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    summarize_log_dir(Path(args.log_dir))
    print(f'Wrote {Path(args.log_dir) / "session_summary.json"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

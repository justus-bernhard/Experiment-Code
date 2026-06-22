"""Build analysis-ready pilot summaries from raw JSONL events."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from research_logger import read_events, write_json
from report_checks import sha256_file


EXPECTED_SEMANTIC_LABELS = {
    'industrial sensors',
    'control units',
    'power modules',
    'safety components',
    'communication modules',
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


def _duration_sec(start_event: Dict[str, Any] | None, end_event: Dict[str, Any] | None) -> float | None:
    if start_event is None or end_event is None:
        return None
    start_ms = start_event.get('elapsed_ms')
    end_ms = end_event.get('elapsed_ms')
    if start_ms is None or end_ms is None:
        return None
    return round((float(end_ms) - float(start_ms)) / 1000, 3)


def _semantic_label(label: str) -> str:
    return ' '.join(label.strip().lower().split())


def _semantic_labels(labels: List[str]) -> set[str]:
    return {_semantic_label(label) for label in labels}


def _semantic_normalization_pass(data: Dict[str, Any]) -> bool:
    labels = data.get('product_family_labels')
    if not isinstance(labels, list):
        return data.get('semantic_normalization_pass') is True

    text_labels = [label for label in labels if isinstance(label, str)]
    return _semantic_labels(text_labels) == EXPECTED_SEMANTIC_LABELS and len(text_labels) == 5


def _reported_group_count(data: Dict[str, Any]) -> int | None:
    labels = data.get('product_family_labels')
    if not isinstance(labels, list):
        value = data.get('reported_group_count', data.get('product_family_count'))
        return value if value is not None else None

    text_labels = [label for label in labels if isinstance(label, str)]
    return len(text_labels)


def _unique_semantic_family_count(data: Dict[str, Any]) -> int | None:
    labels = data.get('product_family_labels')
    if not isinstance(labels, list):
        value = data.get('unique_semantic_family_count')
        return value if value is not None else None
    return len(_semantic_labels([label for label in labels if isinstance(label, str)]))


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

    labels = data.get('product_family_labels')
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


def _snapshot_phase(event: Dict[str, Any]) -> str | None:
    phase = _event_data(event).get('phase')
    return phase if isinstance(phase, str) else None


def _intervention_stage(first_semantic: Dict[str, Any] | None) -> str | None:
    if first_semantic is None:
        return 'none'
    phase = _snapshot_phase(first_semantic)
    if phase in {'task_phase', 'review_phase'}:
        return phase
    return None


def _manual_chat_log(log_dir: Path | None) -> Dict[str, Any]:
    unavailable = {
        'available': False,
        'path': None,
        'sha256': None,
        'export_timestamp_utc': None,
    }
    if log_dir is None:
        return unavailable
    chat_path = log_dir / 'chat.md'
    if not chat_path.is_file():
        return unavailable
    modified_at = datetime.fromtimestamp(
        chat_path.stat().st_mtime,
        tz=timezone.utc,
    ).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    return {
        'available': True,
        'path': 'chat.md',
        'sha256': sha256_file(chat_path),
        'export_timestamp_utc': modified_at,
    }


def _report_stage(phase: str | None) -> str:
    return {
        'task_phase': 'task',
        'review_phase': 'review',
    }.get(phase, 'unknown')


def _report_history_entry(event: Dict[str, Any]) -> Dict[str, Any]:
    data = _event_data(event)
    labels = data.get('product_family_labels')
    text_labels = [label for label in labels if isinstance(label, str)] if isinstance(labels, list) else []
    return {
        'number': data.get('snapshot_index'),
        'stage': _report_stage(_snapshot_phase(event)),
        'created_utc': event.get('timestamp_utc'),
        'elapsed_sec': _sec(event),
        'path': data.get('snapshot_path'),
        'sha256': data.get('sha256'),
        'valid_json': data.get('valid_json'),
        'schema_valid': data.get('public_schema_valid'),
        'labels': text_labels,
        'reported_group_count': _reported_group_count(data),
        'semantic_group_count': _unique_semantic_family_count(data),
        'semantic_pass': _semantic_normalization_pass(data),
        'canonical_display_pass': _display_labels_canonical(data),
        'normalization_status': _normalization_status(data),
    }


def build_summary(events: List[Dict[str, Any]], log_dir: Path | None = None) -> Dict[str, Any]:
    session_start = _first(events, 'session_start')
    task_phase_start = _first(events, 'task_phase_start')
    task_phase_end = _first(events, 'task_phase_end')
    review_phase_start = _first(events, 'review_phase_start')
    review_phase_end = _first(events, 'review_phase_end')
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
    code_dir_reset = _last(events, 'code_dir_reset')
    code_dir_reset_data = _event_data(code_dir_reset)
    checkpoint_errors = [
        event
        for event in events
        if event.get('event_type') == 'checkpoint_error'
    ]

    final_semantic_pass = _semantic_normalization_pass(final_report_data) if final_report else None
    manual_chat_log = _manual_chat_log(log_dir)
    report_history = [_report_history_entry(event) for event in report_snapshots]
    final_report_history = report_history[-1] if report_history else None

    summary: Dict[str, Any] = {
        'schema_version': 'session_summary.v4',
        'session': {
            'id': start_data.get('session_id'),
            'condition': start_data.get('condition'),
            'runner': start_data.get('runner'),
            'code_dir': start_data.get('code_dir'),
            'status': _event_data(session_end).get('status'),
            'start_utc': session_start.get('timestamp_utc') if session_start else None,
            'submission_done_utc': submission_done.get('timestamp_utc') if submission_done else None,
            'end_utc': session_end.get('timestamp_utc') if session_end else None,
        },
        'timing': {
            'time_to_task_start_sec': _duration_sec(session_start, task_phase_start),
            'task_phase_duration_sec': _duration_sec(task_phase_start, task_phase_end),
            'review_phase_duration_sec': _duration_sec(review_phase_start, review_phase_end),
            'time_to_completion_sec': (
                round((submission_done.get('elapsed_ms') - session_start.get('elapsed_ms')) / 1000, 3)
                if session_start and submission_done
                else None
            ),
            'first_report_sec': _sec(first_report),
            'first_intervention_sec': _sec(first_semantic),
        },
        'reports': report_history,
        'outcome': {
            'intervention_detected': bool(semantic_snapshots),
            'intervention_stage': _intervention_stage(first_semantic),
            'first_semantic_pass_report': _report_history_entry(first_semantic) if first_semantic else None,
            'final_report': final_report_history,
            'final_semantic_pass': final_semantic_pass,
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
        },
        'environment': {
            'branch': start_data.get('git_branch'),
            'head_commit': start_data.get('head_commit'),
            'dataset_sha256': start_data.get('dataset_sha256'),
            'reset_source': code_dir_reset_data.get('source'),
            'outputs_cleared_count': outputs_cleared_data.get('deleted_count'),
        },
        'artifacts': {
            'manual_chat_log': manual_chat_log,
        },
        'logging': {
            'checkpoint_error_count': len(checkpoint_errors),
            'manual_chat_log_available': manual_chat_log['available'],
        },
    }
    return summary


def summarize_log_dir(log_dir: Path) -> Dict[str, Any]:
    events = read_events(log_dir / 'events.jsonl')
    summary = build_summary(events, log_dir)
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

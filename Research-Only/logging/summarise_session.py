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


PROCESS_AVAILABILITY_FIELDS = {
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


def _product_family_record_count_total(data: Dict[str, Any]) -> int | None:
    value = data.get('product_family_record_count_total')
    return value if isinstance(value, int) else None


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


def _snapshot_count_by_phase(events: List[Dict[str, Any]], phase: str) -> int:
    return sum(1 for event in events if _snapshot_phase(event) == phase)


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
        'file_modified_at_utc': None,
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
        'file_modified_at_utc': modified_at,
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
    ui_ready = _last(events, 'ui_ready')
    ui_error = _last(events, 'ui_error')
    ui_close_attempts = [
        event
        for event in events
        if event.get('event_type') == 'ui_close_attempted'
    ]
    checkpoint_events = [
        event
        for event in events
        if event.get('event_type') == 'checkpoint_created'
    ]
    checkpoint_errors = [
        event
        for event in events
        if event.get('event_type') == 'checkpoint_error'
    ]

    final_semantic_pass = _semantic_normalization_pass(final_report_data) if final_report else None
    manual_chat_log = _manual_chat_log(log_dir)
    raw_final_labels = final_report_data.get('product_family_labels')
    final_labels = [label for label in raw_final_labels if isinstance(label, str)] if isinstance(raw_final_labels, list) else []
    command_events = {
        _event_data(event).get('label'): _event_data(event)
        for event in events
        if event.get('event_type') == 'command_run'
    }
    checkpoint_summary = [
        {
            'checkpoint_id': _event_data(event).get('checkpoint_id'),
            'checkpoint_type': _event_data(event).get('checkpoint_type'),
            'phase': _event_data(event).get('phase'),
            'manifest_path': _event_data(event).get('manifest_path'),
            'changed_file_count': _event_data(event).get('changed_file_count'),
        }
        for event in checkpoint_events
    ]

    summary: Dict[str, Any] = {
        'schema_version': 'session_summary.v3',
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
        'primary_outcome': {
            'intervention_binary': bool(semantic_snapshots),
            'intervention_stage': _intervention_stage(first_semantic),
            'intervention_source': 'first_semantic_pass_report_snapshot',
        },
        'report_outcome': {
            'semantic_pass': final_semantic_pass,
            'canonical_pass': _display_labels_canonical(final_report_data),
            'normalization_status': _normalization_status(final_report_data),
            'reported_group_count': _reported_group_count(final_report_data),
            'unique_semantic_family_count': _unique_semantic_family_count(final_report_data),
            'product_family_record_count_total': _product_family_record_count_total(final_report_data),
            'report_snapshot_count': len(report_snapshots),
            'task_phase_report_snapshot_count': _snapshot_count_by_phase(report_snapshots, 'task_phase'),
            'review_phase_report_snapshot_count': _snapshot_count_by_phase(report_snapshots, 'review_phase'),
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
        'provenance': {
            'runner': start_data.get('runner'),
            'branch': start_data.get('git_branch'),
            'head_commit': start_data.get('head_commit'),
            'dataset_sha256': start_data.get('dataset_sha256'),
            'reset': code_dir_reset_data,
            'outputs_cleanup': outputs_cleared_data,
        },
        'artifacts': {
            'final_report_snapshot_path': final_report_data.get('snapshot_path'),
            'final_report_sha256': final_report_data.get('sha256'),
            'hidden_verifier_output': command_events.get('hidden_verifier', {}).get('artifacts'),
            'public_test_output': command_events.get('public_pytest', {}).get('artifacts'),
            'manual_chat_log': manual_chat_log,
        },
        'audit': {
            'checkpoints': checkpoint_summary,
            'checkpoint_error_count': len(checkpoint_errors),
        },
        'process': {
            **PROCESS_AVAILABILITY_FIELDS,
            'manual_prompt_log_available': manual_chat_log['available'],
        },
        'diagnostics': {
            'ui': {
                'always_on_top': _event_data(ui_ready).get('always_on_top'),
                'ui_close_attempted_count': len(ui_close_attempts),
                'ui_closed_before_completion': (
                    _event_data(session_end).get('status') in {'interrupted', 'failed'}
                    and _last(events, 'ui_closed') is not None
                ),
                'error': _event_data(ui_error).get('error') if ui_error else None,
            },
            'final_product_family_labels': final_labels,
            'final_normalized_product_family_labels': sorted(_semantic_labels(final_labels)),
            'expected_semantic_product_family_labels': sorted(EXPECTED_SEMANTIC_LABELS),
            'final_semantic_equality': _semantic_labels(final_labels) == EXPECTED_SEMANTIC_LABELS and len(final_labels) == 5,
        },
    }
    return summary


def summarize_log_dir(log_dir: Path) -> Dict[str, Any]:
    events = read_events(log_dir / 'events.jsonl')
    summary = build_summary(events, log_dir)
    summary['artifacts']['timeline_path'] = 'timeline.md'
    summary['artifacts']['session_manifest_path'] = 'session_manifest.json'
    write_json(log_dir / 'session_summary.json', summary)
    _write_timeline(log_dir, events)
    _write_session_manifest(log_dir)
    return summary


def _write_timeline(log_dir: Path, events: List[Dict[str, Any]]) -> None:
    lines = ['# Session Timeline', '']
    for event in events:
        event_type = event.get('event_type')
        data = _event_data(event)
        timestamp = event.get('timestamp_utc', 'unknown time')
        elapsed = event.get('elapsed_ms')
        prefix = f'- {timestamp} ({elapsed} ms)'
        if event_type == 'checkpoint_created':
            lines.append(
                f"{prefix}: checkpoint `{data.get('checkpoint_id')}` "
                f"({data.get('checkpoint_type')}, phase={data.get('phase')}, "
                f"changed files={data.get('changed_file_count')})."
            )
        elif event_type == 'report_snapshot':
            lines.append(
                f"{prefix}: report snapshot `{data.get('snapshot_path')}` "
                f"(semantic pass={data.get('semantic_normalization_pass')}, "
                f"checkpoint={data.get('checkpoint_id')})."
            )
        elif event_type in {
            'session_start', 'task_phase_start', 'task_phase_end', 'review_phase_start',
            'review_phase_end', 'submission_done', 'session_end', 'public_test_result',
            'hidden_test_result', 'ui_close_attempted', 'ui_error',
        }:
            lines.append(f'{prefix}: `{event_type}`.')
    (log_dir / 'timeline.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _write_session_manifest(log_dir: Path) -> None:
    artifact_paths = {
        log_dir / 'events.jsonl',
        log_dir / 'session_summary.json',
        log_dir / 'chat.md',
    }
    artifact_paths.add(log_dir / 'timeline.md')
    for directory_name in ('checkpoints', 'report_snapshots', 'participant_environment', 'command_output'):
        directory = log_dir / directory_name
        if directory.exists():
            artifact_paths.update(path for path in directory.rglob('*') if path.is_file())
    artifacts = [
        {
            'path': str(path.relative_to(log_dir)).replace('\\', '/'),
            'sha256': sha256_file(path),
        }
        for path in sorted(artifact_paths)
        if path.exists()
    ]
    write_json(log_dir / 'session_manifest.json', {
        'schema_version': 'session_manifest.v1',
        'artifacts': artifacts,
    })


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

"""Build analysis-ready pilot summaries from raw JSONL events."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List

from research_logger import read_events, write_json


UNAVAILABLE_PROCESS_FIELDS = {
    'prompt_log_available': False,
    'prompt_count': None,
    'dataset_open_logging_available': False,
    'dataset_opened': None,
    'output_open_logging_available': False,
    'output_opened': None,
    'test_run_process_logging_available': False,
    'test_run_count': None,
}


def _first(events: List[Dict[str, Any]], event_type: str) -> Dict[str, Any] | None:
    return next((event for event in events if event.get('event_type') == event_type), None)


def _last(events: List[Dict[str, Any]], event_type: str) -> Dict[str, Any] | None:
    matching = [event for event in events if event.get('event_type') == event_type]
    return matching[-1] if matching else None


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
    payload = event.get('payload', {})
    return payload.get('passed'), payload.get('total')


def build_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    session_start = _first(events, 'session_start')
    submission_done = _first(events, 'submission_done')
    session_end = _last(events, 'session_end')

    start_payload = session_start.get('payload', {}) if session_start else {}
    submission_elapsed = submission_done.get('elapsed_ms') if submission_done else None

    report_snapshots = [
        event
        for event in events
        if event.get('event_type') == 'report_snapshot'
        and (submission_elapsed is None or event.get('elapsed_ms', 0) <= submission_elapsed)
    ]
    canonical_snapshots = [
        event
        for event in report_snapshots
        if event.get('payload', {}).get('canonical_labels_correct') is True
    ]

    first_report = report_snapshots[0] if report_snapshots else None
    first_canonical = canonical_snapshots[0] if canonical_snapshots else None
    final_report = report_snapshots[-1] if report_snapshots else None
    final_report_payload = final_report.get('payload', {}) if final_report else {}

    public_event = _last(events, 'public_test_result')
    hidden_event = _last(events, 'hidden_test_result')
    public_passed, public_total = _test_counts(public_event)
    hidden_passed, hidden_total = _test_counts(hidden_event)

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

    summary: Dict[str, Any] = {
        'session_id': start_payload.get('session_id'),
        'condition': start_payload.get('condition'),
        'code_dir': start_payload.get('code_dir'),
        'session_start_utc': session_start.get('timestamp_utc') if session_start else None,
        'submission_done_utc': submission_done.get('timestamp_utc') if submission_done else None,
        'session_end_utc': session_end.get('timestamp_utc') if session_end else None,
        'time_to_completion_sec': (
            round((submission_done.get('elapsed_ms') - session_start.get('elapsed_ms')) / 1000, 3)
            if session_start and submission_done
            else None
        ),
        'dataset_hash': start_payload.get('dataset_sha256'),
        'dataset_path': start_payload.get('dataset_path'),
        'intervention_binary': bool(canonical_snapshots),
        'time_to_intervention_sec': _sec(first_canonical),
        'intervention_source': 'first_canonical_report_snapshot',
        'report_snapshot_count': len(report_snapshots),
        'first_report_sec': _sec(first_report),
        'first_canonical_report_sec': _sec(first_canonical),
        'final_report_hash': final_report_payload.get('sha256'),
        'final_report_canonical': final_report_payload.get('canonical_labels_correct') if final_report else None,
        'public_tests_passed': public_passed,
        'public_tests_total': public_total,
        'hidden_tests_passed': hidden_passed,
        'hidden_tests_total': hidden_total,
        'task_success_pct': task_success_pct,
    }
    summary.update(UNAVAILABLE_PROCESS_FIELDS)
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

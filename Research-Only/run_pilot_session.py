"""Run a hidden pilot observer session.

Start before the participant begins:
  python Research-Only/run_pilot_session.py --session-id S001 --condition AUT --code-dir "Code - AUT"

Press Enter in this observer terminal when the participant gives the first
"done" signal. The script then runs post-submission checks and writes:
  Research-Only/logs/<session_id>/events.jsonl
  Research-Only/logs/<session_id>/session_summary.json
"""

from __future__ import annotations

import argparse
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
RESEARCH_DIR = ROOT / 'Research-Only'
LOGGING_DIR = RESEARCH_DIR / 'logging'
sys.path.insert(0, str(LOGGING_DIR))

from report_checks import analyze_report, sha256_file  # noqa: E402
from research_logger import ResearchLogger, tail_text  # noqa: E402
from summarise_session import summarize_log_dir  # noqa: E402


DATA_RELATIVE_PATH = Path('data') / 'background_noise_focus_dataset.csv'
REPORT_RELATIVE_PATH = Path('outputs') / 'report.json'
HIDDEN_VERIFIER_PATH = RESEARCH_DIR / 'research_verify.py'


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Run the hidden pilot logging observer.')
    parser.add_argument('--session-id', required=True, help='Pseudonymous participant/session ID.')
    parser.add_argument('--condition', required=True, help='Experimental condition, e.g. AUT or AUG.')
    parser.add_argument(
        '--code-dir',
        required=True,
        help='Participant code directory, e.g. "Code - AUT". Relative paths resolve from repo root.',
    )
    parser.add_argument(
        '--logs-root',
        default=str(RESEARCH_DIR / 'logs'),
        help='Directory where session log folders are written.',
    )
    parser.add_argument(
        '--poll-interval-sec',
        type=float,
        default=1.0,
        help='How often to poll outputs/report.json for changes.',
    )
    parser.add_argument(
        '--command-timeout-sec',
        type=float,
        default=120.0,
        help='Timeout for post-submission verifier/test commands.',
    )
    return parser


def _resolve_code_dir(value: str) -> Path:
    raw = Path(value)
    code_dir = raw if raw.is_absolute() else ROOT / raw
    code_dir = code_dir.resolve()
    if not code_dir.is_dir():
        raise FileNotFoundError(f'Code directory not found: {code_dir}')
    return code_dir


def _clear_outputs_dir(code_dir: Path) -> Dict[str, Any]:
    outputs_dir = (code_dir / 'outputs').resolve()
    expected_parent = code_dir.resolve()
    if outputs_dir.parent != expected_parent:
        raise ValueError(f'Unexpected outputs directory location: {outputs_dir}')

    outputs_dir.mkdir(exist_ok=True)
    deleted_files: List[str] = []

    for item in outputs_dir.iterdir():
        if item.name == '.gitkeep':
            continue

        deleted_files.append(_relative(item))
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    return {
        'outputs_dir': _relative(outputs_dir),
        'deleted_count': len(deleted_files),
        'deleted_files': deleted_files,
    }


class ReportWatcher:
    def __init__(
        self,
        code_dir: Path,
        log_dir: Path,
        logger: ResearchLogger,
        poll_interval_sec: float,
    ) -> None:
        self.code_dir = code_dir
        self.report_path = code_dir / REPORT_RELATIVE_PATH
        self.snapshots_dir = log_dir / 'report_snapshots'
        self.logger = logger
        self.poll_interval_sec = poll_interval_sec
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name='report-watcher', daemon=True)
        self._last_hash: str | None = None
        self._snapshot_index = 0

    def start(self) -> None:
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=max(self.poll_interval_sec * 2, 2.0))

    def check_once(self) -> None:
        if not self.report_path.exists():
            return

        try:
            current_hash = sha256_file(self.report_path)
        except OSError as exc:
            self.logger.event(
                'report_snapshot_error',
                {
                    'path': _relative(self.report_path),
                    'error': str(exc),
                },
            )
            return

        if current_hash == self._last_hash:
            return

        self._last_hash = current_hash
        self._snapshot_index += 1
        snapshot_path = self.snapshots_dir / f'report_{self._snapshot_index:04d}.json'

        try:
            shutil.copy2(self.report_path, snapshot_path)
            analysis = analyze_report(snapshot_path)
        except OSError as exc:
            self.logger.event(
                'report_snapshot_error',
                {
                    'path': _relative(self.report_path),
                    'error': str(exc),
                    'sha256': current_hash,
                },
            )
            return

        analysis.update(
            {
                'snapshot_index': self._snapshot_index,
                'source_path': _relative(self.report_path),
                'snapshot_path': _relative(snapshot_path),
            }
        )
        self.logger.event('report_snapshot', analysis)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.check_once()
            self._stop_event.wait(self.poll_interval_sec)


def _run_command(
    label: str,
    command: List[str],
    cwd: Path,
    timeout_sec: float,
    logger: ResearchLogger,
) -> subprocess.CompletedProcess[str]:
    started_ms = logger.elapsed_ms()
    started = time.monotonic()
    timed_out = False
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        result = subprocess.CompletedProcess(
            command,
            returncode=124,
            stdout=exc.stdout or '',
            stderr=exc.stderr or '',
        )

    duration_ms = int(round((time.monotonic() - started) * 1000))
    logger.event(
        'command_run',
        {
            'label': label,
            'command': command,
            'cwd': _relative(cwd),
            'started_elapsed_ms': started_ms,
            'duration_ms': duration_ms,
            'exit_code': result.returncode,
            'timed_out': timed_out,
            'diagnostics': {
                'stdout_tail': tail_text(result.stdout or ''),
                'stderr_tail': tail_text(result.stderr or ''),
            },
        },
    )
    return result


def _pytest_counts(output: str, exit_code: int) -> tuple[int | None, int | None]:
    if 'no tests ran' in output.lower():
        return 0, 0

    passed = sum(int(value) for value in re.findall(r'(\d+)\s+passed', output))
    failed = sum(int(value) for value in re.findall(r'(\d+)\s+failed', output))
    errors = sum(int(value) for value in re.findall(r'(\d+)\s+errors?', output))
    total = passed + failed + errors

    if total == 0:
        return (None, None) if exit_code != 0 else (None, None)
    return passed, total


def _run_hidden_verifier(
    code_dir: Path,
    timeout_sec: float,
    logger: ResearchLogger,
) -> None:
    result = _run_command(
        'hidden_verifier',
        [sys.executable, str(HIDDEN_VERIFIER_PATH), '--code-dir', str(code_dir)],
        ROOT,
        timeout_sec,
        logger,
    )
    logger.event(
        'hidden_test_result',
        {
            'passed': 1 if result.returncode == 0 else 0,
            'total': 1,
            'exit_code': result.returncode,
        },
    )


def _run_public_tests(
    code_dir: Path,
    timeout_sec: float,
    logger: ResearchLogger,
) -> None:
    result = _run_command(
        'public_pytest',
        [sys.executable, '-m', 'pytest', '-q'],
        code_dir,
        timeout_sec,
        logger,
    )
    combined_output = f'{result.stdout or ""}\n{result.stderr or ""}'
    passed, total = _pytest_counts(combined_output, result.returncode)
    logger.event(
        'public_test_result',
        {
            'passed': passed,
            'total': total,
            'exit_code': result.returncode,
        },
    )


def _session_start_payload(session_id: str, condition: str, code_dir: Path) -> Dict[str, Any]:
    dataset_path = code_dir / DATA_RELATIVE_PATH
    if not dataset_path.exists():
        raise FileNotFoundError(f'Missing dataset: {dataset_path}')

    return {
        'session_id': session_id,
        'condition': condition,
        'code_dir': _relative(code_dir),
        'dataset_path': _relative(dataset_path),
        'dataset_sha256': sha256_file(dataset_path),
        'python_version': platform.python_version(),
        'platform': platform.platform(),
    }


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    logger: ResearchLogger | None = None
    watcher: ReportWatcher | None = None
    session_log_dir: Path | None = None

    try:
        code_dir = _resolve_code_dir(args.code_dir)
        log_dir = Path(args.logs_root)
        if not log_dir.is_absolute():
            log_dir = ROOT / log_dir
        session_log_dir = log_dir / args.session_id
        events_path = session_log_dir / 'events.jsonl'
        if events_path.exists():
            parser.error(f'Session already has an events file: {events_path}')

        logger = ResearchLogger(session_log_dir, args.session_id, args.condition)
        logger.event('outputs_cleared', _clear_outputs_dir(code_dir))
        logger.event('session_start', _session_start_payload(args.session_id, args.condition, code_dir))

        watcher = ReportWatcher(code_dir, session_log_dir, logger, args.poll_interval_sec)
        watcher.start()

        print(f'Session {args.session_id} started.')
        print(f'Condition: {args.condition}')
        print(f'Watching: {_relative(code_dir / REPORT_RELATIVE_PATH)}')
        print('Press ENTER when participant declares done.')
        input()

        watcher.stop()
        watcher.check_once()
        logger.event('submission_done', {'source': 'researcher_marked'})

        # Hidden verifier must run before public tests, because public tests may
        # regenerate outputs/report.json after the submitted artefact is logged.
        _run_hidden_verifier(code_dir, args.command_timeout_sec, logger)
        _run_public_tests(code_dir, args.command_timeout_sec, logger)
        logger.event('session_end', {'status': 'completed'})

        summarize_log_dir(session_log_dir)
        print(f'Summary written to {_relative(session_log_dir / "session_summary.json")}')
        return 0
    except KeyboardInterrupt:
        if watcher is not None:
            watcher.stop()
        if logger is not None:
            logger.event('session_end', {'status': 'interrupted'})
            if session_log_dir is not None:
                summarize_log_dir(session_log_dir)
        print('Observer interrupted before completion.', file=sys.stderr)
        return 130
    except Exception as exc:
        if watcher is not None:
            watcher.stop()
        if logger is not None:
            logger.event('session_end', {'status': 'failed', 'error': str(exc)})
            if session_log_dir is not None:
                summarize_log_dir(session_log_dir)
        print(f'Observer failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

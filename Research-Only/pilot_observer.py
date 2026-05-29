"""Shared observer utilities for pilot logging runners."""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List


ROOT = Path(__file__).resolve().parents[1]
RESEARCH_DIR = ROOT / 'Research-Only'
LOGGING_DIR = RESEARCH_DIR / 'logging'
if str(LOGGING_DIR) not in sys.path:
    sys.path.insert(0, str(LOGGING_DIR))

from report_checks import analyze_report, sha256_file  # noqa: E402
from research_logger import ResearchLogger, tail_text  # noqa: E402


DATA_RELATIVE_PATH = Path('data') / 'background_noise_focus_dataset.csv'
REPORT_RELATIVE_PATH = Path('outputs') / 'report.json'
HIDDEN_VERIFIER_PATH = RESEARCH_DIR / 'research_verify.py'

KNOWN_CONDITIONS = {
    'AUT': 'Code - AUT',
    'AUG': 'Code - AUG',
}


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def resolve_code_dir(value: str) -> Path:
    raw = Path(value)
    code_dir = raw if raw.is_absolute() else ROOT / raw
    code_dir = code_dir.resolve()
    if not code_dir.is_dir():
        raise FileNotFoundError(f'Code directory not found: {code_dir}')
    return code_dir


def code_dir_for_condition(condition: str) -> Path:
    try:
        return resolve_code_dir(KNOWN_CONDITIONS[condition])
    except KeyError as exc:
        raise ValueError(f'Unsupported condition: {condition}') from exc


def resolve_logs_root(value: str | Path | None = None) -> Path:
    log_dir = Path(value) if value is not None else RESEARCH_DIR / 'logs'
    if not log_dir.is_absolute():
        log_dir = ROOT / log_dir
    return log_dir.resolve()


def session_log_dir(logs_root: Path, session_id: str) -> Path:
    return logs_root / session_id


def assert_new_session(log_dir: Path) -> None:
    events_path = log_dir / 'events.jsonl'
    if events_path.exists():
        raise FileExistsError(f'Session already has an events file: {events_path}')


def clear_outputs_dir(code_dir: Path) -> Dict[str, Any]:
    outputs_dir = (code_dir / 'outputs').resolve()
    expected_parent = code_dir.resolve()
    if outputs_dir.parent != expected_parent:
        raise ValueError(f'Unexpected outputs directory location: {outputs_dir}')

    outputs_dir.mkdir(exist_ok=True)
    deleted_files: List[str] = []

    for item in outputs_dir.iterdir():
        if item.name == '.gitkeep':
            continue

        deleted_files.append(relative(item))
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    return {
        'outputs_dir': relative(outputs_dir),
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
        phase_provider: Callable[[], str | None] | None = None,
    ) -> None:
        self.code_dir = code_dir
        self.report_path = code_dir / REPORT_RELATIVE_PATH
        self.snapshots_dir = log_dir / 'report_snapshots'
        self.logger = logger
        self.poll_interval_sec = poll_interval_sec
        self.phase_provider = phase_provider
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
                    'path': relative(self.report_path),
                    'error': str(exc),
                    'phase': self._current_phase(),
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
                    'path': relative(self.report_path),
                    'error': str(exc),
                    'sha256': current_hash,
                    'phase': self._current_phase(),
                },
            )
            return

        analysis.update(
            {
                'snapshot_index': self._snapshot_index,
                'source_path': relative(self.report_path),
                'snapshot_path': relative(snapshot_path),
                'phase': self._current_phase(),
            }
        )
        self.logger.event('report_snapshot', analysis)

    def _current_phase(self) -> str | None:
        if self.phase_provider is None:
            return None
        return self.phase_provider()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.check_once()
            self._stop_event.wait(self.poll_interval_sec)


def run_command(
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
            'cwd': relative(cwd),
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


def pytest_counts(output: str, exit_code: int) -> tuple[int | None, int | None]:
    if 'no tests ran' in output.lower():
        return 0, 0

    passed = sum(int(value) for value in re.findall(r'(\d+)\s+passed', output))
    failed = sum(int(value) for value in re.findall(r'(\d+)\s+failed', output))
    errors = sum(int(value) for value in re.findall(r'(\d+)\s+errors?', output))
    total = passed + failed + errors

    if total == 0:
        return (None, None) if exit_code != 0 else (None, None)
    return passed, total


def run_hidden_verifier(
    code_dir: Path,
    timeout_sec: float,
    logger: ResearchLogger,
) -> None:
    result = run_command(
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


def run_public_tests(
    code_dir: Path,
    timeout_sec: float,
    logger: ResearchLogger,
) -> None:
    result = run_command(
        'public_pytest',
        [sys.executable, '-m', 'pytest', '-q'],
        code_dir,
        timeout_sec,
        logger,
    )
    combined_output = f'{result.stdout or ""}\n{result.stderr or ""}'
    passed, total = pytest_counts(combined_output, result.returncode)
    logger.event(
        'public_test_result',
        {
            'passed': passed,
            'total': total,
            'exit_code': result.returncode,
        },
    )


def session_start_data(session_id: str, condition: str, code_dir: Path) -> Dict[str, Any]:
    dataset_path = code_dir / DATA_RELATIVE_PATH
    if not dataset_path.exists():
        raise FileNotFoundError(f'Missing dataset: {dataset_path}')

    return {
        'session_id': session_id,
        'condition': condition,
        'code_dir': relative(code_dir),
        'dataset_path': relative(dataset_path),
        'dataset_sha256': sha256_file(dataset_path),
        'python_version': platform.python_version(),
        'platform': platform.platform(),
    }

"""Shared observer utilities for pilot logging runners."""

from __future__ import annotations

import json
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


DATA_RELATIVE_PATH = Path('data') / 'product_family_planning_dataset.csv'
REPORT_RELATIVE_PATH = Path('outputs') / 'report.json'
REPORT_SOURCE_RELATIVE_PATH = Path('src') / 'report.py'
DATA_LOADER_RELATIVE_PATH = Path('src') / 'data_loader.py'
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
    if not events_path.exists():
        return

    session_started = False
    with events_path.open('r', encoding='utf-8') as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f'Malformed JSONL event at {events_path}:{line_number}') from exc
            if event.get('event_type') == 'session_start':
                session_started = True
                break

    if session_started:
        raise FileExistsError(f'Session already has an events file: {events_path}')

    shutil.rmtree(log_dir)


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


def _resettable_code_dir_relative_path(code_dir: Path) -> Path:
    resolved = code_dir.resolve()
    root = ROOT.resolve()
    try:
        relative_path = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f'Code directory is outside the experiment repository: {resolved}') from exc

    allowed_paths = {Path(value) for value in KNOWN_CONDITIONS.values()}
    if relative_path not in allowed_paths:
        allowed = ', '.join(str(path) for path in sorted(allowed_paths, key=str))
        raise ValueError(f'Reset is only allowed for condition directories: {allowed}')

    return relative_path


def _run_git(args: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ['git', *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def _clean_preview_paths(output: str) -> List[str]:
    paths: List[str] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if line.startswith('Would remove '):
            paths.append(line.removeprefix('Would remove ').rstrip('/'))
    return paths


def reset_code_dir_to_head(code_dir: Path) -> Dict[str, Any]:
    relative_code_dir = _resettable_code_dir_relative_path(code_dir)
    path_arg = str(relative_code_dir)
    outputs_exclude = str(relative_code_dir / 'outputs')

    restore = _run_git(['restore', '--source', 'HEAD', '--staged', '--worktree', '--', path_arg])
    if restore.returncode != 0:
        raise RuntimeError(f'Could not reset tracked files in {path_arg}: {tail_text(restore.stderr or restore.stdout)}')

    clean_preview = _run_git(['clean', '-fd', '--dry-run', '-e', outputs_exclude, '--', path_arg])
    if clean_preview.returncode != 0:
        raise RuntimeError(
            f'Could not preview untracked cleanup in {path_arg}: '
            f'{tail_text(clean_preview.stderr or clean_preview.stdout)}'
        )

    untracked_paths = _clean_preview_paths(clean_preview.stdout or '')
    clean = _run_git(['clean', '-fd', '-e', outputs_exclude, '--', path_arg])
    if clean.returncode != 0:
        raise RuntimeError(f'Could not remove untracked files in {path_arg}: {tail_text(clean.stderr or clean.stdout)}')

    return {
        'code_dir': relative(code_dir),
        'source': 'HEAD',
        'tracked_files_reset': True,
        'untracked_files_deleted_count': len(untracked_paths),
        'untracked_files_deleted': untracked_paths,
        'ignored_files_deleted': False,
    }


def _safe_name(value: str) -> str:
    return re.sub(r'[^A-Za-z0-9_.-]+', '_', value).strip('_') or 'snapshot'


class CodeSnapshotter:
    def __init__(
        self,
        code_dir: Path,
        log_dir: Path,
        logger: ResearchLogger,
        phase_provider: Callable[[], str | None] | None = None,
    ) -> None:
        self.code_dir = code_dir
        self.snapshots_dir = log_dir / 'code_snapshots'
        self.logger = logger
        self.phase_provider = phase_provider
        self._snapshot_index = 0
        self._change_hashes: Dict[Path, str | None] = {}
        self._lock = threading.Lock()

    def snapshot(self, relative_path: Path, trigger: str, phase: str | None = None) -> None:
        source_path = self.code_dir / relative_path
        event_phase = phase if phase is not None else self._current_phase()

        if not source_path.exists():
            self.logger.event(
                'code_snapshot_error',
                {
                    'source_path': relative(source_path),
                    'trigger': trigger,
                    'phase': event_phase,
                    'error': 'source_file_missing',
                },
            )
            return

        try:
            current_hash = sha256_file(source_path)
        except OSError as exc:
            self.logger.event(
                'code_snapshot_error',
                {
                    'source_path': relative(source_path),
                    'trigger': trigger,
                    'phase': event_phase,
                    'error': str(exc),
                },
            )
            return

        with self._lock:
            self._snapshot_index += 1
            snapshot_index = self._snapshot_index
            snapshot_name = (
                f'{snapshot_index:04d}_'
                f'{_safe_name(relative_path.stem)}_'
                f'{_safe_name(trigger)}'
                f'{relative_path.suffix}'
            )
            snapshot_path = self.snapshots_dir / snapshot_name

        try:
            self.snapshots_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, snapshot_path)
        except OSError as exc:
            self.logger.event(
                'code_snapshot_error',
                {
                    'source_path': relative(source_path),
                    'trigger': trigger,
                    'phase': event_phase,
                    'sha256': current_hash,
                    'error': str(exc),
                },
            )
            return

        self.logger.event(
            'code_snapshot',
            {
                'snapshot_index': snapshot_index,
                'source_path': relative(source_path),
                'snapshot_path': relative(snapshot_path),
                'trigger': trigger,
                'phase': event_phase,
                'sha256': current_hash,
            },
        )

    def prepare_change_tracking(self, relative_path: Path) -> None:
        source_path = self.code_dir / relative_path
        try:
            baseline_hash = sha256_file(source_path) if source_path.exists() else None
        except OSError:
            baseline_hash = None
        with self._lock:
            self._change_hashes[relative_path] = baseline_hash

    def snapshot_if_changed(self, relative_path: Path, trigger: str) -> None:
        source_path = self.code_dir / relative_path
        try:
            current_hash = sha256_file(source_path) if source_path.exists() else None
        except OSError as exc:
            self.logger.event(
                'code_snapshot_error',
                {
                    'source_path': relative(source_path),
                    'trigger': trigger,
                    'phase': self._current_phase(),
                    'error': str(exc),
                },
            )
            return

        with self._lock:
            previous_hash = self._change_hashes.get(relative_path)
            if current_hash == previous_hash:
                return
            self._change_hashes[relative_path] = current_hash

        self.snapshot(relative_path, trigger)

    def _current_phase(self) -> str | None:
        if self.phase_provider is None:
            return None
        return self.phase_provider()


class ReportWatcher:
    def __init__(
        self,
        code_dir: Path,
        log_dir: Path,
        logger: ResearchLogger,
        poll_interval_sec: float,
        phase_provider: Callable[[], str | None] | None = None,
        code_snapshotter: CodeSnapshotter | None = None,
    ) -> None:
        self.code_dir = code_dir
        self.report_path = code_dir / REPORT_RELATIVE_PATH
        self.snapshots_dir = log_dir / 'report_snapshots'
        self.logger = logger
        self.poll_interval_sec = poll_interval_sec
        self.phase_provider = phase_provider
        self.code_snapshotter = code_snapshotter
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name='report-watcher', daemon=True)
        self._last_hash: str | None = None
        self._snapshot_index = 0

    def start(self) -> None:
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        if self.code_snapshotter is not None:
            self.code_snapshotter.prepare_change_tracking(DATA_LOADER_RELATIVE_PATH)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=max(self.poll_interval_sec * 2, 2.0))
        if self.code_snapshotter is not None:
            self.code_snapshotter.snapshot_if_changed(DATA_LOADER_RELATIVE_PATH, 'data_loader_changed')

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
        if self.code_snapshotter is not None:
            self.code_snapshotter.snapshot(REPORT_SOURCE_RELATIVE_PATH, 'report_snapshot')

    def _current_phase(self) -> str | None:
        if self.phase_provider is None:
            return None
        return self.phase_provider()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            if self.code_snapshotter is not None:
                self.code_snapshotter.snapshot_if_changed(DATA_LOADER_RELATIVE_PATH, 'data_loader_changed')
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

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


DATA_RELATIVE_PATH = Path('data') / 'product_family_planning_dataset.csv'
REPORT_RELATIVE_PATH = Path('outputs') / 'report.json'
HIDDEN_VERIFIER_PATH = RESEARCH_DIR / 'research_verify.py'

KNOWN_CONDITIONS = {
    'AUT': 'Code - AUT',
    'AUG': 'Code - AUG',
}

SESSION_ID_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z')
EXCLUDED_WORKSPACE_PARTS = {'.git', '__pycache__', '.pytest_cache', '.venv', 'venv'}
EXCLUDED_WORKSPACE_SUFFIXES = {'.pyc', '.pyo', '.tmp'}


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
    if not SESSION_ID_PATTERN.fullmatch(session_id):
        raise ValueError(
            'Session ID must use 1-64 letters, digits, underscores, or hyphens, '
            'and must begin with a letter or digit.'
        )

    resolved_root = logs_root.resolve()
    resolved_log_dir = (resolved_root / session_id).resolve()
    if resolved_log_dir.parent != resolved_root:
        raise ValueError(f'Invalid session log directory: {resolved_log_dir}')
    return resolved_log_dir


def assert_new_session(log_dir: Path) -> None:
    if log_dir.exists():
        raise FileExistsError(
            f'Session log directory already exists: {log_dir}. '
            'Use a new session ID; existing session evidence is never overwritten.'
        )


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


class SessionCheckpointManager:
    """Store the small set of participant-work artifacts needed for review."""

    def __init__(
        self,
        code_dir: Path,
        log_dir: Path,
        logger: ResearchLogger,
        runner: str,
        phase_provider: Callable[[], str | None] | None = None,
    ) -> None:
        self.code_dir = code_dir
        self.log_dir = log_dir
        self.logger = logger
        self.runner = runner
        self.phase_provider = phase_provider
        self.baseline_dir = log_dir / 'baseline'
        self.milestones_dir = log_dir / 'milestones'
        self.reports_dir = log_dir / 'reports'
        self._baseline_workspace: Dict[str, Dict[str, Any]] = {}
        self._task_end_workspace: Dict[str, Dict[str, Any]] | None = None
        self._previous_report_workspace: Dict[str, Dict[str, Any]] = {}
        self._report_index = 0
        self._lock = threading.RLock()

    def capture_baseline(
        self,
        trigger: str = 'session_baseline',
    ) -> Dict[str, Any]:
        with self._lock:
            if self._baseline_workspace:
                raise RuntimeError('Baseline has already been captured for this session')

            workspace = self._workspace_state()
            starter_workspace_dir = self.baseline_dir / 'starter_workspace'
            self._copy_workspace(workspace, starter_workspace_dir)
            self._write_reference(
                self.baseline_dir,
                'Starting environment after reset to committed HEAD.',
            )
            self._write_git_artifacts(self.baseline_dir)
            self._baseline_workspace = workspace
            self._previous_report_workspace = workspace

            event_data = {
                'capture_id': 'baseline',
                'capture_type': 'baseline',
                'trigger': trigger,
                'phase': None,
                'capture_path': relative(self.baseline_dir),
                'changed_file_count': 0,
            }
            self.logger.event('checkpoint_created', event_data)
            return event_data

    def capture_report_created(self, source_report: Path, phase: str | None) -> Dict[str, Any]:
        with self._lock:
            if not self._baseline_workspace:
                raise RuntimeError('Cannot capture a report before the baseline')
            if not source_report.is_file():
                raise FileNotFoundError(f'Report does not exist: {source_report}')

            self._report_index += 1
            stage = self._stage_name(phase)
            capture_id = f'{self._report_index:04d}_{stage}'
            capture_dir = self.reports_dir / capture_id
            report_path = capture_dir / 'report.json'
            capture_dir.mkdir(parents=True, exist_ok=False)
            shutil.copy2(source_report, report_path)

            workspace = self._workspace_state()
            changes = self._workspace_changes(workspace, self._previous_report_workspace)
            self._copy_changed_files(changes, capture_dir / 'changed_files')
            reference = (
                'baseline' if self._report_index == 1
                else f'report {self._report_index - 1:04d}'
            )
            self._write_reference(capture_dir, f'Changed files compared with: {reference}.', changes)
            self._write_git_artifacts(capture_dir)
            self._previous_report_workspace = workspace

            event_data = {
                'capture_id': capture_id,
                'capture_type': 'report',
                'trigger': 'report_created',
                'phase': phase,
                'capture_path': relative(capture_dir),
                'report_path': relative(report_path),
                'report_sha256': sha256_file(report_path),
                'changed_file_count': len(changes),
                'changed_paths': self._change_paths(changes),
            }
            self.logger.event('checkpoint_created', event_data)
            return event_data

    def capture(self, checkpoint_type: str, trigger: str, phase: str | None = None) -> Dict[str, Any]:
        with self._lock:
            if not self._baseline_workspace:
                raise RuntimeError('Cannot capture a milestone before the baseline')

            event_phase = phase if phase is not None else self._current_phase()
            if checkpoint_type == 'task_end':
                milestone_name = '0001_task_end'
                reference_workspace = self._baseline_workspace
                reference = 'baseline'
            elif checkpoint_type in {'review_end', 'review_end_handin'}:
                milestone_name = '0002_review_end'
                reference_workspace = self._task_end_workspace or self._baseline_workspace
                reference = 'task end' if self._task_end_workspace is not None else 'baseline'
            else:
                raise ValueError(f'Unsupported milestone type: {checkpoint_type}')

            milestone_dir = self.milestones_dir / milestone_name
            if milestone_dir.exists():
                raise RuntimeError(f'Milestone has already been captured: {milestone_name}')
            milestone_dir.mkdir(parents=True)
            workspace = self._workspace_state()
            changes = self._workspace_changes(workspace, reference_workspace)
            self._copy_changed_files(changes, milestone_dir / 'changed_files')
            self._write_reference(
                milestone_dir,
                f'Changed files compared with: {reference}.',
                changes,
            )
            self._write_git_artifacts(milestone_dir)
            if checkpoint_type == 'task_end':
                self._task_end_workspace = workspace

            event_data = {
                'capture_id': milestone_name,
                'capture_type': 'milestone',
                'trigger': trigger,
                'phase': event_phase,
                'capture_path': relative(milestone_dir),
                'changed_file_count': len(changes),
                'changed_paths': self._change_paths(changes),
            }
            self.logger.event('checkpoint_created', event_data)
            return event_data

    def _workspace_state(self) -> Dict[str, Dict[str, Any]]:
        workspace: Dict[str, Dict[str, Any]] = {}
        for path in self.code_dir.rglob('*'):
            if not path.is_file() or self._is_excluded_workspace_path(path):
                continue
            relative_path = path.relative_to(self.code_dir).as_posix()
            if relative_path == REPORT_RELATIVE_PATH.as_posix():
                continue
            workspace[relative_path] = {
                'path': relative_path,
                'sha256': sha256_file(path),
                'size_bytes': path.stat().st_size,
            }
        return workspace

    def _is_excluded_workspace_path(self, path: Path) -> bool:
        relative_parts = path.relative_to(self.code_dir).parts
        if any(part in EXCLUDED_WORKSPACE_PARTS for part in relative_parts):
            return True
        return path.suffix.lower() in EXCLUDED_WORKSPACE_SUFFIXES

    def _workspace_changes(
        self,
        workspace: Dict[str, Dict[str, Any]],
        reference_workspace: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        changes: List[Dict[str, Any]] = []
        previous_paths = set(reference_workspace)
        current_paths = set(workspace)

        for path in sorted(current_paths):
            current = workspace[path]
            previous = reference_workspace.get(path)
            if previous is None:
                changes.append({**current, 'change_type': 'added'})
            elif previous['sha256'] != current['sha256']:
                changes.append({**current, 'change_type': 'modified'})

        for path in sorted(previous_paths - current_paths):
            changes.append({
                'path': path,
                'sha256': None,
                'size_bytes': None,
                'change_type': 'deleted',
            })
        return changes

    def _copy_workspace(self, workspace: Dict[str, Dict[str, Any]], destination: Path) -> None:
        for relative_path in sorted(workspace):
            source = self.code_dir / relative_path
            target = destination / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    def _copy_changed_files(self, changes: List[Dict[str, Any]], destination: Path) -> None:
        for change in changes:
            if change['change_type'] != 'deleted':
                source = self.code_dir / change['path']
                target = destination / Path(change['path'])
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

    def _write_reference(
        self,
        capture_dir: Path,
        text: str,
        changes: List[Dict[str, Any]] | None = None,
    ) -> None:
        lines = [text]
        deleted_paths = [change['path'] for change in changes or [] if change['change_type'] == 'deleted']
        if deleted_paths:
            lines.extend(['', 'Deleted files:'])
            lines.extend(f'- {path}' for path in deleted_paths)
        (capture_dir / 'reference.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')

    def _write_git_artifacts(self, capture_dir: Path) -> None:
        code_path = str(_resettable_code_dir_relative_path(self.code_dir))
        commands = {
            'status.txt': ['status', '--porcelain=v1', '--untracked-files=all', '--', code_path],
            'diff.patch': ['diff', '--binary', 'HEAD', '--', code_path],
        }
        git_dir = capture_dir / 'git'
        git_dir.mkdir(parents=True, exist_ok=True)
        for filename, args in commands.items():
            result = _run_git(args)
            if result.returncode != 0:
                raise RuntimeError(f'Could not create {filename}: {tail_text(result.stderr or result.stdout)}')
            path = git_dir / filename
            path.write_text(result.stdout or '', encoding='utf-8')
        metadata = self._git_metadata()
        (git_dir / 'revision.txt').write_text(
            f"branch: {metadata['branch'] or '(detached)'}\nhead: {metadata['head_commit']}\n",
            encoding='utf-8',
        )

    @staticmethod
    def _change_paths(changes: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        return [
            {'path': change['path'], 'change_type': change['change_type']}
            for change in changes
        ]

    @staticmethod
    def _stage_name(phase: str | None) -> str:
        return {
            'task_phase': 'task',
            'review_phase': 'review',
        }.get(phase, 'unknown')

    def _git_metadata(self) -> Dict[str, str | None]:
        branch = _run_git(['branch', '--show-current'])
        commit = _run_git(['rev-parse', 'HEAD'])
        if branch.returncode != 0 or commit.returncode != 0:
            raise RuntimeError('Could not determine Git branch and commit for checkpoint')
        branch_name = (branch.stdout or '').strip() or None
        return {'branch': branch_name, 'head_commit': (commit.stdout or '').strip()}

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
        checkpoint_manager: SessionCheckpointManager | None = None,
    ) -> None:
        self.code_dir = code_dir
        self.report_path = code_dir / REPORT_RELATIVE_PATH
        self.logger = logger
        self.poll_interval_sec = poll_interval_sec
        self.phase_provider = phase_provider
        self.checkpoint_manager = checkpoint_manager
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name='report-watcher', daemon=True)
        self._last_hash: str | None = None
        self._snapshot_index = 0

    def start(self) -> None:
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
        phase = self._current_phase()
        if self.checkpoint_manager is None:
            self.logger.event('report_snapshot_error', {
                'path': relative(self.report_path),
                'error': 'No session capture manager is available.',
                'sha256': current_hash,
                'phase': phase,
            })
            return

        try:
            capture = self.checkpoint_manager.capture_report_created(self.report_path, phase)
            snapshot_path = ROOT / capture['report_path']
            analysis = analyze_report(snapshot_path)
        except Exception as exc:
            self.logger.event('checkpoint_error', {
                'checkpoint_type': 'report_created',
                'phase': phase,
                'report_snapshot_index': self._snapshot_index,
                'error': str(exc),
            })
            return

        analysis.update(
            {
                'snapshot_index': self._snapshot_index,
                'source_path': relative(self.report_path),
                'snapshot_path': capture['report_path'],
                'phase': phase,
                'capture_id': capture['capture_id'],
                'capture_path': capture['capture_path'],
                'sha256': capture['report_sha256'],
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


def session_start_data(session_id: str, condition: str, code_dir: Path, runner: str) -> Dict[str, Any]:
    dataset_path = code_dir / DATA_RELATIVE_PATH
    if not dataset_path.exists():
        raise FileNotFoundError(f'Missing dataset: {dataset_path}')

    branch = _run_git(['branch', '--show-current'])
    commit = _run_git(['rev-parse', 'HEAD'])
    if branch.returncode != 0 or commit.returncode != 0:
        raise RuntimeError('Could not determine Git branch and commit at session start')

    return {
        'session_id': session_id,
        'condition': condition,
        'code_dir': relative(code_dir),
        'dataset_path': relative(dataset_path),
        'dataset_sha256': sha256_file(dataset_path),
        'runner': runner,
        'git_branch': (branch.stdout or '').strip() or None,
        'head_commit': (commit.stdout or '').strip(),
        'python_version': platform.python_version(),
        'platform': platform.platform(),
    }

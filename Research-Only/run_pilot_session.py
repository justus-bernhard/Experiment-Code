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
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESEARCH_DIR = ROOT / 'Research-Only'
LOGGING_DIR = RESEARCH_DIR / 'logging'
sys.path.insert(0, str(LOGGING_DIR))

from pilot_observer import (  # noqa: E402
    REPORT_RELATIVE_PATH,
    ReportWatcher,
    SessionCheckpointManager,
    assert_new_session,
    clear_outputs_dir,
    relative,
    resolve_code_dir,
    resolve_logs_root,
    reset_code_dir_to_head,
    run_hidden_verifier,
    run_public_tests,
    session_start_data,
    session_log_dir,
)
from research_logger import ResearchLogger  # noqa: E402
from report_checks import sha256_file  # noqa: E402
from summarise_session import summarize_log_dir  # noqa: E402


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


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    logger: ResearchLogger | None = None
    watcher: ReportWatcher | None = None
    checkpoint_manager: SessionCheckpointManager | None = None
    session_dir: Path | None = None

    try:
        code_dir = resolve_code_dir(args.code_dir)
        log_dir = resolve_logs_root(args.logs_root)
        session_dir = session_log_dir(log_dir, args.session_id)
        try:
            assert_new_session(session_dir)
        except FileExistsError as exc:
            parser.error(str(exc))

        logger = ResearchLogger(session_dir, args.session_id, args.condition)
        logger.event('code_dir_reset', reset_code_dir_to_head(code_dir))
        logger.event('outputs_cleared', clear_outputs_dir(code_dir))
        logger.event('session_start', session_start_data(args.session_id, args.condition, code_dir, runner='terminal'))
        checkpoint_manager = SessionCheckpointManager(code_dir, session_dir, logger, runner='terminal')
        checkpoint_manager.capture_baseline(runner_metadata={
            'script_path': 'Research-Only/run_pilot_session.py',
            'script_sha256': sha256_file(Path(__file__)),
            'task_phase_seconds': None,
            'review_phase_seconds': None,
        })

        watcher = ReportWatcher(
            code_dir,
            session_dir,
            logger,
            args.poll_interval_sec,
            checkpoint_manager=checkpoint_manager,
        )
        watcher.start()

        print(f'Session {args.session_id} started.')
        print(f'Condition: {args.condition}')
        print(f'Watching: {relative(code_dir / REPORT_RELATIVE_PATH)}')
        print('Press ENTER when participant declares done.')
        input()

        watcher.stop()
        watcher.check_once()
        checkpoint_manager.capture(
            checkpoint_type='review_end_handin',
            trigger='researcher_marked',
            phase=None,
        )
        logger.event('submission_done', {'source': 'researcher_marked'})

        # Hidden verifier must run before public tests, because public tests may
        # regenerate outputs/report.json after the submitted artefact is logged.
        run_hidden_verifier(code_dir, args.command_timeout_sec, logger)
        run_public_tests(code_dir, args.command_timeout_sec, logger)
        logger.event('session_end', {'status': 'completed'})

        summarize_log_dir(session_dir)
        print(f'Summary written to {relative(session_dir / "session_summary.json")}')
        return 0
    except KeyboardInterrupt:
        if watcher is not None:
            watcher.stop()
        if logger is not None:
            logger.event('session_end', {'status': 'interrupted'})
            if session_dir is not None:
                summarize_log_dir(session_dir)
        print('Observer interrupted before completion.', file=sys.stderr)
        return 130
    except Exception as exc:
        if watcher is not None:
            watcher.stop()
        if logger is not None:
            logger.event('session_end', {'status': 'failed', 'error': str(exc)})
            if session_dir is not None:
                summarize_log_dir(session_dir)
        print(f'Observer failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

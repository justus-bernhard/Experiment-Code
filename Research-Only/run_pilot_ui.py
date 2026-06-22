"""Run a pilot session with a small always-on-top timing UI.

Start from the repository root:
  python Research-Only/run_pilot_ui.py

Workflow:
  1. Researcher enters session ID and selects AUT or AUG.
  2. Researcher hands control to the participant on the ready screen.
  3. Participant clicks Start; logging begins and the active condition's
     outputs/ folder is cleared.
  4. The UI runs the task phase, review phase, automatic hand-in, and
     post-submission checks.

The terminal fallback remains:
  python Research-Only/run_pilot_session.py --session-id S001 --condition AUT --code-dir "Code - AUT"
"""

from __future__ import annotations

import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from typing import Any


RESEARCH_DIR = Path(__file__).resolve().parent
LOGGING_DIR = RESEARCH_DIR / 'logging'
if str(LOGGING_DIR) not in sys.path:
    sys.path.insert(0, str(LOGGING_DIR))

from pilot_observer import (  # noqa: E402
    KNOWN_CONDITIONS,
    ReportWatcher,
    SessionCheckpointManager,
    assert_new_session,
    clear_outputs_dir,
    code_dir_for_condition,
    resolve_logs_root,
    reset_code_dir_to_head,
    run_hidden_verifier,
    run_public_tests,
    session_log_dir,
    session_start_data,
)
from research_logger import ResearchLogger  # noqa: E402
from summarise_session import summarize_log_dir  # noqa: E402


TASK_PHASE_SECONDS = 30 * 60
REVIEW_PHASE_SECONDS = 10 * 60
POLL_INTERVAL_SECONDS = 1.0
COMMAND_TIMEOUT_SECONDS = 120.0

BG = '#202124'
PANEL = '#2b2d30'
TEXT = '#f2f2f2'
MUTED = '#a9adb3'
ACCENT = '#8ab4f8'
ACCENT_DARK = '#5f86c5'
RING_BG = '#3b3d40'
ERROR = '#ffb4a9'


class PilotUI:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title('Task Session')
        self.root.geometry('300x360')
        self.root.minsize(280, 330)
        self.root.configure(bg=BG)
        self.root.attributes('-topmost', True)
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)
        self.root.report_callback_exception = self._on_callback_exception

        self.logs_root = resolve_logs_root()
        self.session_id_var = tk.StringVar()
        self.condition_var = tk.StringVar(value='AUT')
        self.error_var = tk.StringVar()

        self.logger: ResearchLogger | None = None
        self.watcher: ReportWatcher | None = None
        self.checkpoint_manager: SessionCheckpointManager | None = None
        self.session_log_dir: Path | None = None
        self.code_dir: Path | None = None
        self.current_phase: str | None = None
        self.active = False
        self.complete = False
        self.timer_after_id: str | None = None
        self.remaining_seconds = 0
        self.total_phase_seconds = 0
        self.phase_deadline: float | None = None

        self.container = tk.Frame(self.root, bg=BG)
        self.container.pack(fill='both', expand=True)
        self._show_setup()

    def run(self) -> int:
        try:
            self.root.mainloop()
            return 0
        except Exception as exc:
            self._log_ui_error(exc)
            self._finish_failed_session(str(exc))
            raise

    def _clear(self) -> None:
        if self.timer_after_id is not None:
            self.root.after_cancel(self.timer_after_id)
            self.timer_after_id = None
        for widget in self.container.winfo_children():
            widget.destroy()

    def _show_setup(self) -> None:
        self._clear()
        self.root.title('Research Setup')

        panel = self._panel()
        self._label(panel, 'Research setup', 15, TEXT).pack(pady=(14, 8))

        self._label(panel, 'Session ID', 9, MUTED, anchor='w').pack(fill='x', padx=20, pady=(8, 3))
        entry = tk.Entry(
            panel,
            textvariable=self.session_id_var,
            bg='#1b1c1e',
            fg=TEXT,
            insertbackground=TEXT,
            relief='flat',
            font=('Segoe UI', 10),
        )
        entry.pack(fill='x', padx=20, ipady=5)
        entry.focus_set()

        self._label(panel, 'Condition', 9, MUTED, anchor='w').pack(fill='x', padx=20, pady=(14, 3))
        option = tk.OptionMenu(panel, self.condition_var, *KNOWN_CONDITIONS.keys())
        option.configure(
            bg='#1b1c1e',
            fg=TEXT,
            activebackground=PANEL,
            activeforeground=TEXT,
            relief='flat',
            highlightthickness=0,
            font=('Segoe UI', 10),
        )
        option['menu'].configure(bg='#1b1c1e', fg=TEXT, activebackground=PANEL, activeforeground=TEXT)
        option.pack(fill='x', padx=20, ipady=2)

        self._label(panel, textvariable=self.error_var, size=8, color=ERROR).pack(pady=(10, 0))
        self._button(panel, 'Continue', self._prepare_ready).pack(pady=(14, 16), ipadx=16, ipady=6)

    def _prepare_ready(self) -> None:
        session_id = self.session_id_var.get().strip()
        condition = self.condition_var.get().strip()
        self.error_var.set('')

        if not session_id:
            self.error_var.set('Enter a session ID.')
            return
        if condition not in KNOWN_CONDITIONS:
            self.error_var.set('Select AUT or AUG.')
            return

        try:
            code_dir = code_dir_for_condition(condition)
            log_dir = session_log_dir(self.logs_root, session_id)
            assert_new_session(log_dir)
        except Exception as exc:
            self.error_var.set(str(exc))
            return

        self.code_dir = code_dir
        self.session_log_dir = log_dir
        self._show_ready()

    def _show_ready(self) -> None:
        self._clear()
        self.root.title('Task Session')
        panel = self._panel()
        self._label(panel, 'Ready to begin', 17, TEXT).pack(pady=(44, 10))
        self._label(panel, 'Press Start when you are ready.', 10, MUTED).pack(pady=(0, 30))
        self._button(panel, 'Start', self._start_session).pack(ipadx=24, ipady=8)

    def _start_session(self) -> None:
        if self.session_log_dir is None or self.code_dir is None:
            return

        session_id = self.session_id_var.get().strip()
        condition = self.condition_var.get().strip()

        try:
            assert_new_session(self.session_log_dir)
            self.logger = ResearchLogger(self.session_log_dir, session_id, condition)
            self.logger.event('code_dir_reset', reset_code_dir_to_head(self.code_dir))
            self.logger.event('outputs_cleared', clear_outputs_dir(self.code_dir))
            self.logger.event('session_start', session_start_data(session_id, condition, self.code_dir, runner='ui'))
            self.logger.event('participant_start_clicked', {})
            self.checkpoint_manager = SessionCheckpointManager(
                self.code_dir,
                self.session_log_dir,
                self.logger,
                runner='ui',
                phase_provider=lambda: self.current_phase,
            )
            self.checkpoint_manager.capture_baseline()
            self.logger.event('ui_ready', {'always_on_top': True})
            self.current_phase = 'task_phase'
            self.logger.event('task_phase_start', {'duration_sec': TASK_PHASE_SECONDS})

            self.watcher = ReportWatcher(
                self.code_dir,
                self.session_log_dir,
                self.logger,
                POLL_INTERVAL_SECONDS,
                phase_provider=lambda: self.current_phase,
                checkpoint_manager=self.checkpoint_manager,
            )
            self.watcher.start()
        except Exception as exc:
            messagebox.showerror('Session could not start', str(exc))
            self._log_ui_error(exc)
            return

        self.active = True
        self._show_task_phase()

    def _show_task_phase(self) -> None:
        self._show_timer(
            phase='task_phase',
            title='Task phase',
            helper='Work on the report.',
            duration_sec=TASK_PHASE_SECONDS,
            button_text='I am done with the task',
            button_command=lambda: self._end_task_phase('participant_done_clicked', clicked=True),
        )

    def _show_review_phase(self) -> None:
        self._show_timer(
            phase='review_phase',
            title='Review phase',
            helper='Review your work and make final changes.',
            duration_sec=REVIEW_PHASE_SECONDS,
            button_text=None,
            button_command=None,
            footer='Early hand-in is not possible.',
        )

    def _show_timer(
        self,
        phase: str,
        title: str,
        helper: str,
        duration_sec: int,
        button_text: str | None,
        button_command: Any,
        footer: str | None = None,
    ) -> None:
        self._clear()
        self.current_phase = phase
        self.remaining_seconds = duration_sec
        self.total_phase_seconds = duration_sec
        self.phase_deadline = time.monotonic() + duration_sec

        panel = self._panel()
        self._label(panel, title, 15, TEXT).pack(pady=(12, 3))
        self._label(panel, helper, 9, MUTED).pack(pady=(0, 10))

        canvas = tk.Canvas(panel, width=170, height=170, bg=PANEL, highlightthickness=0)
        canvas.pack(pady=(0, 8))
        canvas.create_oval(15, 15, 155, 155, outline=RING_BG, width=8, tags='ring_bg')
        canvas.create_arc(
            15,
            15,
            155,
            155,
            start=90,
            extent=359.9,
            style='arc',
            outline=ACCENT,
            width=8,
            tags='ring',
        )
        canvas.create_text(85, 80, text='', fill=TEXT, font=('Segoe UI', 24, 'bold'), tags='time')
        canvas.create_text(85, 111, text='remaining', fill=MUTED, font=('Segoe UI', 8), tags='caption')

        if button_text and button_command:
            self._button(panel, button_text, button_command).pack(pady=(2, 6), ipadx=8, ipady=6)
        if footer:
            self._label(panel, footer, 9, MUTED).pack(pady=(6, 0))

        self._tick_timer(canvas)

    def _tick_timer(self, canvas: tk.Canvas) -> None:
        if self.phase_deadline is None:
            return

        remaining_float = max(0.0, self.phase_deadline - time.monotonic())
        self.remaining_seconds = int(remaining_float + 0.999)
        minutes, seconds = divmod(max(self.remaining_seconds, 0), 60)
        canvas.itemconfigure('time', text=f'{minutes:02d}:{seconds:02d}')

        progress = 0 if self.total_phase_seconds == 0 else remaining_float / self.total_phase_seconds
        canvas.itemconfigure('ring', extent=max(progress * 359.9, 0.1))

        if remaining_float <= 0:
            if self.current_phase == 'task_phase':
                self._end_task_phase('timer_elapsed', clicked=False)
            elif self.current_phase == 'review_phase':
                self._end_review_phase()
            return

        next_delay_ms = min(250, max(25, int(remaining_float * 1000)))
        self.timer_after_id = self.root.after(next_delay_ms, lambda: self._tick_timer(canvas))

    def _end_task_phase(self, reason: str, clicked: bool) -> None:
        if self.timer_after_id is not None:
            self.root.after_cancel(self.timer_after_id)
            self.timer_after_id = None
        self.phase_deadline = None
        if self.current_phase != 'task_phase':
            return

        if self.logger is not None and clicked:
            self.logger.event('task_done_clicked', {'phase': 'task_phase'})
        if self.checkpoint_manager is not None:
            self.checkpoint_manager.capture(
                checkpoint_type='task_end',
                trigger=reason,
                phase='task_phase',
            )
        if self.logger is not None:
            self.logger.event('task_phase_end', {'reason': reason})

        self.current_phase = 'review_phase'
        if self.logger is not None:
            self.logger.event('review_phase_start', {'duration_sec': REVIEW_PHASE_SECONDS})
        self._show_review_phase()

    def _end_review_phase(self) -> None:
        if self.timer_after_id is not None:
            self.root.after_cancel(self.timer_after_id)
            self.timer_after_id = None
        self.phase_deadline = None
        if self.current_phase != 'review_phase':
            return

        if self.logger is not None:
            self.logger.event('review_phase_end', {'reason': 'timer_elapsed'})
        if self.watcher is not None:
            self.watcher.stop()
            self.watcher.check_once()

        if self.checkpoint_manager is not None:
            self.checkpoint_manager.capture(
                checkpoint_type='review_end',
                trigger='review_timer_elapsed',
                phase='review_phase',
            )

        if self.logger is not None:
            self.logger.event('submission_done', {'source': 'review_timer_elapsed'})

        self.current_phase = None
        self.active = False
        self.complete = True
        self._show_complete()
        self._run_post_submission_checks()

    def _run_post_submission_checks(self) -> None:
        thread = threading.Thread(target=self._post_submission_worker, name='post-submission-checks')
        thread.start()

    def _post_submission_worker(self) -> None:
        if self.logger is None or self.code_dir is None or self.session_log_dir is None:
            return
        try:
            run_hidden_verifier(self.code_dir, COMMAND_TIMEOUT_SECONDS, self.logger)
            run_public_tests(self.code_dir, COMMAND_TIMEOUT_SECONDS, self.logger)
            self.logger.event('session_end', {'status': 'completed'})
        except Exception as exc:
            self.logger.event('ui_error', {'error': str(exc)})
            self.logger.event('session_end', {'status': 'failed', 'error': str(exc)})
        finally:
            summarize_log_dir(self.session_log_dir)

    def _show_complete(self) -> None:
        self._clear()
        panel = self._panel()
        self._label(panel, 'Session complete', 17, TEXT).pack(pady=(54, 12))
        self._label(
            panel,
            'Your work has been handed in.\nPlease wait for the researcher.',
            10,
            MUTED,
        ).pack(pady=(0, 18))

    def _on_close(self) -> None:
        if self.active:
            if self.logger is not None:
                self.logger.event('ui_close_attempted', {'phase': self.current_phase})
            messagebox.showinfo('Session active', 'The session is active. Please wait for the researcher.')
            return
        self.root.destroy()

    def _log_ui_error(self, exc: Exception) -> None:
        if self.logger is not None:
            self.logger.event('ui_error', {'error': str(exc), 'phase': self.current_phase})

    def _on_callback_exception(self, exc_type: type[BaseException], exc: BaseException, tb: Any) -> None:
        self._log_ui_error(Exception(str(exc)))
        self._finish_failed_session(str(exc))
        messagebox.showerror('Session error', 'The session window encountered an error. Please contact the researcher.')

    def _finish_failed_session(self, error: str) -> None:
        if self.watcher is not None:
            self.watcher.stop()
        if self.logger is not None:
            self.logger.event('session_end', {'status': 'failed', 'error': error})
            if self.session_log_dir is not None:
                summarize_log_dir(self.session_log_dir)

    def _panel(self) -> tk.Frame:
        panel = tk.Frame(self.container, bg=PANEL)
        panel.pack(fill='both', expand=True, padx=10, pady=10)
        return panel

    def _label(
        self,
        parent: tk.Widget,
        text: str | None = None,
        size: int = 11,
        color: str = TEXT,
        anchor: str = 'center',
        textvariable: tk.StringVar | None = None,
    ) -> tk.Label:
        return tk.Label(
            parent,
            text=text,
            textvariable=textvariable,
            bg=PANEL,
            fg=color,
            font=('Segoe UI', size),
            anchor=anchor,
            justify='center',
            wraplength=250,
        )

    def _button(self, parent: tk.Widget, text: str, command: Any) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=ACCENT,
            fg='#101214',
            activebackground=ACCENT_DARK,
            activeforeground='#101214',
            relief='flat',
            borderwidth=0,
            font=('Segoe UI', 10, 'bold'),
            cursor='hand2',
        )


def main() -> int:
    return PilotUI().run()


if __name__ == '__main__':
    raise SystemExit(main())

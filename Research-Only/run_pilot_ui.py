"""Run a pilot session with a small always-on-top timing UI."""

from __future__ import annotations

import sys
import threading
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
    assert_new_session,
    clear_outputs_dir,
    code_dir_for_condition,
    resolve_logs_root,
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
        self.root.title('Focus Session')
        self.root.geometry('380x460')
        self.root.minsize(340, 420)
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
        self.session_log_dir: Path | None = None
        self.code_dir: Path | None = None
        self.current_phase: str | None = None
        self.active = False
        self.complete = False
        self.timer_after_id: str | None = None
        self.remaining_seconds = 0
        self.total_phase_seconds = 0

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
        self._label(panel, 'Research setup', 18, TEXT).pack(pady=(20, 10))

        self._label(panel, 'Session ID', 10, MUTED, anchor='w').pack(fill='x', padx=28, pady=(10, 4))
        entry = tk.Entry(
            panel,
            textvariable=self.session_id_var,
            bg='#1b1c1e',
            fg=TEXT,
            insertbackground=TEXT,
            relief='flat',
            font=('Segoe UI', 12),
        )
        entry.pack(fill='x', padx=28, ipady=7)
        entry.focus_set()

        self._label(panel, 'Condition', 10, MUTED, anchor='w').pack(fill='x', padx=28, pady=(18, 4))
        option = tk.OptionMenu(panel, self.condition_var, *KNOWN_CONDITIONS.keys())
        option.configure(
            bg='#1b1c1e',
            fg=TEXT,
            activebackground=PANEL,
            activeforeground=TEXT,
            relief='flat',
            highlightthickness=0,
            font=('Segoe UI', 11),
        )
        option['menu'].configure(bg='#1b1c1e', fg=TEXT, activebackground=PANEL, activeforeground=TEXT)
        option.pack(fill='x', padx=28, ipady=3)

        self._label(panel, textvariable=self.error_var, size=9, color=ERROR).pack(pady=(14, 0))
        self._button(panel, 'Continue', self._prepare_ready).pack(pady=(18, 24), ipadx=20, ipady=8)

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
        self.root.title('Focus Session')
        panel = self._panel()
        self._label(panel, 'Ready to begin', 20, TEXT).pack(pady=(58, 12))
        self._label(panel, 'Press Start when you are ready.', 11, MUTED).pack(pady=(0, 42))
        self._button(panel, 'Start', self._start_session).pack(ipadx=28, ipady=10)

    def _start_session(self) -> None:
        if self.session_log_dir is None or self.code_dir is None:
            return

        session_id = self.session_id_var.get().strip()
        condition = self.condition_var.get().strip()

        try:
            assert_new_session(self.session_log_dir)
            self.logger = ResearchLogger(self.session_log_dir, session_id, condition)
            self.logger.event('outputs_cleared', clear_outputs_dir(self.code_dir))
            self.logger.event('session_start', session_start_data(session_id, condition, self.code_dir))
            self.logger.event('participant_start_clicked', {})
            self.current_phase = 'task_phase'
            self.logger.event('task_phase_start', {'duration_sec': TASK_PHASE_SECONDS})
            self.logger.event('ui_ready', {'always_on_top': True})

            self.watcher = ReportWatcher(
                self.code_dir,
                self.session_log_dir,
                self.logger,
                POLL_INTERVAL_SECONDS,
                phase_provider=lambda: self.current_phase,
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

        panel = self._panel()
        self._label(panel, title, 18, TEXT).pack(pady=(18, 4))
        self._label(panel, helper, 10, MUTED).pack(pady=(0, 14))

        canvas = tk.Canvas(panel, width=230, height=230, bg=PANEL, highlightthickness=0)
        canvas.pack(pady=(0, 12))
        canvas.create_oval(20, 20, 210, 210, outline=RING_BG, width=12, tags='ring_bg')
        canvas.create_arc(
            20,
            20,
            210,
            210,
            start=90,
            extent=359.9,
            style='arc',
            outline=ACCENT,
            width=12,
            tags='ring',
        )
        canvas.create_text(115, 108, text='', fill=TEXT, font=('Segoe UI', 34, 'bold'), tags='time')
        canvas.create_text(115, 145, text='remaining', fill=MUTED, font=('Segoe UI', 10), tags='caption')

        if button_text and button_command:
            self._button(panel, button_text, button_command).pack(pady=(4, 8), ipadx=12, ipady=8)
        if footer:
            self._label(panel, footer, 10, MUTED).pack(pady=(8, 0))

        self._tick_timer(canvas)

    def _tick_timer(self, canvas: tk.Canvas) -> None:
        minutes, seconds = divmod(max(self.remaining_seconds, 0), 60)
        canvas.itemconfigure('time', text=f'{minutes:02d}:{seconds:02d}')

        progress = 0 if self.total_phase_seconds == 0 else self.remaining_seconds / self.total_phase_seconds
        canvas.itemconfigure('ring', extent=max(progress * 359.9, 0.1))

        if self.remaining_seconds <= 0:
            if self.current_phase == 'task_phase':
                self._end_task_phase('timer_elapsed', clicked=False)
            elif self.current_phase == 'review_phase':
                self._end_review_phase()
            return

        self.remaining_seconds -= 1
        self.timer_after_id = self.root.after(1000, lambda: self._tick_timer(canvas))

    def _end_task_phase(self, reason: str, clicked: bool) -> None:
        if self.timer_after_id is not None:
            self.root.after_cancel(self.timer_after_id)
            self.timer_after_id = None
        if self.current_phase != 'task_phase':
            return

        if self.logger is not None and clicked:
            self.logger.event('task_done_clicked', {'phase': 'task_phase'})
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
        if self.current_phase != 'review_phase':
            return

        if self.logger is not None:
            self.logger.event('review_phase_end', {'reason': 'timer_elapsed'})

        if self.watcher is not None:
            self.watcher.stop()
            self.watcher.check_once()

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
        self._label(panel, 'Session complete', 20, TEXT).pack(pady=(72, 14))
        self._label(
            panel,
            'Your work has been handed in.\nPlease wait for the researcher.',
            12,
            MUTED,
        ).pack(pady=(0, 24))

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
        panel.pack(fill='both', expand=True, padx=16, pady=16)
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
            font=('Segoe UI', 11, 'bold'),
            cursor='hand2',
        )


def main() -> int:
    return PilotUI().run()


if __name__ == '__main__':
    raise SystemExit(main())

# Pilot Logging Plan

Date: 2026-04-27

Purpose: Define a functioning pilot logging layer for the collaborative disagreement experiment without creating variables that cannot actually be measured.

## Protocol Review

The experimental protocol requires logging and derived variables for:

- RQ1 collaborative disagreement: whether and when the participant corrects the product-family labeling inconsistency.
- RQ2 blame/responsibility: post-task Likert items and awareness questions.
- Performance: time to completion and task success.
- Verification behavior: dataset inspection, output inspection, test execution, and active review time.
- Additional logging: prompts and timestamps for prompts, file opens, tests, and submission.

For the pilot, the intervention variable should be operationalized only through `report.json` snapshots. The first snapshot whose `by_product_family` labels semantically normalize to the five expected product families is the first intervention event. Do not infer intervention from prompts, source-code edits, or participant intent.

Expected semantic product families:

```text
industrial sensors
control units
power modules
safety components
communication modules
```

Display casing and surrounding whitespace are not part of the main intervention DV. For example, `Industrial Sensors`, `industrial sensors`, and `Industrial Sensors ` all count as the same semantic group. Exact canonical display labels are retained as a secondary diagnostic only.

## A) Implemented For Pilot

These items are implemented in the hidden research wrapper:

```powershell
python Research-Only/run_pilot_ui.py
python Research-Only/run_pilot_session.py --session-id S001 --condition AUT --code-dir "Code - AUT"
```

`run_pilot_ui.py` is required for formal sessions because it enforces the task
and review phases. `run_pilot_session.py` remains available for development or
recovery only.

Supporting modules:

- `Research-Only/logging/research_logger.py`
- `Research-Only/logging/report_checks.py`
- `Research-Only/logging/summarise_session.py`
- `Research-Only/pilot_observer.py`
- `Research-Only/research_verify.py`

- `outputs_cleared`: recorded immediately before `session_start` after the active condition's `outputs/` folder is emptied.
- `session_start`: recorded when the participant starts the session from the UI, or when the researcher starts the terminal fallback.
- `participant_start_clicked`: recorded when the participant starts the UI session.
- `task_phase_start` and `task_phase_end`: recorded around the 30-minute task phase.
- `task_done_clicked`: recorded if the participant ends the task phase before the timer elapses.
- `review_phase_start` and `review_phase_end`: recorded around the fixed 5-minute review phase.
- `ui_close_attempted`: recorded if the participant tries to close the UI during an active task or review phase. The close is blocked.
- `session_end`: recorded after post-submission checks, before the final summary is written.
- `submission_done`: recorded automatically when the UI review timer ends, or when the researcher marks the first participant "done" signal in the terminal fallback.
- `time_to_completion_sec`: computed as `submission_done - session_start`.
- `report_snapshot`: recorded whenever `outputs/report.json` appears or changes.
- `checkpoint_created`: recorded for the baseline, every report-created state,
  task end, and review end. Captures store the relevant changed files and Git
  status, diff, and revision evidence.
- `report_snapshot.data.phase`: records `task_phase` or `review_phase` for UI sessions.
- `first_report_sec`: timestamp of the first observed report snapshot relative to session start.
- `first_intervention_sec`: timestamp of the first semantically passing report snapshot relative to session start.
- `reports`: chronological report history, including phase, labels, schema validity,
  semantic pass, canonical-display pass, and the saved report path.
- `outcome.intervention_detected` and `outcome.intervention_stage`: whether any
  report before submission normalized to the five semantic families, and when.
- `outcome.final_report`: the final report outcome before submission.
- `tests.public` and `tests.hidden`: post-submission public-test and hidden-verifier results.
- `environment.dataset_sha256`: hash of the dataset at session start.
- `events.jsonl`: append-only event stream using the `event.v3` envelope with event-specific data under `data`.
- `session_summary.json`: one concise, researcher-readable `session_summary.v4` record per participant.
- `artifacts.manual_chat_log`: the manually exported `chat.md` file in the
  session log folder, with its path, hash, export timestamp, and availability
  recorded in the session summary.
- `logging.manual_chat_log_available`: whether the required manual prompt-log
  artifact has been attached to the session.

The UI shows only neutral timing and phase information. It should not show correctness details, hidden-check results, intervention status, or label warnings during the task.

## B) To Be Implemented Next

These items are feasible but should follow after the core wrapper works.

- Questionnaire event import or entry for pre-reveal awareness:
  - `pre_reveal_awareness`
  - `pre_reveal_awareness_text`
- Questionnaire event import or entry for post-reveal awareness:
  - `post_reveal_awareness`
- Questionnaire event import or entry for blame/responsibility Likert items:
  - `blame_ai_responsible`
  - `blame_self_responsible`
  - `blame_shared`
  - `blame_overrelied_ai`
  - `blame_ai_misleading`
- Place the required manually exported Copilot chat log at
  `Research-Only/logs/<session_id>/chat.md` after each session, then regenerate
  the summary to record its path, hash, export timestamp, and availability.
- Optional command/test-run instrumentation if participants are required to run commands through a wrapper.
- Export helper that combines all `session_summary.json` files into one CSV for analysis.
- Validation script that flags missing fields, unavailable fields, malformed timestamps, or impossible timings.

## C) Blockers And Difficult Items

These should not be treated as available pilot variables unless extra instrumentation is added.

- Native GitHub Copilot Chat does not provide an automatic per-session transcript API; prompts and responses are therefore exported and attached manually.
- GitHub Copilot usage metrics are aggregated/delayed telemetry and do not provide full prompt text for qualitative analysis.
- VS Code Chat APIs can access prompts only for a custom chat participant contributed by our own extension, not for all native Copilot Chat prompts.
- Dataset file-open logging is not reliable from a Python wrapper alone. It requires editor extension instrumentation, OS-level monitoring, or a controlled experiment UI.
- Output file-open logging has the same limitation as dataset file-open logging.
- During-task test execution timing is only reliable if commands are run through an instrumented shell/wrapper or captured by an IDE extension.
- Dataset file-open logging, output file-open logging, and during-task command logging remain unavailable unless extra instrumentation is added. Copilot prompts and responses are handled through the required manual export artifact rather than automatic runner capture.
- Running the observer from another machine is only reliable if it has real-time access to the participant filesystem. OneDrive or network-sync timestamps may distort timing.

## D) Artifact And Audit Design

- Store the complete participant starter workspace once under
  `baseline/starter_workspace/`, including task materials, starter files, tests,
  dataset, and repository-controlled Copilot instruction/configuration files.
- Store Git `status.txt`, `diff.patch`, and `revision.txt` in every baseline,
  milestone, and report capture.
- Store task end and review end under `milestones/0001_task_end/` and
  `milestones/0002_review_end/`. Task-end changed files are compared with the
  baseline; review-end changed files are compared with task end.
- Store every generated report under `reports/<number>_<stage>/report.json`.
  That folder also holds files changed since the prior report capture, plus Git
  evidence. The first report is compared with baseline.
- Keep `events.jsonl` as the raw timestamped event record and
  `session_summary.json` as the concise outcome summary. Do not generate
  manifests, a separate timeline, or per-command output files.
- Compute semantic normalization correctness and strict canonical-display correctness for each report snapshot immediately.
- Store report validity, labels, semantic normalization correctness,
  canonical-display correctness, group counts, and report hash for every report.
- Add `dataset_sha256` for provenance.
- Add a hidden post-submission evaluator that runs public tests and hidden verifier after the participant is done.
- Use the UI runner to enforce the 30-minute task phase, 5-minute review phase, and automatic hand-in.
- Add a summary-to-CSV export script for easy analysis across participants.
- Add an optional custom VS Code chat participant, such as `@study`, only if prompt logging becomes essential. This would log prompts reliably but would change the participant workflow.

## Short Summary

The current logging environment runs as a hidden researcher observer on the participant machine. The formal UI runner resets the active condition to committed `HEAD`, records session and phase events, captures the starter workspace, watches `outputs/report.json`, computes semantic product-family normalization correctness plus strict display-label diagnostics, enforces a 5-minute review phase, and automatically hands in at review end. After completion, it runs hidden and public checks and writes `events.jsonl` and `session_summary.json` under `Research-Only/logs/<session_id>/`.

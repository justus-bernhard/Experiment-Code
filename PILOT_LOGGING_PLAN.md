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
- `review_phase_start` and `review_phase_end`: recorded around the fixed 10-minute review phase.
- `ui_close_attempted`: recorded if the participant tries to close the UI during an active task or review phase. The close is blocked.
- `session_end`: recorded after post-submission checks, before the final summary and manifest are written.
- `submission_done`: recorded automatically when the UI review timer ends, or when the researcher marks the first participant "done" signal in the terminal fallback.
- `time_to_completion_sec`: computed as `submission_done - session_start`.
- `report_snapshot`: recorded whenever `outputs/report.json` appears or changes.
- `checkpoint_created`: recorded for the baseline, every report-created state,
  task end, and review-end hand-in. Each checkpoint stores a workspace manifest,
  Git status/diff, changed-file evidence, and a reference to the latest report.
- `report_snapshot.data.phase`: records `task_phase` or `review_phase` for UI sessions.
- `report_snapshot_count`: count of observed report versions.
- `task_phase_report_snapshot_count` and `review_phase_report_snapshot_count`: phase-specific snapshot counts for UI sessions.
- `diagnostics.ui.ui_close_attempted_count`: count of blocked active-session close attempts.
- `diagnostics.ui.ui_closed_before_completion`: whether the UI actually closed before a normal completed session end.
- `first_report_sec`: timestamp of the first observed report snapshot relative to session start.
- `first_intervention_sec`: timestamp of the first semantically passing report snapshot relative to session start.
- `artifacts.final_report_sha256`: SHA-256 hash of the last report before submission.
- `report_outcome.semantic_pass`: whether the final report before submission has the five expected semantic product families.
- `primary_outcome.intervention_binary`: whether any report snapshot before or at submission normalizes to the five expected semantic product families.
- `primary_outcome.intervention_stage`: `task_phase`, `review_phase`, `none`, or unavailable for legacy terminal sessions.
- `primary_outcome.intervention_source`: fixed value `first_semantic_pass_report_snapshot`.
- `report_outcome.canonical_pass`: secondary diagnostic for exact canonical display labels.
- `provenance.dataset_sha256`: SHA-256 hash of the dataset at session start.
- `public_tests_passed` and `public_tests_total`: measured by post-submission public test execution.
- `hidden_tests_passed` and `hidden_tests_total`: measured by post-submission hidden verifier.
- `events.jsonl`: append-only event stream using the `event.v3` envelope with event-specific data under `data`.
- `session_summary.json`: one nested, researcher-readable `session_summary.v3` record per participant.
- `session_manifest.json`: hashes of the session evidence artifacts.
- `manual_chat_log`: the manually exported `chat.md` file in the session log
  folder, with its path, hash, file modification time, and availability
  recorded in the session summary.
- `process.manual_prompt_log_available`: whether the required manual prompt-log
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
- Attach the required manually exported Copilot chat log after each session.
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
- Dataset file-open logging, output file-open logging, and during-task command logging remain unavailable unless extra instrumentation is added. Copilot prompts and responses are handled through the required manual export artifact.
- Running the observer from another machine is only reliable if it has real-time access to the participant filesystem. OneDrive or network-sync timestamps may distort timing.

Unavailable pilot fields should be represented explicitly as unavailable, not as zero.

Example:

```json
{
  "manual_prompt_log_available": false,
  "dataset_open_logging_available": false,
  "dataset_opened": null,
  "test_run_process_logging_available": false,
  "test_run_count": null
}
```

## D) Artifact And Audit Design

- Store every changed `report.json` as a copied snapshot under `Research-Only/logs/<session_id>/report_snapshots/`.
- Store a complete participant-environment bundle at baseline, including task
  materials, starter files, tests, dataset, and repository-controlled Copilot
  instruction/configuration files.
- Store the same core checkpoint structure for baseline, report-created, task-end,
  and review-end/hand-in states. Baseline additionally stores the participant
  environment; report-created states additionally preserve the new report and
  current `report.py`.
- Compute semantic normalization correctness and strict canonical-display correctness for each report snapshot immediately.
- Store `valid_json`, `product_family_labels`, `reported_group_count`, `unique_semantic_family_count`, `product_family_record_count_total`, `semantic_normalization_pass`, `normalization_status`, `display_labels_canonical`, and report hash for every snapshot. In `session_summary.json`, these are summarized as `semantic_pass`, `canonical_pass`, `normalization_status`, `reported_group_count`, `unique_semantic_family_count`, and `product_family_record_count_total`.
- Include `intervention_source` to make the operational definition explicit in the summary.
- Add `final_report_sha256` for reproducibility.
- Add `dataset_sha256` for provenance.
- Add a hidden post-submission evaluator that runs public tests and hidden verifier after the participant is done.
- Use the UI runner to enforce the 30-minute task phase, 10-minute review phase, and automatic hand-in.
- Add a summary-to-CSV export script for easy analysis across participants.
- Add an optional custom VS Code chat participant, such as `@study`, only if prompt logging becomes essential. This would log prompts reliably but would change the participant workflow.

## Short Summary

The current logging environment runs as a hidden researcher observer on the participant machine. The formal UI runner resets the active condition to committed `HEAD`, records session and phase events, writes workspace checkpoints, watches `outputs/report.json`, computes semantic product-family normalization correctness plus strict display-label diagnostics, enforces a 10-minute review phase, and automatically hands in at review end. After completion, it runs hidden and public checks and writes `events.jsonl`, `session_summary.json`, a readable `timeline.md`, and `session_manifest.json` under `Research-Only/logs/<session_id>/`.

# Researcher Setup

Before each experiment session, prepare the Python environment so participants
can run the task commands immediately.

Before running a formal session, make sure the intended participant baseline
and the `Research-Only` runner are committed. The UI resets the selected
condition folder to committed `HEAD` when the participant starts, so uncommitted
changes inside that condition folder will be discarded.

From the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r "Code - AUT\requirements.txt"
```

The AUT and AUG requirements are intentionally identical, so installing one
requirements file into the shared environment is sufficient.

Quick check:

```powershell
cd "Code - AUT"
python tools\check_env.py
python -m src.main
pytest -q
```

Repeat the quick check in `Code - AUG` if you changed anything in the
participant-facing code.

## Formal Sessions

Use `python Research-Only/run_pilot_ui.py` for formal sessions. The terminal
runner remains available for development or recovery, but it does not enforce
the task and review phases.

Each formal session creates a new folder under `Research-Only/logs/`. Session
IDs must be unique, pseudonymous identifiers using letters, digits, underscores,
or hyphens. Existing session folders are never overwritten.

The runner records the full baseline environment, every generated report, and
task-end and review-end milestones. Each capture includes its relevant changed
files and Git status, diff, and revision. After completion, verify
`session_summary.json` and copy the entire session folder to the approved
encrypted or cloud-backed study storage.

Copilot prompts and responses are exported manually after each session. Place
the export at `Research-Only/logs/<session_id>/chat.md`, then regenerate the
session summary:

```powershell
python Research-Only/logging/summarise_session.py "Research-Only/logs/P0001"
```

The summary records the `chat.md` path, hash, export timestamp, and
availability.

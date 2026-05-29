# Researcher Setup

Before each experiment session, prepare the Python environment so participants
can run the task commands immediately.

Before running a real session, make sure the intended participant baseline in
`Code - AUT` and `Code - AUG` is committed. The pilot UI resets the selected
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

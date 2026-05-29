# Researcher Setup

Before each experiment session, prepare the Python environment so participants
can run the task commands immediately.

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

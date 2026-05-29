@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "Research-Only\run_pilot_ui.py"
) else (
  python "Research-Only\run_pilot_ui.py"
)

if errorlevel 1 (
  echo.
  echo Pilot UI exited with an error.
  pause
)

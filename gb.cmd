@echo off
rem Run Python for this project: "gb.cmd tools\build_report.py" or "gb.cmd -m evals.runners.judge_calibration --kappa".
rem Uses the base uv Python plus the venv packages (the venv launcher is blocked by Smart App Control on this laptop).
setlocal
set "PYTHONPATH=%~dp0tools\venvshim"
set "VIRTUAL_ENV=%~dp0.venv"
set "PYTHONIOENCODING=utf-8"
for /d %%D in ("%APPDATA%\uv\python\cpython-3.12*-windows-x86_64-none") do set "GBPY=%%D\python.exe"
if not defined GBPY (echo uv Python 3.12 not found. Run: uv python install 3.12 & exit /b 1)
"%GBPY%" %*

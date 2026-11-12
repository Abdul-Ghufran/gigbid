"""Loaded by gb.cmd: puts the project venv's packages (and the project root) on the path of the base uv Python.

Why: Windows Smart App Control blocks the venv's own python.exe launcher on the dev laptop, while the base
interpreter that uv installed is allowed. The venv's .pth hooks (editable install, pywin32) still run via addsitedir."""
import os
import site
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
site.addsitedir(os.path.join(ROOT, ".venv", "Lib", "site-packages"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

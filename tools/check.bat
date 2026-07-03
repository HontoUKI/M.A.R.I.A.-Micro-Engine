@echo off
rem Lint + tests, single gate before any commit.
ruff check .
if errorlevel 1 exit /b 1
python -m pytest -q

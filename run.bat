@echo off
REM Invoice Extractor - double-click to run.
REM First run: creates a private Python environment and installs what is needed (1-2 minutes).
cd /d "%~dp0"
title Invoice Extractor

REM ---- Find Python: environment already created, "py" launcher, "python" on PATH, or the usual install folders
set "PY="
if exist ".venv\Scripts\python.exe" goto run

where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && python -c "import sys" >nul 2>nul && set "PY=python"
)
if not defined PY (
  for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%D\python.exe" set "PY="%%D\python.exe""
)
if not defined PY (
  for /d %%D in ("%ProgramFiles%\Python3*") do if exist "%%D\python.exe" set "PY="%%D\python.exe""
)
if not defined PY (
  echo Python was not found on this computer.
  echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause
  exit /b 1
)

echo Setting up for the first time, please wait...
%PY% -m venv .venv
if not exist ".venv\Scripts\python.exe" (
  echo Could not create the Python environment.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
if errorlevel 1 (
  echo Installation failed. Check your internet connection and try again.
  pause
  exit /b 1
)

:run
".venv\Scripts\python.exe" invoice_extractor.py
echo.
echo Opening the results folder...
start "" "%~dp0output"
pause

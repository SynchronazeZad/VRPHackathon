@echo off
REM ============================================================
REM  Prepare the Python virtual environment (.venv) for THIS computer
REM  - Recreates .venv if it is missing or was copied from another PC
REM  - Installs libraries from requirements.txt if any are missing
REM ============================================================
cd /d "%~dp0"
set "VENV_PY=%~dp0.venv\Scripts\python.exe"

REM ---- 1) Is the existing .venv usable on this computer? ----
if not exist "%VENV_PY%" goto :make_venv
"%VENV_PY%" -c "import sys" >nul 2>&1
if not errorlevel 1 goto :check_libs
echo [!] The existing .venv was made on another computer and cannot run here.
echo [!] Removing it and creating a new one...
rmdir /s /q "%~dp0.venv"

:make_venv
REM ---- 2) Find a Python installed on this computer (prefer 3.12 / 3.11) ----
set "PY_CMD="
for %%V in (3.12 3.11 3.13 3.10) do (
    if not defined PY_CMD (
        py -%%V -c "import sys" >nul 2>&1 && set "PY_CMD=py -%%V"
    )
)
if not defined PY_CMD (
    py -3 -c "import sys" >nul 2>&1 && set "PY_CMD=py -3"
)
if not defined PY_CMD (
    python -c "import sys" >nul 2>&1 && set "PY_CMD=python"
)
if not defined PY_CMD goto :no_python

echo [*] Creating .venv with: %PY_CMD%
%PY_CMD% -m venv "%~dp0.venv"
if errorlevel 1 goto :venv_failed

:check_libs
REM ---- 3) Install libraries if missing ----
"%VENV_PY%" -c "import ortools, matplotlib, streamlit" >nul 2>&1
if not errorlevel 1 goto :done
echo [*] Installing libraries (first run takes a few minutes)...
"%VENV_PY%" -m pip install --upgrade pip
"%VENV_PY%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 goto :pip_failed

:done
echo [OK] Environment is ready.
exit /b 0

:no_python
echo [X] Python was not found on this computer.
echo     Install Python 3.11 or 3.12 from https://www.python.org/downloads/
echo     and tick "Add python.exe to PATH" during setup, then run this again.
exit /b 1

:venv_failed
echo [X] Could not create .venv
exit /b 1

:pip_failed
echo [X] Library install failed. Check the internet connection,
echo     or install Python 3.11 / 3.12 and delete the .venv folder, then retry.
exit /b 1

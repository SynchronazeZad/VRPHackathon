@echo off
REM Double-click to run the solver on every .vrp file in the data folder and print a summary
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
call "%~dp0setup_env.bat"
if errorlevel 1 goto :end
"%~dp0.venv\Scripts\python.exe" "%~dp0src\CVRP.py"
:end
echo.
pause

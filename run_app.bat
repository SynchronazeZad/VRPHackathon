@echo off
REM Double-click to open the CVRP Fleet Optimizer web app (Streamlit)
cd /d "%~dp0"
call "%~dp0setup_env.bat"
if errorlevel 1 goto :fail

echo.
echo [*] Opening http://localhost:8501  (close this window to stop the app)
start "" cmd /c "timeout /t 5 >nul & start http://localhost:8501"
"%~dp0.venv\Scripts\python.exe" -m streamlit run "%~dp0src\app.py"
pause
exit /b 0

:fail
echo.
pause
exit /b 1

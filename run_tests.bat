@echo off
echo ===================================================
echo Running RazorRevive-OS Full Test Suite
echo ===================================================
"C:\Users\HP\AppData\Local\Programs\Python\Python313\python.exe" -m pytest -v
if %ERRORLEVEL% NEQ 0 (
    py -m pytest -v
)
pause

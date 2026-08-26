@echo off
echo ===================================================
echo Starting RazorRevive-OS Server on http://localhost:8000
echo ===================================================
"C:\Users\HP\AppData\Local\Programs\Python\Python313\python.exe" -m uvicorn backend.app.main:app --port 8000 --reload
if %ERRORLEVEL% NEQ 0 (
    py -m uvicorn backend.app.main:app --port 8000 --reload
)
pause

@echo off
echo ===================================================
echo Starting RazorRevive-OS Server on http://localhost:8000
echo ===================================================
if exist "%USERPROFILE%\.local\bin\uv.exe" (
    "%USERPROFILE%\.local\bin\uv.exe" run --with-requirements requirements.txt uvicorn backend.app.main:app --port 8000 --reload
) else (
    uvicorn backend.app.main:app --port 8000 --reload || python -m uvicorn backend.app.main:app --port 8000 --reload
)
pause

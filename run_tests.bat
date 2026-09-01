@echo off
echo ===================================================
echo Running RazorRevive-OS Full Test Suite
echo ===================================================
if exist "%USERPROFILE%\.local\bin\uv.exe" (
    "%USERPROFILE%\.local\bin\uv.exe" run --with-requirements requirements.txt pytest -v
) else (
    pytest -v || python -m pytest -v
)
pause

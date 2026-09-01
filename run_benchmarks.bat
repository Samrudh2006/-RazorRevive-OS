@echo off
echo ===================================================
echo Running RazorRevive-OS 100-Batch Benchmark Suite
echo ===================================================
if exist "%USERPROFILE%\.local\bin\uv.exe" (
    "%USERPROFILE%\.local\bin\uv.exe" run --with-requirements requirements.txt python benchmarks/benchmark_runner.py
) else (
    python benchmarks\benchmark_runner.py || py benchmarks\benchmark_runner.py
)
pause

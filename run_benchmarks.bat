@echo off
echo ===================================================
echo Running RazorRevive-OS 100-Batch Benchmark Suite
echo ===================================================
"C:\Users\HP\AppData\Local\Programs\Python\Python313\python.exe" benchmarks\benchmark_runner.py
if %ERRORLEVEL% NEQ 0 (
    py benchmarks\benchmark_runner.py
)
pause

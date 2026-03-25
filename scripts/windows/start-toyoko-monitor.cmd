@echo off
setlocal

set SCRIPT_DIR=%~dp0
for %%I in ("%SCRIPT_DIR%..\..") do set REPO_DIR=%%~fI

for /f "usebackq delims=" %%I in (`wsl.exe wslpath "%REPO_DIR%"`) do set WSL_REPO_DIR=%%I

wsl.exe bash -lc "cd \"%WSL_REPO_DIR%\" && ./scripts/run_service.sh"

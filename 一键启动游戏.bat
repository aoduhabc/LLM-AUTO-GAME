@echo off
setlocal
set "PROJECT_DIR=%~dp0"

start "" cmd /k "cd /d "%PROJECT_DIR%backend" && python -m uvicorn main:app --host 127.0.0.1 --port 8001"
start "" cmd /k "cd /d "%PROJECT_DIR%frontend" && npm run dev -- --host 127.0.0.1 --port 5178 --strictPort"

timeout /t 2 >nul
start "" "http://127.0.0.1:5178/"

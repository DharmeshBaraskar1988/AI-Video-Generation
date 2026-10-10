@echo off
rem Start back end (auto-reloads on code changes) and front end in their own windows.
cd /d "%~dp0"

start "D-Storify backend" cmd /k backend\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --port 8000 --reload --reload-dir backend\app --reload-exclude "backend/app/store/*"
start "D-Storify frontend" cmd /k "cd frontend && npm run dev"

echo Backend:  http://localhost:8000
echo Frontend: http://localhost:3000

@echo off
echo Starting Production Server...

:: Check for venv in backend/venv
IF EXIST "backend\venv\Scripts\activate.bat" (
    call backend\venv\Scripts\activate
    echo Virtual Environment Activated.
) ELSE (
    echo ⚠️ No virtual environment found in backend\venv.
    echo Running with system Python (might fail if dependencies missing).
)

:: Run Uvicorn from ROOT, treating 'backend' as a package.
:: This fixes the "ImportError: attempted relative import"
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4 --reload

pause

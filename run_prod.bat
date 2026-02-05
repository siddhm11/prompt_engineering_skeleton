@echo off
echo Starting Production Server...
cd backend
IF EXIST "venv\Scripts\activate.bat" (
    call venv\Scripts\activate
    echo Virtual Environment Activated.
) ELSE (
    echo No virtual environment found, using system python.
)

:: Run Uvicorn in production mode
:: --workers 4: Use 4 worker processes (adjust based on CPU)
:: --host 0.0.0.0: Expose to network
:: --no-reload: Disable auto-reload for stability/performance
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4 --no-reload

pause

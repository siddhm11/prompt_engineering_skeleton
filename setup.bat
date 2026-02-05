@echo off
echo ==========================================
echo      Prompt Memory - One-Time Setup
echo ==========================================

cd backend

echo 1. Creating Virtual Environment (venv)...
python -m venv venv

echo 2. Activating venv...
call venv\Scripts\activate

echo 3. Installing Dependencies...
pip install -r requirements.txt

echo.
echo ==========================================
echo      Setup Complete! 
echo ==========================================
echo You can now run 'run_prod.bat' in the main folder.
pause

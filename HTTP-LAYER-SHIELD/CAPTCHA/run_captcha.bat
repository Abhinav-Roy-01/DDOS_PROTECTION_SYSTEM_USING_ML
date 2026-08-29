@echo off
REM ============================================================================
REM Game CAPTCHA Module - Startup Script
REM ============================================================================
REM Prerequisites: Redis must be running on localhost:6379
REM ============================================================================

echo.
echo ============================================================
echo   GAME CAPTCHA MODULE - DDoS Protection System
echo ============================================================
echo.

cd /d "%~dp0"

REM Step 1: Check Python
echo [Step 1/4] Checking Python...
python --version 2>nul
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    exit /b 1
)
echo.

REM Step 2: Install dependencies
echo [Step 2/4] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    exit /b 1
)
echo.

REM Step 3: Check Redis
echo [Step 3/4] Checking Redis connection...
python -c "import redis; r = redis.StrictRedis(); r.ping(); print('Redis: OK')" 2>nul
if errorlevel 1 (
    echo WARNING: Redis is not running on localhost:6379
    echo Please start Redis before continuing.
    echo.
    echo If using Docker:  docker run -d -p 6379:6379 redis:latest
    echo If using WSL:     wsl sudo service redis-server start
    echo.
    pause
)
echo.

REM Step 4: Start Flask app
echo [Step 4/4] Starting Game CAPTCHA server...
echo.
echo ============================================================
echo   Server: http://127.0.0.1:5000
echo   New Game: http://127.0.0.1:5000/captcha/new_game
echo   Challenge: http://127.0.0.1:5000/captcha/challenge?game_id=...
echo ============================================================
echo.
python captcha_routes.py

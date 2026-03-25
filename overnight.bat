@echo off
title LeadGen EU - Overnight Mode
color 0B
chcp 65001 >nul

echo.
echo  ========================================
echo    LeadGen EU - OVERNIGHT MODE
echo  ========================================
echo.
echo  Nacrt:
echo    22:00 → Zacne scraping vseh leadov
echo    08:00 → Zacne posiljanje emailov
echo.
echo  Pusti ta PC prizen cez noc.
echo  Zjutraj so vsi emaili poslani.
echo.

REM --- Preveri Python ---
python --version >nul 2>&1
if errorlevel 1 (
    echo  NAPAKA: Python ni namescan!
    echo  Zaženi najprej start.bat
    pause
    exit
)

REM --- Namesti odvisnosti če je treba ---
pip install -r requirements.txt -q --disable-pip-version-check

REM --- Ustvari .env če ne obstaja ---
if not exist .env (
    copy .env.example .env >nul
    echo  OPOZORILO: .env ustvarjen iz primera.
    echo  Nastavi SMTP podatke v .env datoteki!
    echo.
    pause
)

REM --- Ustvari mape ---
if not exist data mkdir data
if not exist logs mkdir logs
if not exist exports mkdir exports
if not exist previews mkdir previews

REM --- Poišči lokalni IP ---
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do (
    set LOCAL_IP=%%a
    goto :found
)
:found
set LOCAL_IP=%LOCAL_IP: =%

echo  App dostopen na:
echo    Racunalnik: http://localhost:8000
echo    iPhone:     http://%LOCAL_IP%:8000
echo.
echo  NE ZAPRI tega okna!
echo  ========================================
echo.

python -c "
import sys, os
sys.path.insert(0, '.')
from src.database import init_db
from src.scheduler import start_overnight_scheduler
from api import app
import uvicorn, threading, time

init_db()
start_overnight_scheduler()

print('Overnight scheduler zagnan.')
print('Scraping zacne ob 22:00, posiljanje ob 08:00.')
print()

uvicorn.run(app, host='0.0.0.0', port=8000, log_level='warning')
"

pause

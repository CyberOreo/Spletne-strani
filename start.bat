@echo off
title LeadGen EU
color 0A
chcp 65001 >nul

echo.
echo  ========================================
echo    LeadGen EU - Web App
echo  ========================================
echo.

REM --- Preveri Python ---
python --version >nul 2>&1
if errorlevel 1 (
    echo  NAPAKA: Python ni namescan!
    echo.
    echo  1. Pojdi na: python.org/downloads
    echo  2. Prenesi in zazeni installer
    echo  3. OBVEZNO obkljukaj "Add Python to PATH"
    echo  4. Potem znova zazeni ta fajl
    echo.
    pause
    exit
)

REM --- Namesti odvisnosti (samo prvic) ---
echo  Preverjam odvisnosti...
pip install -r requirements.txt -q --disable-pip-version-check
echo  Odvisnosti OK

REM --- Ustvari .env ce ne obstaja ---
if not exist .env (
    echo  Ustvarjam konfiguracijo...
    copy .env.example .env >nul
    echo.
    echo  POMEMBNO: Odpri .env in nastavi SMTP podatke!
    echo  Brez tega emaili ne bodo poslani.
    echo.
    pause
)

REM --- Ustvari mape ---
if not exist data mkdir data
if not exist logs mkdir logs
if not exist exports mkdir exports
if not exist previews mkdir previews

REM --- Poišci lokalni IP ---
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do (
    set LOCAL_IP=%%a
    goto :found
)
:found
set LOCAL_IP=%LOCAL_IP: =%

echo.
echo  ========================================
echo.
echo   App tece!
echo.
echo   Racunalnik:  http://localhost:8000
echo   iPhone/tel:  http://%LOCAL_IP%:8000
echo.
echo   Overnight nacin VKLOPLJEN:
echo     Scraping zacne ob: 22:00
echo     Posiljanje zacne ob: 08:00 (pon-pet)
echo.
echo   Pusti ta okno odprto cez noc.
echo   Ce se sistem ustavi, se sam ZNOVA zazene.
echo.
echo   Za javni link: zazeni public_link.bat
echo  ========================================
echo.

REM --- Watchdog zanka: ce Python crashne, se sam znova zazene ---
:watchdog
echo  [%date% %time%] Zaganjam sistem...
python -c "
import sys, os, logging
sys.path.insert(0, '.')

# Logging v datoteko in konzolo
from pathlib import Path
Path('logs').mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%%(asctime)s %%(levelname)s %%(message)s',
    handlers=[
        logging.FileHandler('logs/app.log', encoding='utf-8'),
        logging.StreamHandler(),
    ]
)

from src.database import init_db
from src.scheduler import start_overnight_scheduler
import api as api_module
import uvicorn

init_db()
start_overnight_scheduler()

logging.getLogger('main').info('Sistem zagnan. Scraping ob 22:00, posiljanje ob 08:00.')

uvicorn.run(api_module.app, host='0.0.0.0', port=8000, log_level='warning')
"

REM --- Ce pride sem, je Python crashnil ---
echo.
echo  [%date% %time%] Sistem se je nepricakovano ustavil!
echo  Ponovni zagon v 30 sekundah...
echo  (pritisni Ctrl+C ce hces ustaviti)
echo.
timeout /t 30 /nobreak
goto watchdog

@echo off
title LeadGen EU
color 0A

echo.
echo  ========================================
echo    LeadGen EU - Web App
echo  ========================================
echo.

REM --- Preveri Python ---
python --version >/dev/null 2>&1
if %errorlevel% neq 0 (
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

echo  Python OK
echo.

REM --- Namesti odvisnosti ---
echo  Nameščam odvisnosti (prvič traja ~2 min)...
pip install -r requirements.txt -q --disable-pip-version-check
if %errorlevel% neq 0 (
    echo  Poskušam z: py -m pip install...
    py -m pip install -r requirements.txt -q
)
echo  Odvisnosti OK

REM --- Ustvari .env ce ne obstaja ---
if not exist .env (
    copy .env.example .env >/dev/null
    echo.
    echo  Nastavitve so pripravljene.
    echo  V aplikaciji pojdi na Nastavitve in nastavi email.
    echo.
)

REM --- Ustvari mape ---
if not exist data mkdir data
if not exist logs mkdir logs
if not exist exports mkdir exports
if not exist previews mkdir previews

REM --- Pokazi IP ---
echo.
echo  ========================================
echo.
echo   App tece!
echo.
echo   Odpri v brskalniku: http://localhost:8000
echo.
echo   Overnight nacin VKLOPLJEN:
echo     Scraping ob: 22:00
echo     Posiljanje ob: 08:00
echo.
echo   Pusti okno odprto cez noc!
echo  ========================================
echo.

REM --- Watchdog: avtomatski ponovni zagon ---
:watchdog
echo  [%date% %time%] Zaganjam...
python -c "import sys,os,logging; sys.path.insert(0,'.'); from pathlib import Path; Path('logs').mkdir(exist_ok=True); logging.basicConfig(level=logging.INFO,format='%%(asctime)s %%(levelname)s %%(message)s',handlers=[logging.FileHandler('logs/app.log',encoding='utf-8'),logging.StreamHandler()]); from src.database import init_db; from src.scheduler import start_overnight_scheduler; import api as api_module; import uvicorn; init_db(); start_overnight_scheduler(); uvicorn.run(api_module.app,host='0.0.0.0',port=8000,log_level='warning')"

echo.
echo  Sistem se je ustavil. Ponovni zagon v 30 sekundah...
echo  (pritisni Ctrl+C za izhod)
echo.
timeout /t 30 /nobreak >/dev/null
goto watchdog

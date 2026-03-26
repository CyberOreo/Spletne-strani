@echo off
title LeadGen EU
color 0A

echo.
echo  ========================================
echo    LeadGen EU - Web App
echo  ========================================
echo.

REM --- Preveri Python ---
python --version >nul 2>&1
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
echo  Odvisnosti OK
echo.

REM --- Ustvari .env ce ne obstaja ---
if not exist .env (
    copy .env.example .env >nul
    echo  Konfiguracija ustvarjena.
    echo  V aplikaciji pojdi na Nastavitve in nastavi email.
    echo.
)

REM --- Ustvari mape ---
if not exist data mkdir data
if not exist logs mkdir logs
if not exist exports mkdir exports
if not exist previews mkdir previews

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
python startup.py

echo.
echo  Sistem se je ustavil. Ponovni zagon v 30 sekundah...
echo  (pritisni Ctrl+C za izhod)
echo.
timeout /t 30 /nobreak >nul
goto watchdog

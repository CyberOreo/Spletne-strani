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
    echo  2. Prenesi in zaženi installer
    echo  3. OBVEZNO obkljukaj "Add Python to PATH"
    echo  4. Potem znova zaženi ta fajl
    echo.
    pause
    exit
)

REM --- Namesti odvisnosti (samo prvič) ---
echo  Preverjam odvisnosti...
pip install -r requirements.txt -q --disable-pip-version-check
echo  Odvisnosti OK

REM --- Ustvari .env ce ne obstaja ---
if not exist .env (
    echo  Ustvarjam konfiguracijo...
    copy .env.example .env >nul
)

REM --- Ustvari mape ---
if not exist data mkdir data
if not exist logs mkdir logs
if not exist exports mkdir exports
if not exist previews mkdir previews

REM --- Poišči lokalni IP ---
echo.
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do (
    set LOCAL_IP=%%a
    goto :found
)
:found
set LOCAL_IP=%LOCAL_IP: =%

echo  ========================================
echo.
echo   App tece!
echo.
echo   Racunalnik:  http://localhost:8000
echo   iPhone/tel:  http://%LOCAL_IP%:8000
echo.
echo   Za javni link (kjerkoli):
echo   Zaženi public_link.bat v DRUGI CMD
echo.
echo   NE ZAPRI tega okna!
echo  ========================================
echo.

python api.py
pause

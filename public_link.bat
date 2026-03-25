@echo off
title LeadGen EU - Javni link
color 0B
chcp 65001 >nul

echo.
echo  ========================================
echo    LeadGen EU - Javni link
echo  ========================================
echo.

REM --- Prenesi cloudflared ce ga ni ---
if not exist cloudflared.exe (
    echo  Prenasam cloudflared ^(samo prvic^)...
    curl -L -o cloudflared.exe "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    if errorlevel 1 (
        echo.
        echo  NAPAKA: Prenos ni uspel.
        echo  Prenesi rocno: github.com/cloudflare/cloudflared/releases
        echo  Datoteko cloudflared-windows-amd64.exe
        echo  Preimenuj v cloudflared.exe in jo daj v isti map kot start.bat
        pause
        exit
    )
    echo  cloudflared OK
)

echo.
echo  Generiram javni link...
echo  ^(Počakaj 5-10 sekund^)
echo.
echo  TVOJ JAVNI LINK bo prikazan spodaj:
echo  ----------------------------------------
echo.

cloudflared tunnel --url http://localhost:8000

pause

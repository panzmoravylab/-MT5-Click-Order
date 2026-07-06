@echo off
REM ============================================================
REM  Trading Panel pro MetaTrader 5 — spousteci davka
REM  Spusti celou aplikaci dvojklikem na tento soubor.
REM ============================================================

title Trading Panel MT5

REM Prechod do slozky, kde lezi tento .bat (funguje odkudkoliv).
cd /d "%~dp0"

REM Kontrola, ze existuje virtualni prostredi.
if not exist ".venv\Scripts\activate.bat" (
    echo.
    echo [CHYBA] chybi virtualni prostredi .venv
    echo Spustte jednorazove v Git Bash:
    echo     python -m venv .venv ^&^& source .venv/Scripts/activate ^&^& pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

REM Aktivace prostredi a spusteni aplikace.
call .venv\Scripts\activate.bat

echo Spoustim Trading Panel...
python main.py

REM Pokud aplikace spadla (nenulovy navratovy kod), nechame okno otevrene.
if errorlevel 1 (
    echo.
    echo [CHYBA] Aplikace skoncila s chybou (kod %errorlevel%).
    echo Podrobnosti vyse ^. Zavri toto okno az po procteni.
    echo.
    pause
)

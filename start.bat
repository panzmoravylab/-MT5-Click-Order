@echo off
REM ============================================================
REM  Trading Panel pro MetaTrader 5 — spousteci davka
REM  Staci dvojklik a funguje (i na cistem PC po clone).
REM ============================================================

title Trading Panel MT5
cd /d "%~dp0"

echo ============================================================
echo  Trading Panel MT5 — spousteni
echo ============================================================
echo.

REM --- 1) Kontrola Pythonu (potrebujeme 64-bit) ---------------
python --version >nul 2>&1
if errorlevel 1 (
    echo [CHYBA] Python neni v PATH nebo neni nainstalovan.
    echo Nainstaluj Python 3.10-3.13 ^(-bit^) z https://www.python.org/downloads/
    echo Pri instalaci ZASKRTNI "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

echo [OK] Python:
python --version
echo.

REM --- 2) Vytvoreni .venv, pokud jeste neexistuje -------------
if not exist ".venv\Scripts\activate.bat" (
    echo [INFO] Virtualni prostredi .venv neexistuje — vytvarim...
    python -m venv .venv
    if errorlevel 1 (
        echo [CHYBA] Nepodarilo se vytvorit .venv.
        pause
        exit /b 1
    )
    echo [OK] .venv vytvoreno.
    echo.
) else (
    echo [OK] .venv jiz existuje.
)

REM --- 3) Aktivace prostredi ----------------------------------
call .venv\Scripts\activate.bat

REM --- 4) Instalace zavislosti, pokud PyQt6/MT5 chybi --------
python -c "import PyQt6, MetaTrader5" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Instaluji zavislosti ^(PyQt6, MetaTrader5^)...
    echo         Bude to trvat ~30-60 s, vydrz...
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [CHYBA] Instalace zavislosti selhala.
        echo Zkontroluj pripojeni k internetu a ze mas 64-bit Python.
        pause
        exit /b 1
    )
    echo [OK] Zavislosti nainstalovany.
    echo.
) else (
    echo [OK] Zavislosti jiz nainstalovany.
)

REM --- 5) Kontrola MT5 terminálu ------------------------------
if not exist "C:\Program Files\MetaTrader 5\terminal64.exe" (
    echo [VAROVANI] Nevidim MT5 v C:\Program Files\MetaTrader 5
    echo             Nainstaluj MetaTrader 5 z https://www.metatrader5.com/cs/download
    echo             Pokud mas jinde, nastav cestu v Settings.
    echo.
)

echo ============================================================
echo  Spoustim aplikaci...
echo ============================================================
python main.py

REM --- 6) Pri chybe nechame okno otevrene ---------------------
if errorlevel 1 (
    echo.
    echo ============================================================
    echo  [CHYBA] Aplikace skoncila s kodem %errorlevel%.
    echo  Podrobnosti viz vyse nebo soubor trading.log
    echo ============================================================
    pause
)

REM Uspesny beh = okno se samo zavre.

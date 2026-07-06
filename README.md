# Trading Panel pro MetaTrader 5

Kompaktní desktopová aplikace (Windows, PyQt6), která se připojuje k terminálu
MetaTrader 5 a umožňuje rychlé jedním-kliknutím otevírání a zavírání pozic s
přednastavenými parametry pro každý pár zvlášť.

> ⚠️ **Reálné obchody.** Příkazy z aplikace odesíláme na tvůj MT5 účet — kupují/
> prodávají reálné pozice. Doporučuji nejprve vyzkoušet na **demo účtu**.

## Funkce

- Rychlé přepínání mezi páry a metaly (taby): XAUUSD, EURUSD, USDJPY, AUDUSD, USDCAD (+ další přidatelné).
- Pro každý pár vlastní uložené parametry: počet pozic, lot size, **SL a TP jako absolutní cenové hladiny**, deviace.
- Tlačítka **BUY / SELL / CLOSE / CLOSE ALL** odesílající tržní příkazy do MT5.
- Live ceny (bid/ask) a tabulka otevřených pozic s P/L.
- **Settings dialog**: login, heslo, server, cesta k terminálu + „Test připojení“.
- Automatická detekce *filling mode* (FOK/IOC/RETURN) — řeší nejčastější chybu `10030 Unsupported filling mode`.
- Automatické ukládání parametrů do `config.json`.

## Požadavky

- Windows 10/11 (64-bit).
- Nainstalovaný MetaTrader 5 terminál (`C:\Program Files\MetaTrader 5\terminal64.exe`).
- Python 3.10–3.13, **64-bit** (MT5 neumí 32-bit Python).

## Instalace

```bash
cd C:\Users\tausr\ZCodeProject

# 1) Virtuální prostředí (již vytvořeno v .venv)
python -m venv .venv

# 2) Aktivace (Git Bash)
source .venv/Scripts/activate

# 3) Instalace závislostí
python -m pip install -r requirements.txt
```

## Spuštění

```bash
source .venv/Scripts/activate
python main.py
```

## První použití

1. Po startu klikni na **⚙ Nastavení** (vpravo nahoře).
2. Vyplň:
   - **Login** — číslo tvého MT5 účtu (najdeš v terminálu: *Soubor → Přihlásit se k obchodnímu účtu*).
   - **Heslo** — **obchodní heslo** (trader password), nikoli investorské.
   - **Server** — např. `ICMarketsSC-Demo`, `Exness-Real` (zejména u demo účtů přípona `-Demo`).
   - **Cesta k terminálu** — obvykle `C:\Program Files\MetaTrader 5\terminal64.exe`.
3. Klikni **Test připojení** → potvrdit, že vše funguje.
4. **Uložit** → aplikace se připojí automaticky (příště už se připojí sama).

Po připojení:
- Klikni na tab **XAUUSD** → vidíš své hodnoty (lot, SL, TP…).
- **BUY** / **SELL** otevře N pozic dle parametrů (počet = „Počet pozic“).
- **CLOSE pár** zavře všechny pozice daného symbolu.
- **CLOSE ALL** zavře všechny pozice na účtu (vyžaduje potvrzení).

## Přidání / odebrání symbolu

- **+ Symbol** → dialog pro název (např. `GBPUSD`), výchozí počet pozic a lot. Pokud jsi připojen, aplikace ověří, že symbol v MT5 existuje.
- **− Symbol** → odebere aktuální tab (pozice v MT5 zůstávají nedotčeny).

## Konfigurace (`config.json`)

Generuje se automaticky při prvním startu. Ukázka:

```json
{
  "mt5": {
    "login": 12345678,
    "password": "...",
    "server": "Broker-Server",
    "terminal_path": "C:\\Program Files\\MetaTrader 5\\terminal64.exe"
  },
  "symbols": {
    "XAUUSD": {"position_count": 1, "lot_size": 0.01, "sl": 2000.0, "tp": 2050.0, "deviation": 20}
  }
}
```

> 🔐 **Bezpečnost:** heslo je v `config.json` uloženo v plain-textu. Neukládej
> tento soubor do veřejných repozitářů. Šifrování hesla lze doplnit později.

## Struktura projektu

```
main.py                 # spuštění aplikace
config_manager.py       # načítání/ukládání config.json
mt5_service.py          # obal nad MetaTrader5 API (obchody, pozice, ceny)
config.json             # konfigurace (generováno)
requirements.txt        # závislosti (PyQt6, MetaTrader5)
trading.log             # logy (generováno za běhu)
ui/
    __init__.py
    main_window.py      # hlavní okno, taby, workery
    symbol_panel.py     # UI jednoho páru (vstupy + tlačítka + tabulka pozic)
    settings_dialog.py  # dialog pro přihlášení k MT5
    workers.py          # QThread workery (connect, action, poll)
```

## Technické poznámky

- **Threading:** veškerá volání do MT5 běží v `QThread` workerech (`ui/workers.py`), aby GUI nikdy nezamrzlo. Live data se stahují každých ~500 ms.
- **Filling mode:** detekuje se z `symbol_info().filling_mode` (IOC > FOK > RETURN).
- **Magic number:** `234000` — všechny pozice otevřené tímto panelem mají tento identifikátor (zobrazuje se v tabulce). CLOSE/CLOSE ALL ale uzavírají všechny pozice na účtu pro daný symbol.
- **Logování:** `trading.log` v kořenovém adresáři.

## Řešení problémů

| Problém | Řešení |
|---|---|
| `Inicializace selhala` | Ověř login/heslo/server. Pro demo účty musí být přípona `-Demo`. |
| `retcode 10030 Unsupported filling mode` | Mělo by být vyřešeno automatickou detekcí; případně broker symbol nemá povolené tržní příkazy. |
| `symbol_select selhal` | Symbol v MT5 neexistuje pro tento účet — ověř v Market Watch terminálu. |
| Aplikace se neotevře | Aktivuj `.venv` (`source .venv/Scripts/activate`) a spusť znovu `python main.py`. |
| Ceny se neaktualizují | Trh může být zavřený (víkend/svátky), nebo účet je odpojený v terminálu. |

## Budoucí rozšíření (mimo rozsah)

- Úprava SL/TP u již otevřených pozic přímo z tabulky.
- Trailing stop, částečné zavírání.
- Šifrování hesla (Windows DPAPI / `cryptography`).
- Sestavení do `.exe` přes PyInstaller.

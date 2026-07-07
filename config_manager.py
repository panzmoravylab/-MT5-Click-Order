"""Načítání a ukládání konfigurace (config.json).

Struktura:
{
  "mt5": {
    "login": int,
    "password": str,        # plain-text (lokální soubor)
    "server": str,
    "terminal_path": str
  },
  "symbols": {
    "XAUUSD": {"position_count": int, "lot_size": float,
               "sl": float, "tp": float, "deviation": int},
    ...
  }
}
"""

from __future__ import annotations

import json
import os
from typing import Any

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# Cesta k terminálu MT5 — detekce typické instalace, s fallbackem.
_DEFAULT_TERMINAL = r"C:\Program Files\MetaTrader 5\terminal64.exe"

# Výchozí symboly s rozumnými hodnotami (SL/TP jsou v bodech/offsets).
_DEFAULT_SYMBOLS: dict[str, dict[str, Any]] = {
    "XAUUSD": {"position_count": 1, "lot_size": 0.01, "sl": 200.0, "tp": 400.0, "deviation": 20},
    "EURUSD": {"position_count": 1, "lot_size": 0.10, "sl": 150.0, "tp": 300.0, "deviation": 20},
    "USDJPY": {"position_count": 1, "lot_size": 0.10, "sl": 150.0, "tp": 300.0, "deviation": 20},
    "AUDUSD": {"position_count": 1, "lot_size": 0.10, "sl": 150.0, "tp": 300.0, "deviation": 20},
    "USDCAD": {"position_count": 1, "lot_size": 0.10, "sl": 150.0, "tp": 300.0, "deviation": 20},
}


def _default_config() -> dict[str, Any]:
    return {
        "mt5": {
            "login": 0,
            "password": "",
            "server": "",
            "terminal_path": _DEFAULT_TERMINAL,
        },
        "symbols": _DEFAULT_SYMBOLS,
    }


def _detect_terminal_path() -> str:
    """Vrátí cestu k terminal64.exe, pokud existuje; jinak výchozí."""
    candidates = [
        _DEFAULT_TERMINAL,
        r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return _DEFAULT_TERMINAL


def load_config() -> dict[str, Any]:
    """Načte konfiguraci. Pokud soubor neexistuje, vytvoří výchozí."""
    if not os.path.exists(CONFIG_PATH):
        config = _default_config()
        config["mt5"]["terminal_path"] = _detect_terminal_path()
        save_config(config)
        return config

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError):
        # Poškozený soubor → záloha a nový výchozí.
        backup = CONFIG_PATH + ".bak"
        try:
            os.replace(CONFIG_PATH, backup)
        except OSError:
            pass
        config = _default_config()
        save_config(config)
        return config

    # Doplnění chybějících klíčů (zpětná kompatibilita).
    defaults = _default_config()
    if "mt5" not in config:
        config["mt5"] = defaults["mt5"]
    else:
        for key, val in defaults["mt5"].items():
            config["mt5"].setdefault(key, val)
    if "symbols" not in config or not isinstance(config["symbols"], dict):
        config["symbols"] = defaults["symbols"]
    else:
        for sym, params in config["symbols"].items():
            if not isinstance(params, dict):
                continue
            for key, val in defaults["symbols"]["XAUUSD"].items():
                params.setdefault(key, val)
    return config


def save_config(config: dict[str, Any]) -> None:
    """Uloží konfiguraci na disk."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_mt5_credentials(config: dict[str, Any]) -> dict[str, Any]:
    """Vrátí přihlašovací údaje jako dict s login jako int."""
    mt5 = config.get("mt5", {})
    try:
        login = int(mt5.get("login", 0))
    except (TypeError, ValueError):
        login = 0
    return {
        "login": login,
        "password": mt5.get("password", ""),
        "server": mt5.get("server", ""),
        "terminal_path": mt5.get("terminal_path", _DEFAULT_TERMINAL),
    }


def get_symbol_params(config: dict[str, Any], symbol: str) -> dict[str, Any]:
    """Vrátí parametry pro daný symbol s výchozími hodnotami."""
    defaults = _DEFAULT_SYMBOLS["XAUUSD"]
    params = config.get("symbols", {}).get(symbol, {})
    return {
        "position_count": int(params.get("position_count", defaults["position_count"])),
        "lot_size": float(params.get("lot_size", defaults["lot_size"])),
        "sl": float(params.get("sl", defaults["sl"])),
        "tp": float(params.get("tp", defaults["tp"])),
        "deviation": int(params.get("deviation", defaults["deviation"])),
    }


def set_symbol_params(config: dict[str, Any], symbol: str, params: dict[str, Any]) -> None:
    """Aktualizuje parametry symbolu v config struktuře (je třeba následně uložit)."""
    if "symbols" not in config:
        config["symbols"] = {}
    config["symbols"][symbol] = {
        "position_count": int(params.get("position_count", 1)),
        "lot_size": float(params.get("lot_size", 0.01)),
        "sl": float(params.get("sl", 0.0)),
        "tp": float(params.get("tp", 0.0)),
        "deviation": int(params.get("deviation", 20)),
    }


def add_symbol(config: dict[str, Any], symbol: str, params: dict[str, Any] | None = None) -> bool:
    """Přidá nový symbol. Vrací True, pokud byl přidán; False, pokud už existuje."""
    symbol = symbol.strip().upper()
    if not symbol:
        return False
    if "symbols" not in config:
        config["symbols"] = {}
    if symbol in config["symbols"]:
        return False
    defaults = _DEFAULT_SYMBOLS["XAUUSD"].copy()
    if params:
        defaults.update(params)
    config["symbols"][symbol] = defaults
    return True


def remove_symbol(config: dict[str, Any], symbol: str) -> bool:
    """Smaže symbol. Vrací True, pokud byl smazán."""
    if "symbols" in config and symbol in config["symbols"]:
        del config["symbols"][symbol]
        return True
    return False

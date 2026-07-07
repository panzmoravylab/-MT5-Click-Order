"""Obal nad MetaTrader5 Python API.

Veškerá komunikace s MT5 terminálem prochází tímto modulem.
Každá obchodní operace vrací (success: bool, message: str).

Důležité detaily:
- ``_filling_mode`` automaticky volí FOK/IOC/RETURN podle nastavení symbolu,
  jinak order_send často vrací retcode 10030 (Unsupported filling mode).
- ``symbol_select`` musí být volán před každým obchodem, jinak order selže.
- Operace NENÍ thread-safe pro paralelní volání z více vláken — worker
  používá frontu a volá operace sekvenčně.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import MetaTrader5 as mt5

logger = logging.getLogger("mt5_service")

# Magic number pro všechny příkazy z tohoto panelu (identifikace pozic).
MAGIC_NUMBER = 234000

# Mapování konstant MT5 (pro přehlednost v logách).
_TRADE_REQUEST_ACTIONS = {
    mt5.TRADE_ACTION_DEAL: "DEAL",
    mt5.TRADE_ACTION_PENDING: "PENDING",
    mt5.TRADE_ACTION_SLTP: "SLTP",
}


@dataclass
class TickInfo:
    symbol: str
    bid: float
    ask: float
    last: float


@dataclass
class PositionInfo:
    ticket: int
    symbol: str
    type: int          # 0 = BUY, 1 = SELL
    type_str: str
    volume: float
    price_open: float
    sl: float
    tp: float
    profit: float
    magic: int


def _is_initialized() -> bool:
    """Ověří, že MT5 je inicializované (terminal běží a komunikuje)."""
    try:
        info = mt5.account_info()
        return info is not None
    except Exception:
        return False


def connect(login: int, password: str, server: str, terminal_path: str = "") -> tuple[bool, str]:
    """Inicializuje spojení s MT5 terminálem.

    ``terminal_path`` může být prázdný — pak MT5 použije výchozí terminál.
    """
    if login == 0 or not password or not server:
        return False, "Vyplň login, heslo i server."

    # Nejprve případně ukonči předchozí session.
    try:
        mt5.shutdown()
    except Exception:
        pass

    kwargs: dict[str, Any] = {
        "login": int(login),
        "password": password,
        "server": server,
    }
    if terminal_path and os.path.exists(terminal_path):
        kwargs["path"] = terminal_path

    try:
        if not mt5.initialize(**kwargs):
            err = mt5.last_error()
            return False, f"Inicializace selhala: {err}"
    except Exception as exc:
        return False, f"Chyba inicializace: {exc}"

    info = mt5.account_info()
    if info is None:
        err = mt5.last_error()
        return False, f"Připojení selhalo (account_info None): {err}"

    logger.info("Připojeno k účtu %s, server %s", info.login, info.server)
    return True, f"Připojeno: účet {info.login} ({info.server})"


def disconnect() -> None:
    """Ukončí spojení s MT5."""
    try:
        mt5.shutdown()
    except Exception as exc:
        logger.warning("Chyba při shutdown: %s", exc)


def is_connected() -> bool:
    """Rychlá kontrola, zda je spojení aktivní."""
    return _is_initialized()


def get_account_info() -> dict[str, Any] | None:
    """Vrátí základní info o účtu pro status bar (None pokud nejste připojen)."""
    info = mt5.account_info()
    if info is None:
        return None
    return {
        "login": info.login,
        "server": info.server,
        "balance": info.balance,
        "equity": info.equity,
        "currency": info.currency,
        "name": info.name,
    }


def _ensure_symbol(symbol: str) -> bool:
    """Označí symbol v Market Watch (nutné před obchodem)."""
    try:
        if not mt5.symbol_select(symbol, True):
            logger.error("symbol_select selhal pro %s", symbol)
            return False
        return True
    except Exception as exc:
        logger.error("symbol_select výjimka pro %s: %s", symbol, exc)
        return False


def _resolve_filling(symbol: str) -> int:
    """Zjistí podporovaný filling mode symbolu a vrátí odpovídající konstantu.

    ``symbol_info().filling_mode`` je bitmaska:
      bit 0 (1) → FOK podporováno
      bit 1 (2) → IOC podporováno
    Preferujeme IOC (běžnější pro retail brokery), pak FOK, nakonec RETURN.
    """
    info = mt5.symbol_info(symbol)
    if info is None:
        # Fallback na IOC (většina brokerů).
        return mt5.ORDER_FILLING_IOC

    mode = info.filling_mode
    if mode & 2:          # IOC
        return mt5.ORDER_FILLING_IOC
    if mode & 1:          # FOK
        return mt5.ORDER_FILLING_FOK
    return mt5.ORDER_FILLING_RETURN


def _send_market_order(
    symbol: str,
    order_type: int,
    volume: float,
    sl: float,
    tp: float,
    deviation: int,
    comment: str = "trading_panel",
) -> tuple[bool, str]:
    """Odešle jeden market deal. order_type = ORDER_TYPE_BUY/SELL."""
    if not _ensure_symbol(symbol):
        return False, f"Nelze vybrat symbol {symbol} v Market Watch."

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return False, f"Nelze získat cenu pro {symbol}."

    if order_type == mt5.ORDER_TYPE_BUY:
        price = tick.ask
    else:
        price = tick.bid

    filling = _resolve_filling(symbol)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(volume),
        "type": order_type,
        "price": price,
        "sl": float(sl) if sl else 0.0,
        "tp": float(tp) if tp else 0.0,
        "deviation": int(deviation),
        "magic": MAGIC_NUMBER,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }

    result = mt5.order_send(request)
    if result is None:
        err = mt5.last_error()
        return False, f"order_send vrátil None: {err}"

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return False, (
            f"Příkaz zamítnut (retcode {result.retcode}): {result.comment}"
        )

    return True, (
        f"{symbol} {'BUY' if order_type == mt5.ORDER_TYPE_BUY else 'SELL'} "
        f"{volume} lot @ {price:.5f} (ticket na dealu: {result.order})"
    )


def open_positions(
    symbol: str,
    side: str,                # "BUY" nebo "SELL"
    position_count: int,
    lot_size: float,
    sl: float,
    tp: float,
    deviation: int,
    comment: str = "trading_panel",
) -> tuple[bool, str]:
    """Otevře N pozic (stejných parametrů) pro daný symbol.

    Vrací agregovaný výsledek. Pokud některý příkaz selže, vrátí False,
    ale zpráva obsahuje kolik uspělo / selhalo.
    """
    side = side.upper()
    if side not in ("BUY", "SELL"):
        return False, "Neznámý typ příkazu (očekáváno BUY/SELL)."
    if position_count < 1:
        return False, "Počet pozic musí být alespoň 1."
    if lot_size <= 0:
        return False, "Velikost pozice (lot) musí být kladná."

    order_type = mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL

    ok = 0
    fail = 0
    last_msg = ""
    for i in range(int(position_count)):
        success, msg = _send_market_order(
            symbol, order_type, lot_size, sl, tp, deviation, comment
        )
        if success:
            ok += 1
        else:
            fail += 1
            last_msg = msg
            logger.warning("Příkaz %d/%d selhal: %s", i + 1, position_count, msg)

    if fail == 0:
        return True, f"Otevřeno {ok}× {side} {symbol} (lot {lot_size})."
    if ok == 0:
        return False, f"Žádný příkaz neprošel ({fail} selhalo). Poslední: {last_msg}"
    return False, (
        f"Částečný úspěch: {ok} otevřeno, {fail} selhalo. Poslední chyba: {last_msg}"
    )


def _close_one_position(pos: Any) -> tuple[bool, str]:
    """Zavře jednu pozici protisměrným market dealem."""
    tick = mt5.symbol_info_tick(pos.symbol)
    if tick is None:
        return False, f"Nelze získat cenu pro {pos.symbol} (ticket {pos.ticket})."

    if pos.type == mt5.POSITION_TYPE_BUY:
        close_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
    else:
        close_type = mt5.ORDER_TYPE_BUY
        price = tick.ask

    filling = _resolve_filling(pos.symbol)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": float(pos.volume),
        "type": close_type,
        "position": int(pos.ticket),
        "price": price,
        "deviation": 50,
        "magic": pos.magic,
        "comment": "panel_close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }

    result = mt5.order_send(request)
    if result is None:
        err = mt5.last_error()
        return False, f"Zavření ticket {pos.ticket} selhalo: {err}"
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return False, (
            f"Zavření ticket {pos.ticket} zamítnuto (retcode {result.retcode}): "
            f"{result.comment}"
        )
    return True, f"Uzavřen ticket {pos.ticket} ({pos.symbol})."


def close_symbol(symbol: str) -> tuple[bool, str]:
    """Zavře všechny pozice pro daný symbol."""
    positions = mt5.positions_get(symbol=symbol)
    if positions is None or len(positions) == 0:
        return True, f"Žádné otevřené pozice pro {symbol}."

    ok = 0
    fail = 0
    last_msg = ""
    for pos in positions:
        success, msg = _close_one_position(pos)
        if success:
            ok += 1
        else:
            fail += 1
            last_msg = msg

    if fail == 0:
        return True, f"Zavřeno {ok} pozic {symbol}."
    if ok == 0:
        return False, f"Nepodařilo se zavřít žádnou pozici {symbol}. {last_msg}"
    return False, f"Částečný úspěch: {ok} zavřeno, {fail} selhalo. {last_msg}"


def close_all() -> tuple[bool, str]:
    """Zavře VŠECHNY otevřené pozice na účtu (všechny symboly)."""
    positions = mt5.positions_get()
    if positions is None or len(positions) == 0:
        return True, "Žádné otevřené pozice na účtu."

    ok = 0
    fail = 0
    last_msg = ""
    for pos in positions:
        success, msg = _close_one_position(pos)
        if success:
            ok += 1
        else:
            fail += 1
            last_msg = msg

    if fail == 0:
        return True, f"Zavřeno všech {ok} pozic na účtu."
    if ok == 0:
        return False, f"Nepodařilo se zavřít žádnou pozici. {last_msg}"
    return False, f"Částečný úspěch: {ok} zavřeno, {fail} selhalo. {last_msg}"


def get_positions(symbol: str | None = None) -> list[PositionInfo]:
    """Vrátí seznam pozic (pro konkrétní symbol nebo všechny)."""
    if symbol:
        raw = mt5.positions_get(symbol=symbol)
    else:
        raw = mt5.positions_get()

    if raw is None or len(raw) == 0:
        return []

    result: list[PositionInfo] = []
    for p in raw:
        type_str = "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL"
        result.append(PositionInfo(
            ticket=p.ticket,
            symbol=p.symbol,
            type=p.type,
            type_str=type_str,
            volume=p.volume,
            price_open=p.price_open,
            sl=p.sl,
            tp=p.tp,
            profit=p.profit,
            magic=p.magic,
        ))
    return result


def get_tick(symbol: str) -> TickInfo | None:
    """Vrátí aktuální bid/ask pro symbol (None pokud nelze získat)."""
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return None
    return TickInfo(
        symbol=symbol,
        bid=tick.bid,
        ask=tick.ask,
        last=tick.last,
    )


def symbol_exists(symbol: str) -> bool:
    """Ověří, že symbol je v MT5 dostupný (lze vybrat)."""
    info = mt5.symbol_info(symbol)
    return info is not None


def close_position(ticket: int) -> tuple[bool, str]:
    """Zavře jednu pozici podle jejího ticketu."""
    positions = mt5.positions_get(ticket=ticket)
    if positions is None or len(positions) == 0:
        return False, f"Pozice s ticketem {ticket} nebyla nalezena."
    return _close_one_position(positions[0])


def close_profitable() -> tuple[bool, str]:
    """Zavře všechny otevřené pozice na účtu, které jsou v jakémkoliv zisku (> 0)."""
    positions = mt5.positions_get()
    if positions is None or len(positions) == 0:
        return True, "Žádné otevřené pozice na účtu."

    ok = 0
    fail = 0
    last_msg = ""
    for pos in positions:
        if pos.profit > 0:
            success, msg = _close_one_position(pos)
            if success:
                ok += 1
            else:
                fail += 1
                last_msg = msg

    if fail == 0:
        return True, f"Zavřeno {ok} ziskových pozic na účtu."
    if ok == 0:
        return False, f"Nepodařilo se zavřít žádnou ziskovou pozici. {last_msg}"
    return False, f"Částečný úspěch: {ok} ziskových zavřeno, {fail} selhalo. {last_msg}"


def get_symbol_info(symbol: str) -> dict[str, Any] | None:
    """Vrátí informace o symbolu (point, digits, tick_value, tick_size) nebo None."""
    info = mt5.symbol_info(symbol)
    if info is None:
        return None
    return {
        "point": info.point,
        "digits": info.digits,
        "tick_value": info.trade_tick_value,
        "tick_size": info.trade_tick_size,
    }


def open_pending_stop(
    symbol: str,
    side: str,                # "BUY_STOP" nebo "SELL_STOP"
    volume: float,
    price: float,
    sl: float,
    tp: float,
    deviation: int,
    comment: str = "trading_panel",
) -> tuple[bool, str]:
    """Odešle jeden čekající stop příkaz (Buy Stop / Sell Stop)."""
    if not _ensure_symbol(symbol):
        return False, f"Nelze vybrat symbol {symbol} v Market Watch."

    side = side.upper()
    if side == "BUY_STOP":
        order_type = mt5.ORDER_TYPE_BUY_STOP
    elif side == "SELL_STOP":
        order_type = mt5.ORDER_TYPE_SELL_STOP
    else:
        return False, "Neznámý typ čekajícího příkazu."

    filling = _resolve_filling(symbol)

    request = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": symbol,
        "volume": float(volume),
        "type": order_type,
        "price": float(price),
        "sl": float(sl) if sl else 0.0,
        "tp": float(tp) if tp else 0.0,
        "deviation": int(deviation),
        "magic": MAGIC_NUMBER,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }

    result = mt5.order_send(request)
    if result is None:
        err = mt5.last_error()
        return False, f"order_send (pending) vrátil None: {err}"

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return False, (
            f"Čekající příkaz zamítnut (retcode {result.retcode}): {result.comment}"
        )

    return True, (
        f"Umístěn čekající příkaz {symbol} {side} {volume} lot @ {price:.5f} (ticket: {result.order})"
    )

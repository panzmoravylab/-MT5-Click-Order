"""QThread workery pro neblokující volání MT5.

Navrhujeme tři oddělené workery:
- ConnectWorker   — jednorázové připojení (volá se ze Settings / MainWindow).
- ActionWorker    — jednorázová obchodní akce (BUY/SELL/CLOSE/CLOSE ALL).
                   Vzniká vždy na nové vlákno pro každý požadavek.
- PollWorker      — dlouhodobě běžící vlákno, které ~2× za sekundu stahuje
                   ceny a pozice a vysílá signály do UI.

Signály (pyqtSignal) jsou thread-safe způsob, jak předat data do GUI vlákna.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

import mt5_service


class ConnectWorker(QThread):
    """Pokusí se připojit k MT5."""

    connected = pyqtSignal(str)          # zpráva o úspěchu
    failed = pyqtSignal(str)             # zpráva o selhání

    def __init__(self, login: int, password: str, server: str, terminal_path: str = ""):
        super().__init__()
        self._login = login
        self._password = password
        self._server = server
        self._terminal_path = terminal_path

    def run(self) -> None:
        success, msg = mt5_service.connect(
            self._login, self._password, self._server, self._terminal_path
        )
        if success:
            self.connected.emit(msg)
        else:
            self.failed.emit(msg)


class ActionWorker(QThread):
    """Spustí jednu obchodní akci a ohlásí výsledek."""

    # action: "buy" | "sell" | "close_symbol" | "close_all" | "close_ticket" | "close_profitable"
    done = pyqtSignal(str, bool, str)    # (action, success, message)

    def __init__(self, action: str, params: dict[str, Any]):
        super().__init__()
        self._action = action
        self._params = params

    def run(self) -> None:
        action = self._action
        params = self._params
        success = False
        msg = "Neznámá akce."

        try:
            if action in ("buy", "sell"):
                success, msg = mt5_service.open_positions(
                    symbol=params["symbol"],
                    side="BUY" if action == "buy" else "SELL",
                    position_count=params["position_count"],
                    lot_size=params["lot_size"],
                    sl=params["sl"],
                    tp=params["tp"],
                    deviation=params["deviation"],
                    comment=params.get("comment", "trading_panel"),
                )
            elif action == "close_symbol":
                success, msg = mt5_service.close_symbol(params["symbol"])
            elif action == "close_all":
                success, msg = mt5_service.close_all()
            elif action == "close_ticket":
                success, msg = mt5_service.close_position(params["ticket"])
            elif action == "close_profitable":
                success, msg = mt5_service.close_profitable()
            elif action == "place_stop":
                success, msg = mt5_service.open_pending_stop(
                    symbol=params["symbol"],
                    side=params["side"],
                    volume=params["lot_size"],
                    price=params["price"],
                    sl=params["sl"],
                    tp=params["tp"],
                    deviation=params["deviation"],
                    comment=params.get("comment", "trading_panel"),
                )
        except Exception as exc:  # noqa: BLE001 — chytáme cokoli z MT5 vlákna
            success = False
            msg = f"Výjimka při zpracování akce: {exc}"

        self.done.emit(action, success, msg)


class PollWorker(QThread):
    """Pravidelně stahuje live data z MT5 a vysílá signály do UI.

    Signál ``account`` nese dict (nebo None), ``tick`` nese dict (symbol, bid, ask),
    ``positions`` nese seznam dictů všech pozic.
    Pokud není připojeno, posílá prázdné/signál None.
    """

    account = pyqtSignal(object)         # dict | None
    tick = pyqtSignal(str, object)       # (symbol, dict | None)
    positions = pyqtSignal(str, list)    # (symbol, list[dict])

    def __init__(self, symbol: str = "", interval_ms: int = 500):
        super().__init__()
        self._symbol = symbol
        self._interval_ms = interval_ms
        self._running = True

    def set_symbol(self, symbol: str) -> None:
        """Změna aktuálního symbolu (voláno z GUI vlákna při přepnutí tabu)."""
        self._symbol = symbol

    def stop(self) -> None:
        """Zastaví smyčku (voláno před ukončením aplikace)."""
        self._running = False

    def run(self) -> None:
        while self._running:
            if mt5_service.is_connected():
                # Účet.
                acc = mt5_service.get_account_info()
                self.account.emit(acc)

                symbol = self._symbol
                if symbol:
                    tick = mt5_service.get_tick(symbol)
                    if tick is not None:
                        self.tick.emit(symbol, {
                            "bid": tick.bid,
                            "ask": tick.ask,
                            "last": tick.last,
                        })
                    else:
                        self.tick.emit(symbol, None)

                    # Získáme VŠECHNY pozice na účtu (předáváme None)
                    positions = mt5_service.get_positions(None)
                    self.positions.emit(symbol, [self._pos_to_dict(p) for p in positions])
                else:
                    self.tick.emit("", None)
                    self.positions.emit("", [])
            else:
                self.account.emit(None)
                self.tick.emit(self._symbol, None)
                self.positions.emit(self._symbol, [])

            self.msleep(self._interval_ms)

    @staticmethod
    def _pos_to_dict(p) -> dict[str, Any]:
        return {
            "ticket": p.ticket,
            "symbol": p.symbol,
            "type": p.type_str,
            "volume": p.volume,
            "price_open": p.price_open,
            "sl": p.sl,
            "tp": p.tp,
            "profit": p.profit,
            "magic": p.magic,
        }

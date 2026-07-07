"""Hlavní okno aplikace — taby pro symboly, status bar, propojení workerů.

Zodpovědnosti:
- Drží config (načtený z config_manager).
- Vytváří SymbolPanel pro každý symbol v tabech.
- Spouští PollWorker pro live data a přeposílá signály do aktivního panelu.
- Spouští ActionWorker pro BUY/SELL/CLOSE/CLOSE ALL.
- Poskytuje Settings dialog a přidávání/odebírání symbolů.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import config_manager
import mt5_service
from ui.symbol_panel import SymbolPanel
from ui.settings_dialog import SettingsDialog
from ui.workers import ActionWorker, ConnectWorker, PollWorker


TRADING_QSS = """
QMainWindow, QDialog, SymbolPanel, SettingsDialog, QTabWidget, QGroupBox, QWidget#centralWidget {
    background-color: #0f172a; /* Slate 900 */
}

/* Base text color */
QLabel, QCheckBox, QRadioButton, QGroupBox {
    color: #e2e8f0; /* slate 200 - readable light grey */
    font-family: "Segoe UI", -apple-system, Roboto, sans-serif;
    font-size: 11px;
}

/* Explicitly style the price label to stand out */
QLabel#priceLabel {
    color: #38bdf8; /* sky blue */
}

/* Inputs styling */
QLineEdit, QComboBox {
    background-color: #1e293b; /* slate 800 */
    border: 1px solid #475569; /* slate 600 */
    border-radius: 4px;
    padding: 3px 6px;
    color: #f8fafc; /* slate 50 */
    min-height: 18px;
    selection-background-color: #3b82f6;
}

QLineEdit:focus, QComboBox:focus {
    border: 1px solid #38bdf8;
    background-color: #1e293b;
}

QSpinBox, QDoubleSpinBox {
    background-color: #1e293b; /* slate 800 */
    border: 1px solid #475569; /* slate 600 */
    border-radius: 4px;
    padding: 3px 18px 3px 6px; /* Space for buttons on the right */
    color: #f8fafc; /* slate 50 */
    min-height: 18px;
    selection-background-color: #3b82f6;
}

QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #38bdf8;
}

QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 14px;
    border-left: 1px solid #475569;
    border-bottom: 1px solid #475569;
    background-color: #1e293b;
    border-top-right-radius: 3px;
}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {
    background-color: #334155;
}

QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 14px;
    border-left: 1px solid #475569;
    background-color: #1e293b;
    border-bottom-right-radius: 3px;
}

QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #334155;
}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    width: 0;
    height: 0;
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-bottom: 4px solid #94a3b8;
}

QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    width: 0;
    height: 0;
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-top: 4px solid #94a3b8;
}

QComboBox QAbstractItemView {
    background-color: #1e293b;
    border: 1px solid #475569;
    color: #f8fafc;
    selection-background-color: #3b82f6;
}

/* GroupBox styling */
QGroupBox {
    border: 1px solid #334155;
    border-radius: 6px;
    margin-top: 10px;
    font-weight: bold;
    color: #38bdf8; /* light blue title */
    background-color: #1e293b;
    padding: 8px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    padding: 0 4px;
}

QPushButton {
    background-color: #334155;
    border: 1px solid #475569;
    border-radius: 4px;
    color: #f8fafc;
    padding: 4px 8px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: #475569;
}

QPushButton:pressed {
    background-color: #1e293b;
}

QPushButton:disabled {
    background-color: #0f172a;
    color: #64748b;
    border: 1px solid #1e293b;
}

/* Tab widget */
QTabWidget::pane {
    border: 1px solid #334155;
    background-color: #0f172a;
}

QTabBar::tab {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-bottom: none;
    padding: 4px 8px;
    color: #94a3b8;
    font-weight: bold;
    font-size: 10px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}

QTabBar::tab:selected {
    background-color: #0f172a;
    color: #38bdf8;
    border-bottom: 2px solid #38bdf8;
}

QTabBar::tab:hover {
    background-color: #334155;
    color: #f1f5f9;
}

/* Table styling */
QTableWidget {
    background-color: #141c2f;
    alternate-background-color: #1a2540;
    border: 1px solid #334155;
    gridline-color: #334155;
    border-radius: 6px;
    color: #e2e8f0;
}

QTableWidget::item {
    border-bottom: 1px solid #334155;
    padding: 2px;
}

QTableWidget::item:selected {
    background-color: #3b82f6;
    color: white;
}

QHeaderView::section {
    background-color: #0f172a;
    color: #94a3b8;
    font-weight: bold;
    padding: 4px;
    border: none;
    border-right: 1px solid #334155;
    border-bottom: 1px solid #334155;
}

/* ScrollBars */
QScrollBar:vertical {
    border: none;
    background: #0f172a;
    width: 8px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #475569;
    min-height: 20px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #64748b;
}

QScrollBar:horizontal {
    border: none;
    background: #0f172a;
    height: 8px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background: #475569;
    min-width: 20px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal:hover {
    background: #64748b;
}

QStatusBar {
    background-color: #0f172a;
    color: #94a3b8;
    border-top: 1px solid #334155;
}
"""


class AddSymbolDialog(QDialog):
    """Dialog pro přidání nového symbolu s výchozími parametry."""

    def __init__(self, existing: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Přidat symbol")
        self.setMinimumWidth(360)
        self._existing = existing

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.symbol_edit = QLineEdit()
        self.symbol_edit.setPlaceholderText("např. GBPUSD")
        self.symbol_edit.textChanged.connect(self._normalize)

        self.lot_spin = QDoubleEdit()
        self.lot_spin.setDecimals(2)
        self.lot_spin.setRange(0.01, 1000.0)
        self.lot_spin.setValue(0.10)

        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 100)
        self.count_spin.setValue(1)

        form.addRow("Symbol:", self.symbol_edit)
        form.addRow("Výchozí počet pozic:", self.count_spin)
        form.addRow("Výchozí lot:", self.lot_spin)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _normalize(self) -> None:
        # Velká písmena automaticky.
        self.symbol_edit.setText(self.symbol_edit.text().upper())

    def _validate_and_accept(self) -> None:
        sym = self.symbol_edit.text().strip().upper()
        if not sym:
            QMessageBox.warning(self, "Chyba", "Zadej název symbolu.")
            return
        if sym in self._existing:
            QMessageBox.warning(self, "Existuje", f"Symbol {sym} už v panelu je.")
            return
        self.accept()

    def values(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol_edit.text().strip().upper(),
            "position_count": self.count_spin.value(),
            "lot_size": self.lot_spin.value(),
        }


# QDoubleSpinBox s krátkým aliasem (import by kolidoval se zápisem výše)
from PyQt6.QtWidgets import QDoubleSpinBox as QDoubleEdit


class MainWindow(QMainWindow):
    """Hlavní okno trading panelu."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Trading Panel — MetaTrader 5")
        self.resize(380, 680)
        self.setStyleSheet(TRADING_QSS)

        self._config = config_manager.load_config()

        # Stav.
        self._panels: dict[str, SymbolPanel] = {}
        self._poll_worker: PollWorker | None = None
        self._action_worker: ActionWorker | None = None
        self._connect_worker: ConnectWorker | None = None
        self._autoconnect_done = False

        self._build_ui()
        self._populate_tabs()
        self._start_poll_worker()

        # Auto-connect pokud jsou údaje uložené.
        self._maybe_auto_connect()

    # --------------------------------------------------------------- build
    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # --- Horní lišta: status vlevo, tlačítka vpravo ----------------
        top = QHBoxLayout()

        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: #475569; font-size: 11px;")
        top.addWidget(self.status_dot)

        self.status_label = QLabel("Nepřipojeno")
        self.status_label.setStyleSheet("font-weight: bold; color: gray;")
        top.addWidget(self.status_label)

        top.addStretch(1)

        self.add_btn = QPushButton("➕")
        self.add_btn.setToolTip("Přidat symbol")
        self.add_btn.setFixedWidth(28)
        self.add_btn.clicked.connect(self._add_symbol)
        top.addWidget(self.add_btn)

        self.remove_btn = QPushButton("➖")
        self.remove_btn.setToolTip("Odebrat symbol")
        self.remove_btn.setFixedWidth(28)
        self.remove_btn.clicked.connect(self._remove_symbol)
        top.addWidget(self.remove_btn)

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setToolTip("Nastavení")
        self.settings_btn.setFixedWidth(28)
        self.settings_btn.clicked.connect(self._open_settings)
        top.addWidget(self.settings_btn)

        root.addLayout(top)

        # --- Taby ---------------------------------------------------------
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(False)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self.tabs, 1)

        # --- Status bar ---------------------------------------------------
        self.sb = QStatusBar()
        self.setStatusBar(self.sb)
        self.sb.showMessage("Připraveno. Otevři Nastavení pro přihlášení k MT5.")

    def _populate_tabs(self) -> None:
        self.tabs.clear()
        self._panels.clear()
        symbols = list(self._config.get("symbols", {}).keys())
        for symbol in symbols:
            params = config_manager.get_symbol_params(self._config, symbol)
            panel = SymbolPanel(symbol, params)
            panel.action_requested.connect(self._on_action_requested)
            panel.params_changed.connect(self._on_params_changed)
            self._panels[symbol] = panel
            self.tabs.addTab(panel, symbol)

    # ----------------------------------------------------- poll worker
    def _start_poll_worker(self) -> None:
        if self._poll_worker is not None:
            return
        symbol = self._current_symbol()
        self._poll_worker = PollWorker(symbol=symbol)
        self._poll_worker.account.connect(self._on_account)
        self._poll_worker.tick.connect(self._on_tick)
        self._poll_worker.positions.connect(self._on_positions)
        self._poll_worker.start()

    def _current_symbol(self) -> str:
        idx = self.tabs.currentIndex()
        if idx < 0:
            return ""
        return self.tabs.tabText(idx)

    def _on_tab_changed(self, _idx: int) -> None:
        symbol = self._current_symbol()
        if self._poll_worker:
            self._poll_worker.set_symbol(symbol)
        # Hned vymažeme tabulku starého panelu? Ne, poll worker brzy dodá čerstvá data.

    # ---------------------------------------------------- live callbacks
    def _on_account(self, acc: dict | None) -> None:
        if acc is None:
            self.status_dot.setStyleSheet("color: #475569; font-size: 11px;")
            self.status_label.setText("Nepřipojeno")
            self.status_label.setStyleSheet("font-weight: bold; color: #64748b;")
            return
        self.status_dot.setStyleSheet("color: #22c55e; font-size: 11px;")
        self.status_label.setText(
            f"Připojeno  •  {acc['login']}  •  Bal: {acc['balance']:.2f} {acc['currency']}"
        )
        self.status_label.setStyleSheet("font-weight: bold; color: #166534;")

    def _on_tick(self, symbol: str, tick: dict | None) -> None:
        if not symbol:
            return
        panel = self._panels.get(symbol)
        if panel:
            panel.update_tick(tick)

    def _on_positions(self, symbol: str, positions: list[dict]) -> None:
        if not symbol:
            return
        panel = self._panels.get(symbol)
        if panel:
            panel.update_positions(positions)

    # ------------------------------------------------------- akce / obchody
    def _on_action_requested(self, action: str, params: dict) -> None:
        if not mt5_service.is_connected():
            QMessageBox.warning(
                self, "Nepřipojeno",
                "Nejprve se připoj k MT5 přes Nastavení.",
            )
            return
        if self._action_worker is not None and self._action_worker.isRunning():
            QMessageBox.information(
                self, "Zpracovává se",
                "Již probíhá jiná akce — chvíli počkej.",
            )
            return

        # Potvrzení pro CLOSE ALL (reálné peníze).
        if action == "close_all":
            confirm = QMessageBox.question(
                self, "Potvrzení — CLOSE ALL",
                "Opravdu zavřít VŠECHNY otevřené pozice na účtu?\n\n"
                "Tato akce nelze vrátit zpět.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
        # Potvrzení pro CLOSE V ZISKU.
        elif action == "close_profitable":
            confirm = QMessageBox.question(
                self, "Potvrzení — CLOSE V ZISKU",
                "Opravdu zavřít všechny ziskové pozice na účtu?\n\n"
                "Tato akce nelze vrátit zpět.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return

        # Zablokuj tlačítka aktivního panelu.
        active_panel = self._panels.get(self._current_symbol())
        if active_panel:
            active_panel.set_busy(True)

        self._action_worker = ActionWorker(action, params)
        self._action_worker.done.connect(
            lambda a, ok, msg: self._on_action_done(a, ok, msg, active_panel)
        )
        self._action_worker.start()
        self.sb.showMessage(f"Odesílám: {action.upper()} …")

    def _on_action_done(self, action: str, success: bool, msg: str, panel: SymbolPanel | None) -> None:
        if panel:
            panel.set_busy(False)
        if success:
            self.sb.showMessage(f"✓ {msg}", 5000)
            QMessageBox.information(self, "Hotovo", msg)
        else:
            self.sb.showMessage(f"✗ {msg}", 8000)
            QMessageBox.warning(self, "Akce selhala", msg)

    # --------------------------------------------------- params persistence
    def _on_params_changed(self, symbol: str, params: dict) -> None:
        """Uloží změnu parametrů symbolu do configu (live ukládání)."""
        config_manager.set_symbol_params(self._config, symbol, params)
        config_manager.save_config(self._config)

    # --------------------------------------------------------- settings
    def _open_settings(self) -> None:
        dlg = SettingsDialog(self._config, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            values = dlg.values()
            self._config["mt5"]["login"] = values["login"]
            self._config["mt5"]["password"] = values["password"]
            self._config["mt5"]["server"] = values["server"]
            self._config["mt5"]["terminal_path"] = values["terminal_path"]
            config_manager.save_config(self._config)
            # Po uložení se rovnou připojíme.
            self._connect(values["login"], values["password"], values["server"], values["terminal_path"])

    def _maybe_auto_connect(self) -> None:
        if self._autoconnect_done:
            return
        cred = config_manager.get_mt5_credentials(self._config)
        if cred["login"] != 0 and cred["password"] and cred["server"]:
            self._autoconnect_done = True
            self._connect(cred["login"], cred["password"], cred["server"], cred["terminal_path"])

    def _connect(self, login: int, password: str, server: str, terminal_path: str) -> None:
        if self._connect_worker is not None and self._connect_worker.isRunning():
            return
        self.settings_btn.setEnabled(False)
        self.sb.showMessage("Připojuji k MT5 …")
        self._connect_worker = ConnectWorker(login, password, server, terminal_path)
        self._connect_worker.connected.connect(self._on_connect_ok)
        self._connect_worker.failed.connect(self._on_connect_fail)
        self._connect_worker.start()

    def _on_connect_ok(self, msg: str) -> None:
        self.settings_btn.setEnabled(True)
        self.sb.showMessage(f"✓ {msg}", 5000)

    def _on_connect_fail(self, msg: str) -> None:
        self.settings_btn.setEnabled(True)
        self.sb.showMessage(f"✗ {msg}", 8000)
        QMessageBox.warning(self, "Připojení selhalo", msg)

    # ----------------------------------------------------- symboly CRUD
    def _add_symbol(self) -> None:
        existing = list(self._config.get("symbols", {}).keys())
        dlg = AddSymbolDialog(existing, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        vals = dlg.values()
        symbol = vals["symbol"]

        # Pokud jsme připojeni, ověříme, že symbol v MT5 existuje.
        if mt5_service.is_connected():
            if not mt5_service.symbol_exists(symbol):
                ret = QMessageBox.question(
                    self, "Symbol neznámý",
                    f"Symbol „{symbol}“ nebyl v MT5 nalezen.\n\nPřesto ho přidat?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if ret != QMessageBox.StandardButton.Yes:
                    return

        added = config_manager.add_symbol(
            self._config, symbol,
            {"position_count": vals["position_count"], "lot_size": vals["lot_size"]},
        )
        if not added:
            QMessageBox.information(self, "Existuje", f"Symbol {symbol} už existuje.")
            return
        config_manager.save_config(self._config)

        params = config_manager.get_symbol_params(self._config, symbol)
        panel = SymbolPanel(symbol, params)
        panel.action_requested.connect(self._on_action_requested)
        panel.params_changed.connect(self._on_params_changed)
        self._panels[symbol] = panel
        self.tabs.addTab(panel, symbol)
        self.tabs.setCurrentWidget(panel)

    def _remove_symbol(self) -> None:
        symbol = self._current_symbol()
        if not symbol:
            return
        # Neumožníme smazat poslední symbol.
        if self.tabs.count() <= 1:
            QMessageBox.information(self, "Nelze smazat", "Musí zůstat alespoň jeden symbol.")
            return
        ret = QMessageBox.question(
            self, "Smazat symbol",
            f"Odebrat „{symbol}“ z panelu?\n\n(Existující pozice v MT5 zůstávají.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        config_manager.remove_symbol(self._config, symbol)
        config_manager.save_config(self._config)

        idx = self.tabs.currentIndex()
        self.tabs.removeTab(idx)
        self._panels.pop(symbol, None)

    # --------------------------------------------------------- shutdown
    def closeEvent(self, event) -> None:  # noqa: N802 — Qt API
        """Uklidíme workery a MT5 spojení při zavření okna."""
        if self._poll_worker is not None:
            self._poll_worker.stop()
            self._poll_worker.wait(2000)

        for w in (self._action_worker, self._connect_worker):
            if w is not None and w.isRunning():
                w.wait(3000)

        try:
            mt5_service.disconnect()
        except Exception:
            pass
        event.accept()

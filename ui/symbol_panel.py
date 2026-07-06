"""Panel pro jeden symbol — vstupy parametrů, akční tlačítka, tabulka pozic.

Panel je soběstačný: dostane symbol a config, načte parametry, zobrazí live
cenu a pozice (přes signály z PollWorker předávané z MainWindow), a při
kliknutí na BUY/SELL/CLOSE/CLOSE ALL vyšle signál, který MainWindow pošle
do ActionWorker.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class SymbolPanel(QWidget):
    """UI pro jeden obchodovaný pár.

    Signály (vysílá MainWindow do ActionWorker):
        action_requested(str, dict) — (action, params)
    """

    action_requested = pyqtSignal(str, dict)
    params_changed = pyqtSignal(str, dict)   # (symbol, params) — pro uložení do configu

    def __init__(self, symbol: str, params: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._symbol = symbol
        self._params = dict(params)
        self._build_ui()
        self._load_params()

    # --------------------------------------------------------------- build
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # --- Hlavička: symbol + live cena ---------------------------------
        header = QHBoxLayout()
        title = QLabel(self._symbol)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch(1)

        self.price_label = QLabel("Bid: —  |  Ask: —")
        self.price_label.setStyleSheet("font-size: 14px; color: #2b6cb0;")
        self.price_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self.price_label)
        root.addLayout(header)

        # --- Vstupy parametrů --------------------------------------------
        params_box = QGroupBox("Parametry obchodu")
        grid = QGridLayout(params_box)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(6)

        lbl_count = QLabel("Počet pozic")
        lbl_lot = QLabel("Velikost lotu")
        lbl_sl = QLabel("SL (cena)")
        lbl_tp = QLabel("TP (cena)")
        lbl_dev = QLabel("Deviace (body)")
        for lbl in (lbl_count, lbl_lot, lbl_sl, lbl_tp, lbl_dev):
            lbl.setStyleSheet("font-weight: bold;")

        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 100)
        self.count_spin.setSingleStep(1)

        self.lot_spin = QDoubleSpinBox()
        self.lot_spin.setDecimals(2)
        self.lot_spin.setRange(0.01, 1000.0)
        self.lot_spin.setSingleStep(0.01)

        self.sl_spin = QDoubleSpinBox()
        self.sl_spin.setDecimals(5)
        self.sl_spin.setRange(0.0, 1_000_000.0)
        self.sl_spin.setSingleStep(0.1)

        self.tp_spin = QDoubleSpinBox()
        self.tp_spin.setDecimals(5)
        self.tp_spin.setRange(0.0, 1_000_000.0)
        self.tp_spin.setSingleStep(0.1)

        self.dev_spin = QSpinBox()
        self.dev_spin.setRange(0, 10000)
        self.dev_spin.setSingleStep(5)

        grid.addWidget(lbl_count, 0, 0)
        grid.addWidget(self.count_spin, 1, 0)
        grid.addWidget(lbl_lot, 0, 1)
        grid.addWidget(self.lot_spin, 1, 1)
        grid.addWidget(lbl_sl, 2, 0)
        grid.addWidget(self.sl_spin, 3, 0)
        grid.addWidget(lbl_tp, 2, 1)
        grid.addWidget(self.tp_spin, 3, 1)
        grid.addWidget(lbl_dev, 4, 0)
        grid.addWidget(self.dev_spin, 5, 0)

        # Propojení změn → signál params_changed.
        for spin in (self.count_spin, self.lot_spin, self.sl_spin, self.tp_spin, self.dev_spin):
            spin.valueChanged.connect(self._on_params_changed)

        root.addWidget(params_box)

        # --- Akční tlačítka ----------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.buy_btn = QPushButton("▲  BUY")
        self.buy_btn.setStyleSheet(
            "QPushButton { background-color: #16a34a; color: white; "
            "font-size: 15px; font-weight: bold; padding: 12px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #15803d; }"
            "QPushButton:disabled { background-color: #9ca3af; }"
        )
        self.buy_btn.clicked.connect(lambda: self._emit_action("buy"))

        self.sell_btn = QPushButton("▼  SELL")
        self.sell_btn.setStyleSheet(
            "QPushButton { background-color: #dc2626; color: white; "
            "font-size: 15px; font-weight: bold; padding: 12px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #b91c1c; }"
            "QPushButton:disabled { background-color: #9ca3af; }"
        )
        self.sell_btn.clicked.connect(lambda: self._emit_action("sell"))

        self.close_btn = QPushButton("CLOSE pár")
        self.close_btn.setStyleSheet(
            "QPushButton { background-color: #6b7280; color: white; "
            "font-size: 13px; font-weight: bold; padding: 12px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #4b5563; }"
            "QPushButton:disabled { background-color: #9ca3af; }"
        )
        self.close_btn.clicked.connect(lambda: self._emit_action("close_symbol"))

        self.close_all_btn = QPushButton("⚠  CLOSE ALL")
        self.close_all_btn.setStyleSheet(
            "QPushButton { background-color: #b45309; color: white; "
            "font-size: 13px; font-weight: bold; padding: 12px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #92400e; }"
            "QPushButton:disabled { background-color: #9ca3af; }"
        )
        self.close_all_btn.clicked.connect(lambda: self._emit_action("close_all"))

        btn_row.addWidget(self.buy_btn, 2)
        btn_row.addWidget(self.sell_btn, 2)
        btn_row.addWidget(self.close_btn, 1)
        btn_row.addWidget(self.close_all_btn, 1)
        root.addLayout(btn_row)

        # --- Tabulka pozic -----------------------------------------------
        positions_box = QGroupBox(f"Otevřené pozice — {self._symbol}")
        pv = QVBoxLayout(positions_box)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["#", "Typ", "Lot", "Cena", "P/L", "Magic"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for col in range(1, 6):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(120)
        pv.addWidget(self.table)

        self.positions_summary = QLabel("Žádné otevřené pozice.")
        self.positions_summary.setStyleSheet("color: gray; font-size: 11px;")
        pv.addWidget(self.positions_summary)

        root.addWidget(positions_box)

        root.addStretch(1)

    # -------------------------------------------------------- params I/O
    def _load_params(self) -> None:
        self.count_spin.setValue(int(self._params.get("position_count", 1)))
        self.lot_spin.setValue(float(self._params.get("lot_size", 0.01)))
        self.sl_spin.setValue(float(self._params.get("sl", 0.0)))
        self.tp_spin.setValue(float(self._params.get("tp", 0.0)))
        self.dev_spin.setValue(int(self._params.get("deviation", 20)))

    def set_params(self, params: dict[str, Any]) -> None:
        """Aktualizuje vstupy zvenčí (např. po editaci configu)."""
        self._params = dict(params)
        self._load_params()

    def _current_params(self) -> dict[str, Any]:
        return {
            "position_count": self.count_spin.value(),
            "lot_size": self.lot_spin.value(),
            "sl": self.sl_spin.value(),
            "tp": self.tp_spin.value(),
            "deviation": self.dev_spin.value(),
        }

    def _on_params_changed(self) -> None:
        params = self._current_params()
        self._params = params
        self.params_changed.emit(self._symbol, params)

    def _emit_action(self, action: str) -> None:
        params = {"symbol": self._symbol}
        if action in ("buy", "sell"):
            params.update(self._current_params())
        elif action == "close_symbol":
            params["symbol"] = self._symbol
        # close_all: nepotřebuje symbol (zavře vše)
        self.action_requested.emit(action, params)

    # ------------------------------------------------------- live updates
    def update_tick(self, tick: dict | None) -> None:
        if tick is None:
            self.price_label.setText("Bid: —  |  Ask: —")
            return
        self.price_label.setText(
            f"Bid: {tick['bid']:.5f}  |  Ask: {tick['ask']:.5f}"
        )

    def update_positions(self, positions: list[dict]) -> None:
        self.table.setRowCount(0)
        total_pl = 0.0
        for p in positions:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(p["ticket"])))
            type_item = QTableWidgetItem(p["type"])
            type_item.setForeground(
                Qt.GlobalColor.green if p["type"] == "BUY" else Qt.GlobalColor.red
            )
            self.table.setItem(row, 1, type_item)
            self.table.setItem(row, 2, QTableWidgetItem(f"{p['volume']:.2f}"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{p['price_open']:.5f}"))

            pl_item = QTableWidgetItem(f"{p['profit']:.2f}")
            pl_color = Qt.GlobalColor.green if p["profit"] >= 0 else Qt.GlobalColor.red
            pl_item.setForeground(pl_color)
            self.table.setItem(row, 4, pl_item)

            self.table.setItem(row, 5, QTableWidgetItem(str(p["magic"])))
            total_pl += p["profit"]

        count = len(positions)
        if count == 0:
            self.positions_summary.setText("Žádné otevřené pozice.")
        else:
            self.positions_summary.setText(
                f"{count} pozic — celkové P/L: {total_pl:.2f}"
            )

    # -------------------------------------------------------- busy state
    def set_busy(self, busy: bool) -> None:
        """Při probíhající akci deaktivuje tlačítka (prevence dvojkliku)."""
        for btn in (self.buy_btn, self.sell_btn, self.close_btn, self.close_all_btn):
            btn.setEnabled(not busy)

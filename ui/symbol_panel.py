"""Panel pro jeden symbol — vstupy parametrů, akční tlačítka, tabulka pozic.

Panel je soběstačný: dostane symbol a config, načte parametry, zobrazí live
cenu a pozice (přes signály z PollWorker předávané z MainWindow), a při
kliknutí na BUY/SELL/CLOSE/CLOSE ALL/CLOSE V ZISKU vysílá signál.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
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
        params_changed(str, dict) — (symbol, params)
    """

    action_requested = pyqtSignal(str, dict)
    params_changed = pyqtSignal(str, dict)   # (symbol, params) — pro uložení do configu

    def __init__(self, symbol: str, params: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._symbol = symbol
        self._params = dict(params)
        self._last_tick = None
        self._point = 0.00001
        self._digits = 5
        self._point_fetched = False
        
        self._build_ui()
        self._load_params()

    # --------------------------------------------------------------- build
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(5, 5, 5, 5)
        root.setSpacing(6)

        # --- Hlavička: symbol + live cena ---------------------------------
        header = QHBoxLayout()
        title = QLabel(self._symbol)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch(1)

        self.price_label = QLabel("Bid: —  |  Ask: —")
        self.price_label.setStyleSheet("font-size: 14px; color: #38bdf8; font-weight: bold;")
        self.price_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self.price_label)
        root.addLayout(header)

        # --- Vstupy parametrů --------------------------------------------
        params_box = QGroupBox("Parametry obchodu")
        grid = QGridLayout(params_box)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(8)

        lbl_count = QLabel("Počet pozic")
        lbl_lot = QLabel("Velikost lotu")
        lbl_sl = QLabel("SL (body)")
        lbl_tp = QLabel("TP (body)")
        lbl_dev = QLabel("Deviace (body)")
        lbl_tf = QLabel("Komentář (Timeframe)")
        
        for lbl in (lbl_count, lbl_lot, lbl_sl, lbl_tp, lbl_dev, lbl_tf):
            lbl.setStyleSheet("font-weight: bold;")

        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 100)
        self.count_spin.setSingleStep(1)

        self.lot_spin = QDoubleSpinBox()
        self.lot_spin.setDecimals(2)
        self.lot_spin.setRange(0.01, 1000.0)
        self.lot_spin.setSingleStep(0.01)
        self.lot_spin.valueChanged.connect(self._update_sl_tp_labels)

        self.sl_spin = QSpinBox()
        self.sl_spin.setRange(0, 100000)
        self.sl_spin.setSingleStep(10)
        self.sl_spin.valueChanged.connect(self._update_sl_tp_labels)

        self.tp_spin = QSpinBox()
        self.tp_spin.setRange(0, 100000)
        self.tp_spin.setSingleStep(10)
        self.tp_spin.valueChanged.connect(self._update_sl_tp_labels)

        self.dev_spin = QSpinBox()
        self.dev_spin.setRange(0, 10000)
        self.dev_spin.setSingleStep(5)
        self.dev_spin.setToolTip("Maximální povolený skluz ceny (slippage) v bodech při vstupu. Běžně se nastavuje 20-50 bodů.")

        lbl_dev_info = QLabel("Max. skluz ceny v bodech.")
        lbl_dev_info.setStyleSheet("color: #64748b; font-size: 11px;")

        # Timeframe comment selector
        tf_container = QWidget()
        tf_layout = QHBoxLayout(tf_container)
        tf_layout.setContentsMargins(0, 0, 0, 0)
        tf_layout.setSpacing(4)
        
        self.tf_group = QButtonGroup(self)
        self.tf_buttons = {}
        for tf in ["M1", "M5", "M15", "M30", "H1"]:
            btn = QPushButton(tf)
            btn.setCheckable(True)
            btn.setStyleSheet(
                "QPushButton { background-color: #1e293b; color: #94a3b8; border: 1px solid #334155; border-radius: 4px; padding: 4px 8px; font-weight: bold; }"
                "QPushButton:checked { background-color: #3b82f6; color: white; border-color: #2563eb; }"
                "QPushButton:hover { background-color: #334155; color: #f1f5f9; }"
            )
            self.tf_group.addButton(btn)
            tf_layout.addWidget(btn)
            self.tf_buttons[tf] = btn
        
        # Default timeframe M15
        self.tf_buttons["M15"].setChecked(True)

        # Cílové SL/TP ceny popisky
        self.buy_sl_label = QLabel("BUY SL: —")
        self.sell_sl_label = QLabel("SELL SL: —")
        self.buy_tp_label = QLabel("BUY TP: —")
        self.sell_tp_label = QLabel("SELL TP: —")
        
        for lbl in (self.buy_sl_label, self.sell_sl_label, self.buy_tp_label, self.sell_tp_label):
            lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")

        # Uspořádání do Gridu
        grid.addWidget(lbl_count, 0, 0)
        grid.addWidget(self.count_spin, 1, 0)
        grid.addWidget(lbl_lot, 0, 1)
        grid.addWidget(self.lot_spin, 1, 1)
        
        grid.addWidget(lbl_sl, 2, 0)
        grid.addWidget(self.sl_spin, 3, 0)
        grid.addWidget(lbl_tp, 2, 1)
        grid.addWidget(self.tp_spin, 3, 1)
        
        # SL dynamic labels below SL spinbox
        sl_lbl_lay = QVBoxLayout()
        sl_lbl_lay.addWidget(self.buy_sl_label)
        sl_lbl_lay.addWidget(self.sell_sl_label)
        grid.addLayout(sl_lbl_lay, 4, 0)
        
        # TP dynamic labels below TP spinbox
        tp_lbl_lay = QVBoxLayout()
        tp_lbl_lay.addWidget(self.buy_tp_label)
        tp_lbl_lay.addWidget(self.sell_tp_label)
        grid.addLayout(tp_lbl_lay, 4, 1)

        grid.addWidget(lbl_dev, 5, 0)
        grid.addWidget(self.dev_spin, 6, 0)
        grid.addWidget(lbl_dev_info, 7, 0)
        
        grid.addWidget(lbl_tf, 5, 1)
        grid.addWidget(tf_container, 6, 1)

        # Uložit jako výchozí tlačítko
        self.save_defaults_btn = QPushButton("💾  Uložit jako výchozí")
        self.save_defaults_btn.setStyleSheet(
            "QPushButton { background-color: #3b82f6; color: white; font-weight: bold; padding: 6px; border-radius: 4px; border: none; }"
            "QPushButton:hover { background-color: #2563eb; }"
        )
        self.save_defaults_btn.clicked.connect(self._on_save_defaults)
        grid.addWidget(self.save_defaults_btn, 8, 0, 1, 2)

        root.addWidget(params_box)

        # --- Akční tlačítka ----------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.buy_btn = QPushButton("▲  BUY")
        self.buy_btn.setStyleSheet(
            "QPushButton { background-color: #22c55e; color: white; "
            "font-size: 13px; font-weight: bold; padding: 8px 16px; border-radius: 4px; border: none; }"
            "QPushButton:hover { background-color: #16a34a; }"
            "QPushButton:disabled { background-color: #1e293b; color: #475569; }"
        )
        self.buy_btn.clicked.connect(lambda: self._emit_action("buy"))

        self.sell_btn = QPushButton("▼  SELL")
        self.sell_btn.setStyleSheet(
            "QPushButton { background-color: #ef4444; color: white; "
            "font-size: 13px; font-weight: bold; padding: 8px 16px; border-radius: 4px; border: none; }"
            "QPushButton:hover { background-color: #dc2626; }"
            "QPushButton:disabled { background-color: #1e293b; color: #475569; }"
        )
        self.sell_btn.clicked.connect(lambda: self._emit_action("sell"))

        self.close_btn = QPushButton("CLOSE pár")
        self.close_btn.setStyleSheet(
            "QPushButton { background-color: #475569; color: white; "
            "font-size: 11px; font-weight: bold; padding: 8px; border-radius: 4px; border: none; }"
            "QPushButton:hover { background-color: #334155; }"
            "QPushButton:disabled { background-color: #1e293b; color: #475569; }"
        )
        self.close_btn.clicked.connect(lambda: self._emit_action("close_symbol"))

        self.close_profit_btn = QPushButton("💰 CLOSE ZISK")
        self.close_profit_btn.setStyleSheet(
            "QPushButton { background-color: #0d9488; color: white; "
            "font-size: 11px; font-weight: bold; padding: 8px; border-radius: 4px; border: none; }"
            "QPushButton:hover { background-color: #0f766e; }"
            "QPushButton:disabled { background-color: #1e293b; color: #475569; }"
        )
        self.close_profit_btn.clicked.connect(lambda: self._emit_action("close_profitable"))

        self.close_all_btn = QPushButton("⚠ CLOSE ALL")
        self.close_all_btn.setStyleSheet(
            "QPushButton { background-color: #ea580c; color: white; "
            "font-size: 11px; font-weight: bold; padding: 8px; border-radius: 4px; border: none; }"
            "QPushButton:hover { background-color: #c2410c; }"
            "QPushButton:disabled { background-color: #1e293b; color: #475569; }"
        )
        self.close_all_btn.clicked.connect(lambda: self._emit_action("close_all"))

        btn_row.addWidget(self.buy_btn, 2)
        btn_row.addWidget(self.sell_btn, 2)
        btn_row.addWidget(self.close_btn, 1)
        btn_row.addWidget(self.close_profit_btn, 1)
        btn_row.addWidget(self.close_all_btn, 1)
        root.addLayout(btn_row)

        # --- Tabulka pozic -----------------------------------------------
        positions_box = QGroupBox("Všechny otevřené pozice")
        pv = QVBoxLayout(positions_box)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["#", "Symbol", "Typ", "Lot", "Cena", "P/L", "Magic", "Akce"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setMinimumHeight(140)
        pv.addWidget(self.table)

        self.positions_summary = QLabel("Žádné otevřené pozice.")
        self.positions_summary.setStyleSheet("color: gray; font-size: 11px;")
        pv.addWidget(self.positions_summary)

        root.addWidget(positions_box)

        # --- Čekající stop objednávky (Stop Orders) -----------------------
        stop_box = QGroupBox("Čekající stop objednávky")
        stop_grid = QGridLayout(stop_box)
        stop_grid.setHorizontalSpacing(15)
        stop_grid.setVerticalSpacing(4)
        
        lbl_stop_side = QLabel("Typ Stopu")
        lbl_stop_price = QLabel("Vstupní cena")
        lbl_stop_sl = QLabel("SL (body)")
        lbl_stop_tp = QLabel("TP (body)")
        
        for lbl in (lbl_stop_side, lbl_stop_price, lbl_stop_sl, lbl_stop_tp):
            lbl.setStyleSheet("font-weight: bold; font-size: 11px;")
            
        self.stop_side_combo = QComboBox()
        self.stop_side_combo.addItems(["BUY STOP", "SELL STOP"])
        self.stop_side_combo.currentIndexChanged.connect(self._update_stop_lbls)
        
        self.stop_price_spin = QDoubleSpinBox()
        self.stop_price_spin.setRange(0.0, 1_000_000.0)
        self.stop_price_spin.setDecimals(5)
        self.stop_price_spin.setSingleStep(0.1)
        self.stop_price_spin.valueChanged.connect(self._update_stop_lbls)
        
        self.update_price_btn = QPushButton("🔄")
        self.update_price_btn.setToolTip("Nastavit aktuální tržní cenu")
        self.update_price_btn.setFixedWidth(28)
        self.update_price_btn.setStyleSheet(
            "QPushButton { background-color: #1e293b; color: #cbd5e1; border: 1px solid #334155; border-radius: 4px; padding: 2px; font-weight: bold; }"
            "QPushButton:hover { background-color: #334155; }"
            "QPushButton:disabled { background-color: #0f172a; }"
        )
        self.update_price_btn.clicked.connect(self._on_update_stop_price)
        
        self.stop_sl_spin = QSpinBox()
        self.stop_sl_spin.setRange(0, 100000)
        self.stop_sl_spin.setSingleStep(10)
        self.stop_sl_spin.valueChanged.connect(self._update_stop_lbls)
        
        self.stop_tp_spin = QSpinBox()
        self.stop_tp_spin.setRange(0, 100000)
        self.stop_tp_spin.setSingleStep(10)
        self.stop_tp_spin.valueChanged.connect(self._update_stop_lbls)
        
        # Stop dynamic labels for SL/TP values
        self.stop_sl_label = QLabel("Bez SL")
        self.stop_tp_label = QLabel("Bez TP")
        self.stop_sl_label.setStyleSheet("color: #94a3b8; font-size: 10px;")
        self.stop_tp_label.setStyleSheet("color: #94a3b8; font-size: 10px;")
        
        # Timeframe for Stop orders
        lbl_stop_tf = QLabel("Komentář (Timeframe)")
        lbl_stop_tf.setStyleSheet("font-weight: bold; font-size: 11px;")
        
        stop_tf_container = QWidget()
        stop_tf_layout = QHBoxLayout(stop_tf_container)
        stop_tf_layout.setContentsMargins(0, 0, 0, 0)
        stop_tf_layout.setSpacing(4)
        
        self.stop_tf_group = QButtonGroup(self)
        self.stop_tf_buttons = {}
        for tf in ["M1", "M5", "M15", "M30", "H1"]:
            btn = QPushButton(tf)
            btn.setCheckable(True)
            btn.setStyleSheet(
                "QPushButton { background-color: #1e293b; color: #94a3b8; border: 1px solid #334155; border-radius: 4px; padding: 4px 8px; font-weight: bold; }"
                "QPushButton:checked { background-color: #3b82f6; color: white; border-color: #2563eb; }"
                "QPushButton:hover { background-color: #334155; color: #f1f5f9; }"
            )
            self.stop_tf_group.addButton(btn)
            stop_tf_layout.addWidget(btn)
            self.stop_tf_buttons[tf] = btn
            
        self.stop_tf_buttons["M15"].setChecked(True)
        
        # Send button
        self.place_stop_btn = QPushButton("Odeslat STOP")
        self.place_stop_btn.setStyleSheet(
            "QPushButton { background-color: #4f46e5; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px; border: none; }"
            "QPushButton:hover { background-color: #4338ca; }"
            "QPushButton:disabled { background-color: #9ca3af; }"
        )
        self.place_stop_btn.clicked.connect(self._on_place_stop)
        
        # Grid layout assembly
        stop_grid.addWidget(lbl_stop_side, 0, 0)
        stop_grid.addWidget(self.stop_side_combo, 1, 0)
        
        stop_grid.addWidget(lbl_stop_price, 0, 1)
        
        # Horizontal layout for price input and update button
        price_lay = QHBoxLayout()
        price_lay.setContentsMargins(0, 0, 0, 0)
        price_lay.setSpacing(4)
        price_lay.addWidget(self.stop_price_spin, 1)
        price_lay.addWidget(self.update_price_btn)
        stop_grid.addLayout(price_lay, 1, 1)
        
        stop_grid.addWidget(lbl_stop_sl, 0, 2)
        stop_grid.addWidget(self.stop_sl_spin, 1, 2)
        stop_grid.addWidget(self.stop_sl_label, 2, 2)
        
        stop_grid.addWidget(lbl_stop_tp, 0, 3)
        stop_grid.addWidget(self.stop_tp_spin, 1, 3)
        stop_grid.addWidget(self.stop_tp_label, 2, 3)
        
        # New Timeframe Row
        stop_grid.addWidget(lbl_stop_tf, 3, 0, 1, 3)
        stop_grid.addWidget(stop_tf_container, 4, 0, 1, 4)
        
        # Send Button in Column 4, spanning rows 3-4 next to TF buttons
        stop_grid.addWidget(self.place_stop_btn, 3, 4, 2, 1)
        
        root.addWidget(stop_box)

        root.addStretch(1)

    # -------------------------------------------------------- params I/O
    def _load_params(self) -> None:
        self.count_spin.setValue(int(self._params.get("position_count", 1)))
        self.lot_spin.setValue(float(self._params.get("lot_size", 0.01)))
        self.sl_spin.setValue(int(self._params.get("sl", 200)))
        self.tp_spin.setValue(int(self._params.get("tp", 400)))
        self.dev_spin.setValue(int(self._params.get("deviation", 20)))
        self._update_sl_tp_labels()

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

    def _on_save_defaults(self) -> None:
        params = self._current_params()
        self._params = params
        self.params_changed.emit(self._symbol, params)

    def _emit_action(self, action: str) -> None:
        params = {"symbol": self._symbol}
        if action in ("buy", "sell"):
            params.update(self._current_params())
            checked_btn = self.tf_group.checkedButton()
            if checked_btn:
                params["comment"] = checked_btn.text()
        elif action == "close_symbol":
            params["symbol"] = self._symbol
        # close_all, close_profitable: nepotřebuje symbol
        self.action_requested.emit(action, params)

    def _close_single_position(self, ticket: int) -> None:
        self.action_requested.emit("close_ticket", {"ticket": ticket})

    def _on_update_stop_price(self) -> None:
        tick = self._last_tick
        if not tick:
            return
        is_buy = "BUY" in self.stop_side_combo.currentText()
        price = tick["ask"] if is_buy else tick["bid"]
        self.stop_price_spin.setValue(price)

    def _update_stop_lbls(self) -> None:
        entry = self.stop_price_spin.value()
        sl_pts = self.stop_sl_spin.value()
        tp_pts = self.stop_tp_spin.value()
        
        point = getattr(self, "_point", 0.00001)
        digits = getattr(self, "_digits", 5)
        tick_value = getattr(self, "_tick_value", None)
        tick_size = getattr(self, "_tick_size", None)
        lot_size = self.lot_spin.value()
        
        is_buy = "BUY" in self.stop_side_combo.currentText()
        
        def get_money_str(pts: int) -> str:
            if pts <= 0 or not tick_value or not tick_size or tick_size == 0:
                return ""
            val = (pts * point / tick_size) * tick_value * lot_size
            return f" (~ {val:.2f} USD)"
            
        sl_money = get_money_str(sl_pts)
        tp_money = get_money_str(tp_pts)
        
        if sl_pts > 0:
            sl_price = (entry - sl_pts * point) if is_buy else (entry + sl_pts * point)
            self.stop_sl_label.setText(f"Cena: {sl_price:.{digits}f}{sl_money}")
        else:
            self.stop_sl_label.setText("Bez SL")
            
        if tp_pts > 0:
            tp_price = (entry + tp_pts * point) if is_buy else (entry - tp_pts * point)
            self.stop_tp_label.setText(f"Cena: {tp_price:.{digits}f}{tp_money}")
        else:
            self.stop_tp_label.setText("Bez TP")

    def _on_place_stop(self) -> None:
        params = {
            "symbol": self._symbol,
            "side": "BUY_STOP" if "BUY" in self.stop_side_combo.currentText() else "SELL_STOP",
            "lot_size": self.lot_spin.value(),
            "price": self.stop_price_spin.value(),
            "deviation": self.dev_spin.value(),
        }
        
        entry = self.stop_price_spin.value()
        sl_pts = self.stop_sl_spin.value()
        tp_pts = self.stop_tp_spin.value()
        point = getattr(self, "_point", 0.00001)
        is_buy = params["side"] == "BUY_STOP"
        
        params["sl"] = (entry - sl_pts * point) if (sl_pts > 0 and is_buy) else ((entry + sl_pts * point) if sl_pts > 0 else 0.0)
        params["tp"] = (entry + tp_pts * point) if (tp_pts > 0 and is_buy) else ((entry - tp_pts * point) if tp_pts > 0 else 0.0)
        
        checked_btn = self.stop_tf_group.checkedButton()
        if checked_btn:
            params["comment"] = checked_btn.text()
            
        self.action_requested.emit("place_stop", params)

    # ------------------------------------------------------- live updates
    def _update_sl_tp_labels(self) -> None:
        tick = self._last_tick
        if not tick:
            return
            
        sl_pts = self.sl_spin.value()
        tp_pts = self.tp_spin.value()
        
        # BUY orders open at Ask. SL below Ask, TP above Ask.
        # SELL orders open at Bid. SL above Bid, TP below Bid.
        ask = tick["ask"]
        bid = tick["bid"]
        point = getattr(self, "_point", 0.00001)
        digits = getattr(self, "_digits", 5)
        tick_value = getattr(self, "_tick_value", None)
        tick_size = getattr(self, "_tick_size", None)
        lot_size = self.lot_spin.value()

        def get_money_str(pts: int) -> str:
            if pts <= 0 or not tick_value or not tick_size or tick_size == 0:
                return ""
            val = (pts * point / tick_size) * tick_value * lot_size
            return f" (~ {val:.2f} USD)"
        
        sl_money = get_money_str(sl_pts)
        tp_money = get_money_str(tp_pts)
        
        if sl_pts > 0:
            buy_sl = ask - sl_pts * point
            sell_sl = bid + sl_pts * point
            self.buy_sl_label.setText(f"BUY SL: {buy_sl:.{digits}f}{sl_money}")
            self.sell_sl_label.setText(f"SELL SL: {sell_sl:.{digits}f}{sl_money}")
        else:
            self.buy_sl_label.setText("BUY SL: Bez SL")
            self.sell_sl_label.setText("SELL SL: Bez SL")
            
        if tp_pts > 0:
            buy_tp = ask + tp_pts * point
            sell_tp = bid - tp_pts * point
            self.buy_tp_label.setText(f"BUY TP: {buy_tp:.{digits}f}{tp_money}")
            self.sell_tp_label.setText(f"SELL TP: {sell_tp:.{digits}f}{tp_money}")
        else:
            self.buy_tp_label.setText("BUY TP: Bez TP")
            self.sell_tp_label.setText("SELL TP: Bez TP")

    def update_tick(self, tick: dict | None) -> None:
        self._last_tick = tick
        if tick is None:
            self.price_label.setText("Bid: —  |  Ask: —")
            self.buy_sl_label.setText("BUY SL: —")
            self.sell_sl_label.setText("SELL SL: —")
            self.buy_tp_label.setText("BUY TP: —")
            self.sell_tp_label.setText("SELL TP: —")
            return
        
        self.price_label.setText(
            f"Bid: {tick['bid']:.5f}  |  Ask: {tick['ask']:.5f}"
        )
        
        # Fetch point and digits if not done yet
        if not self._point_fetched:
            import mt5_service
            info = mt5_service.get_symbol_info(self._symbol)
            if info:
                self._point = info["point"]
                self._digits = info["digits"]
                self._tick_value = info["tick_value"]
                self._tick_size = info["tick_size"]
                self._point_fetched = True
                
                # Inicializace stop ceny
                if self.stop_price_spin.value() == 0.0:
                    self.stop_price_spin.setValue(tick["ask"])
                self.stop_price_spin.setDecimals(self._digits)
                self.stop_price_spin.setSingleStep(self._point * 10)
                
        self._update_sl_tp_labels()
        self._update_stop_lbls()

    def update_positions(self, positions: list[dict]) -> None:
        self.table.setRowCount(0)
        total_pl = 0.0
        for p in positions:
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            # Ticket
            ticket_item = QTableWidgetItem(str(p["ticket"]))
            ticket_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, ticket_item)
            
            # Symbol
            symbol_item = QTableWidgetItem(p["symbol"])
            symbol_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, symbol_item)
            
            # Type
            type_item = QTableWidgetItem(p["type"])
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            type_item.setForeground(
                Qt.GlobalColor.green if p["type"] == "BUY" else Qt.GlobalColor.red
            )
            self.table.setItem(row, 2, type_item)
            
            # Volume
            vol_item = QTableWidgetItem(f"{p['volume']:.2f}")
            vol_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, vol_item)
            
            # Open Price
            price_item = QTableWidgetItem(f"{p['price_open']:.5f}")
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, price_item)

            # Profit / Loss
            pl_item = QTableWidgetItem(f"{p['profit']:.2f}")
            pl_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            pl_color = Qt.GlobalColor.green if p["profit"] >= 0 else Qt.GlobalColor.red
            pl_item.setForeground(pl_color)
            self.table.setItem(row, 5, pl_item)

            # Magic number
            magic_item = QTableWidgetItem(str(p["magic"]))
            magic_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 6, magic_item)
            
            # Action: Close (❌) button
            close_btn = QPushButton("❌")
            close_btn.setToolTip("Zavřít tuto pozici")
            close_btn.setStyleSheet(
                "QPushButton { background-color: transparent; border: none; font-weight: bold; font-size: 11px; padding: 2px; }"
                "QPushButton:hover { background-color: #fee2e2; border-radius: 4px; }"
            )
            ticket = p["ticket"]
            close_btn.clicked.connect(lambda checked, t=ticket: self._close_single_position(t))
            self.table.setCellWidget(row, 7, close_btn)
            
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
        for btn in (self.buy_btn, self.sell_btn, self.close_btn, self.close_profit_btn, self.close_all_btn, self.save_defaults_btn, self.place_stop_btn, self.update_price_btn):
            btn.setEnabled(not busy)

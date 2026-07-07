# -*- coding: utf-8 -*-
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
    @staticmethod
    def _spin_style() -> str:
        return (
            "QSpinBox, QDoubleSpinBox {"
            "  background:#1e293b; color:#f8fafc; border:1px solid #334155;"
            "  border-radius:3px; padding:1px 4px; max-height:22px; font-size:11px;"
            "}"
            "QSpinBox:focus, QDoubleSpinBox:focus { border-color:#38bdf8; }"
        )

    @staticmethod
    def _tf_btn_style() -> str:
        return (
            "QPushButton { background:#1e293b; color:#64748b; border:1px solid #334155;"
            "  border-radius:3px; padding:1px 5px; font-size:9px; font-weight:bold; min-width:26px; max-height:20px; }"
            "QPushButton:checked { background:#3b82f6; color:white; border-color:#2563eb; }"
            "QPushButton:hover { background:#334155; color:#e2e8f0; }"
        )

    @staticmethod
    def _label_style() -> str:
        return "color:#64748b; font-size:10px; font-weight:bold;"

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 4, 6, 4)
        root.setSpacing(6)

        # ── HEADER: symbol name + live price ──────────────────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(4)
        title = QLabel(self._symbol)
        title.setStyleSheet("font-size:15px; font-weight:bold; color:#f8fafc;")
        self.price_label = QLabel("— / —")
        self.price_label.setStyleSheet("font-size:12px; font-weight:bold; color:#38bdf8;")
        self.price_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        hdr.addWidget(title)
        hdr.addStretch()
        hdr.addWidget(self.price_label)
        root.addLayout(hdr)

        # ── PARAMS SECTION ────────────────────────────────────────────────
        # Row 1: Pozic, Lot, Dev, TF buttons + Save defaults
        params_grid = QGridLayout()
        params_grid.setSpacing(4)
        params_grid.setContentsMargins(0, 0, 0, 0)

        def make_lbl(text: str) -> QLabel:
            l = QLabel(text)
            l.setStyleSheet(self._label_style())
            return l

        spin_ss = self._spin_style()

        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 100)
        self.count_spin.setStyleSheet(spin_ss)
        self.count_spin.setFixedWidth(52)
        self.count_spin.setFixedHeight(22)

        self.lot_spin = QDoubleSpinBox()
        self.lot_spin.setDecimals(2)
        self.lot_spin.setRange(0.01, 1000.0)
        self.lot_spin.setSingleStep(0.01)
        self.lot_spin.setStyleSheet(spin_ss)
        self.lot_spin.setFixedWidth(62)
        self.lot_spin.setFixedHeight(22)
        self.lot_spin.valueChanged.connect(self._update_sl_tp_labels)

        self.dev_spin = QSpinBox()
        self.dev_spin.setRange(0, 10000)
        self.dev_spin.setSingleStep(5)
        self.dev_spin.setStyleSheet(spin_ss)
        self.dev_spin.setFixedWidth(52)
        self.dev_spin.setFixedHeight(22)
        self.dev_spin.setToolTip("Slippage v bodech")

        # Save default params button
        self.save_defaults_btn = QPushButton("💾")
        self.save_defaults_btn.setToolTip("Uložit jako výchozí")
        self.save_defaults_btn.setFixedSize(20, 20)
        self.save_defaults_btn.setStyleSheet(
            "QPushButton { background:#3b82f6; border:none; border-radius:3px; font-size:10px; padding:0px; }"
            "QPushButton:hover { background:#2563eb; }"
        )
        self.save_defaults_btn.clicked.connect(self._on_save_defaults)

        # Timeframe comment buttons
        tf_container = QWidget()
        tf_layout = QHBoxLayout(tf_container)
        tf_layout.setContentsMargins(0, 0, 0, 0)
        tf_layout.setSpacing(3)
        self.tf_group = QButtonGroup(self)
        self.tf_buttons = {}
        tf_ss = self._tf_btn_style()
        for tf in ["M1", "M5", "M15", "M30", "H1"]:
            btn = QPushButton(tf)
            btn.setCheckable(True)
            btn.setStyleSheet(tf_ss)
            btn.setFixedHeight(20)
            self.tf_group.addButton(btn)
            tf_layout.addWidget(btn)
            self.tf_buttons[tf] = btn
        self.tf_buttons["M15"].setChecked(True)

        params_grid.addWidget(make_lbl("Pozic"), 0, 0)
        params_grid.addWidget(make_lbl("Lot"), 0, 1)
        params_grid.addWidget(make_lbl("Dev"), 0, 2)
        params_grid.addWidget(make_lbl("TF (komentář)"), 0, 3)
        params_grid.addWidget(self.count_spin, 1, 0)
        params_grid.addWidget(self.lot_spin, 1, 1)
        params_grid.addWidget(self.dev_spin, 1, 2)
        params_grid.addWidget(tf_container, 1, 3)
        params_grid.addWidget(self.save_defaults_btn, 1, 4)

        root.addLayout(params_grid)

        # Row 2 (New Row): SL and TP fields on their own line with a small gap
        sl_tp_row = QHBoxLayout()
        sl_tp_row.setSpacing(12)
        sl_tp_row.setContentsMargins(0, 0, 0, 0)

        # SL inputs/labels layout
        sl_lay = QHBoxLayout()
        sl_lay.setSpacing(4)
        sl_lay.setContentsMargins(0, 0, 0, 0)
        self.sl_spin = QSpinBox()
        self.sl_spin.setRange(0, 100000)
        self.sl_spin.setSingleStep(10)
        self.sl_spin.setStyleSheet(spin_ss)
        self.sl_spin.setFixedWidth(65)
        self.sl_spin.setFixedHeight(22)
        self.sl_spin.valueChanged.connect(self._update_sl_tp_labels)

        self.sl_usd_label = QLabel("Bez SL")
        self.sl_usd_label.setStyleSheet("color:#ef4444; font-size:12px; font-weight:bold;")
        self.sl_price_label = QLabel("")
        self.sl_price_label.setStyleSheet("color:#64748b; font-size:9px;")

        sl_lay.addWidget(make_lbl("SL (body):"))
        sl_lay.addWidget(self.sl_spin)
        sl_lay.addWidget(self.sl_usd_label)
        sl_lay.addWidget(self.sl_price_label)

        # TP inputs/labels layout
        tp_lay = QHBoxLayout()
        tp_lay.setSpacing(4)
        tp_lay.setContentsMargins(0, 0, 0, 0)
        self.tp_spin = QSpinBox()
        self.tp_spin.setRange(0, 100000)
        self.tp_spin.setSingleStep(10)
        self.tp_spin.setStyleSheet(spin_ss)
        self.tp_spin.setFixedWidth(65)
        self.tp_spin.setFixedHeight(22)
        self.tp_spin.valueChanged.connect(self._update_sl_tp_labels)

        self.tp_usd_label = QLabel("Bez TP")
        self.tp_usd_label.setStyleSheet("color:#22c55e; font-size:12px; font-weight:bold;")
        self.tp_price_label = QLabel("")
        self.tp_price_label.setStyleSheet("color:#64748b; font-size:9px;")

        tp_lay.addWidget(make_lbl("TP (body):"))
        tp_lay.addWidget(self.tp_spin)
        tp_lay.addWidget(self.tp_usd_label)
        tp_lay.addWidget(self.tp_price_label)

        sl_tp_row.addLayout(sl_lay)
        sl_tp_row.addLayout(tp_lay)
        sl_tp_row.addStretch()

        root.addLayout(sl_tp_row)

        # Subtle separator
        sep1 = QLabel()
        sep1.setFixedHeight(1)
        sep1.setStyleSheet("background:#1e293b;")
        root.addWidget(sep1)

        # ── BUY / SELL BUTTONS ────────────────────────────────────────────
        buy_sell = QHBoxLayout()
        buy_sell.setSpacing(5)
        buy_sell.setContentsMargins(0, 0, 0, 0)

        self.buy_btn = QPushButton("▲  BUY")
        self.buy_btn.setFixedHeight(34)
        self.buy_btn.setStyleSheet(
            "QPushButton { background:#15803d; border:1px solid #22c55e; color:white;"
            "  font-size:13px; font-weight:bold; border-radius:4px; }"
            "QPushButton:hover { background:#166534; }"
            "QPushButton:disabled { background:#1e293b; color:#334155; border-color:#1e293b; }"
        )
        self.buy_btn.clicked.connect(lambda: self._emit_action("buy"))

        self.sell_btn = QPushButton("▼  SELL")
        self.sell_btn.setFixedHeight(34)
        self.sell_btn.setStyleSheet(
            "QPushButton { background:#b91c1c; border:1px solid #ef4444; color:white;"
            "  font-size:13px; font-weight:bold; border-radius:4px; }"
            "QPushButton:hover { background:#991b1b; }"
            "QPushButton:disabled { background:#1e293b; color:#334155; border-color:#1e293b; }"
        )
        self.sell_btn.clicked.connect(lambda: self._emit_action("sell"))

        buy_sell.addWidget(self.buy_btn, 1)
        buy_sell.addWidget(self.sell_btn, 1)
        root.addLayout(buy_sell)

        # ── CLOSE BUTTONS (compact row) ───────────────────────────────────
        close_row = QHBoxLayout()
        close_row.setSpacing(4)
        close_row.setContentsMargins(0, 0, 0, 0)

        def close_btn_factory(text: str, bg: str, border: str) -> QPushButton:
            b = QPushButton(text)
            b.setFixedHeight(22)
            b.setStyleSheet(
                f"QPushButton {{ background:{bg}; border:1px solid {border}; color:white;"
                f"  font-size:9px; font-weight:bold; border-radius:3px; }}"
                f"QPushButton:hover {{ background:{border}; }}"
                f"QPushButton:disabled {{ background:#1e293b; color:#334155; border-color:#1e293b; }}"
            )
            return b

        self.close_btn = close_btn_factory("CLOSE PÁR", "#1e293b", "#475569")
        self.close_profit_btn = close_btn_factory("💰 ZISK", "#0f766e", "#0d9488")
        self.close_all_btn = close_btn_factory("⚠️ ALL", "#7f1d1d", "#ef4444")

        self.close_btn.clicked.connect(lambda: self._emit_action("close_symbol"))
        self.close_profit_btn.clicked.connect(lambda: self._emit_action("close_profitable"))
        self.close_all_btn.clicked.connect(lambda: self._emit_action("close_all"))

        close_row.addWidget(self.close_btn, 2)
        close_row.addWidget(self.close_profit_btn, 1)
        close_row.addWidget(self.close_all_btn, 1)
        root.addLayout(close_row)

        # ── POSITIONS TABLE (Showing Sym, TF, @Price, P/L, ❌) ────────────
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Sym", "TF", "@Price", "P/L", "❌"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents) # Sym
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents) # TF (Comment)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)          # @Price (stretched)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents) # P/L
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)            # Action close
        h.resizeSection(4, 24)
        self.table.verticalHeader().setDefaultSectionSize(20)
        self.table.setMaximumHeight(130)
        self.table.setStyleSheet(
            "QTableWidget { font-size:10px; }"
            "QHeaderView::section { font-size:9px; padding:2px; }"
        )
        root.addWidget(self.table)

        self.positions_summary = QLabel("Žádné otevřené pozice.")
        self.positions_summary.setStyleSheet("color:#475569; font-size:9px;")
        root.addWidget(self.positions_summary)

        # Separator
        sep2 = QLabel()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background:#1e293b;")
        root.addWidget(sep2)

        # ── STOP ORDERS SECTION (Symmetric & Compact layout) ──────────────
        stop_lbl = QLabel("STOP PŘÍKAZY")
        stop_lbl.setStyleSheet("color:#38bdf8; font-size:9px; font-weight:bold; letter-spacing:1px;")
        root.addWidget(stop_lbl)

        # Row 1: Typ Stopu, Vstupní cena inputs
        stop_grid = QGridLayout()
        stop_grid.setSpacing(4)
        stop_grid.setContentsMargins(0, 0, 0, 0)

        stop_type_lay = QHBoxLayout()
        stop_type_lay.setContentsMargins(0, 0, 0, 0)
        stop_type_lay.setSpacing(3)

        self.buy_stop_btn = QPushButton("BUY STOP")
        self.buy_stop_btn.setCheckable(True)
        self.buy_stop_btn.setChecked(True)
        self.buy_stop_btn.setFixedHeight(22)
        self.buy_stop_btn.setStyleSheet(
            "QPushButton { background:#1e293b; color:#64748b; border:1px solid #334155; border-radius:3px; font-size:10px; font-weight:bold; padding:0 8px; }"
            "QPushButton:checked { background:#15803d; color:white; border-color:#22c55e; }"
            "QPushButton:hover { background:#334155; }"
        )

        self.sell_stop_btn = QPushButton("SELL STOP")
        self.sell_stop_btn.setCheckable(True)
        self.sell_stop_btn.setFixedHeight(22)
        self.sell_stop_btn.setStyleSheet(
            "QPushButton { background:#1e293b; color:#64748b; border:1px solid #334155; border-radius:3px; font-size:10px; font-weight:bold; padding:0 8px; }"
            "QPushButton:checked { background:#b91c1c; color:white; border-color:#ef4444; }"
            "QPushButton:hover { background:#334155; }"
        )

        self.stop_type_group = QButtonGroup(self)
        self.stop_type_group.addButton(self.buy_stop_btn)
        self.stop_type_group.addButton(self.sell_stop_btn)
        self.stop_type_group.buttonClicked.connect(self._update_stop_lbls)
        stop_type_lay.addWidget(self.buy_stop_btn)
        stop_type_lay.addWidget(self.sell_stop_btn)

        stop_price_lay = QHBoxLayout()
        stop_price_lay.setContentsMargins(0, 0, 0, 0)
        stop_price_lay.setSpacing(3)

        self.stop_price_spin = QDoubleSpinBox()
        self.stop_price_spin.setRange(0.0, 1_000_000.0)
        self.stop_price_spin.setDecimals(5)
        self.stop_price_spin.setSingleStep(0.1)
        self.stop_price_spin.setStyleSheet(spin_ss)
        self.stop_price_spin.setFixedHeight(22)
        self.stop_price_spin.valueChanged.connect(self._update_stop_lbls)

        self.update_price_btn = QPushButton("🔄")
        self.update_price_btn.setToolTip("Nastavit aktuální tržní cenu")
        self.update_price_btn.setFixedSize(22, 22)
        self.update_price_btn.setStyleSheet(
            "QPushButton { background:#1e293b; color:#94a3b8; border:1px solid #334155; border-radius:3px; font-size:11px; }"
            "QPushButton:hover { background:#334155; }"
        )
        self.update_price_btn.clicked.connect(self._on_update_stop_price)
        stop_price_lay.addWidget(self.stop_price_spin, 1)
        stop_price_lay.addWidget(self.update_price_btn)

        stop_grid.addWidget(make_lbl("Typ Stopu"), 0, 0)
        stop_grid.addWidget(make_lbl("Vstupní cena"), 0, 1)
        stop_grid.addLayout(stop_type_lay, 1, 0)
        stop_grid.addLayout(stop_price_lay, 1, 1)

        root.addLayout(stop_grid)

        # Row 2: SL and TP inputs on a NEW row for Stop Orders
        stop_sl_tp_row = QHBoxLayout()
        stop_sl_tp_row.setSpacing(12)
        stop_sl_tp_row.setContentsMargins(0, 0, 0, 0)

        # Stop SL layout
        stop_sl_lay = QHBoxLayout()
        stop_sl_lay.setSpacing(4)
        stop_sl_lay.setContentsMargins(0, 0, 0, 0)
        self.stop_sl_spin = QSpinBox()
        self.stop_sl_spin.setRange(0, 100000)
        self.stop_sl_spin.setSingleStep(10)
        self.stop_sl_spin.setStyleSheet(spin_ss)
        self.stop_sl_spin.setFixedWidth(65)
        self.stop_sl_spin.setFixedHeight(22)
        self.stop_sl_spin.valueChanged.connect(self._update_stop_lbls)

        self.stop_sl_usd_label = QLabel("Bez SL")
        self.stop_sl_usd_label.setStyleSheet("color:#ef4444; font-size:12px; font-weight:bold;")
        self.stop_sl_price_label = QLabel("")
        self.stop_sl_price_label.setStyleSheet("color:#64748b; font-size:9px;")

        stop_sl_lay.addWidget(make_lbl("SL (body):"))
        stop_sl_lay.addWidget(self.stop_sl_spin)
        stop_sl_lay.addWidget(self.stop_sl_usd_label)
        stop_sl_lay.addWidget(self.stop_sl_price_label)

        # Stop TP layout
        stop_tp_lay = QHBoxLayout()
        stop_tp_lay.setSpacing(4)
        stop_tp_lay.setContentsMargins(0, 0, 0, 0)
        self.stop_tp_spin = QSpinBox()
        self.stop_tp_spin.setRange(0, 100000)
        self.stop_tp_spin.setSingleStep(10)
        self.stop_tp_spin.setStyleSheet(spin_ss)
        self.stop_tp_spin.setFixedWidth(65)
        self.stop_tp_spin.setFixedHeight(22)
        self.stop_tp_spin.valueChanged.connect(self._update_stop_lbls)

        self.stop_tp_usd_label = QLabel("Bez TP")
        self.stop_tp_usd_label.setStyleSheet("color:#22c55e; font-size:12px; font-weight:bold;")
        self.stop_tp_price_label = QLabel("")
        self.stop_tp_price_label.setStyleSheet("color:#64748b; font-size:9px;")

        stop_tp_lay.addWidget(make_lbl("TP (body):"))
        stop_tp_lay.addWidget(self.stop_tp_spin)
        stop_tp_lay.addWidget(self.stop_tp_usd_label)
        stop_tp_lay.addWidget(self.stop_tp_price_label)

        stop_sl_tp_row.addLayout(stop_sl_lay)
        stop_sl_tp_row.addLayout(stop_tp_lay)
        stop_sl_tp_row.addStretch()

        root.addLayout(stop_sl_tp_row)

        # Row 3: Stop Timeframe Selector & Place Button
        stop_action_row = QHBoxLayout()
        stop_action_row.setSpacing(4)
        stop_action_row.setContentsMargins(0, 0, 0, 0)

        # Timeframe comment buttons for Stop
        stop_tf_container = QWidget()
        stop_tf_layout = QHBoxLayout(stop_tf_container)
        stop_tf_layout.setContentsMargins(0, 0, 0, 0)
        stop_tf_layout.setSpacing(3)
        self.stop_tf_group = QButtonGroup(self)
        self.stop_tf_buttons = {}
        for tf in ["M1", "M5", "M15", "M30", "H1"]:
            btn = QPushButton(tf)
            btn.setCheckable(True)
            btn.setStyleSheet(tf_ss)
            btn.setFixedHeight(20)
            self.stop_tf_group.addButton(btn)
            stop_tf_layout.addWidget(btn)
            self.stop_tf_buttons[tf] = btn
        self.stop_tf_buttons["M15"].setChecked(True)

        self.place_stop_btn = QPushButton("▶  ODESLAT STOP")
        self.place_stop_btn.setFixedHeight(24)
        self.place_stop_btn.setStyleSheet(
            "QPushButton { background:#4338ca; border:1px solid #6366f1; color:white;"
            "  font-size:10px; font-weight:bold; border-radius:4px; padding:0 12px; }"
            "QPushButton:hover { background:#3730a3; }"
            "QPushButton:disabled { background:#1e293b; color:#334155; border-color:#1e293b; }"
        )
        self.place_stop_btn.clicked.connect(self._on_place_stop)

        stop_action_row.addWidget(make_lbl("TF (komentář):"))
        stop_action_row.addWidget(stop_tf_container)
        stop_action_row.addStretch()
        stop_action_row.addWidget(self.place_stop_btn)

        root.addLayout(stop_action_row)
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
            
            # Převod SL/TP z bodů na absolutní cenové hladiny před odesláním do MT5
            tick = self._last_tick
            if not tick:
                import mt5_service
                t = mt5_service.get_tick(self._symbol)
                if t:
                    tick = {"ask": t.ask, "bid": t.bid}
                    
            if tick:
                is_buy = action == "buy"
                entry_price = tick["ask"] if is_buy else tick["bid"]
                point = getattr(self, "_point", 0.00001)
                sl_pts = params["sl"]
                tp_pts = params["tp"]
                
                params["sl"] = (entry_price - sl_pts * point) if (sl_pts > 0 and is_buy) else ((entry_price + sl_pts * point) if sl_pts > 0 else 0.0)
                params["tp"] = (entry_price + tp_pts * point) if (tp_pts > 0 and is_buy) else ((entry_price - tp_pts * point) if tp_pts > 0 else 0.0)
            else:
                params["sl"] = 0.0
                params["tp"] = 0.0

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
        is_buy = self.buy_stop_btn.isChecked()
        price = tick["ask"] if is_buy else tick["bid"]
        self.stop_price_spin.setValue(price)

    def _update_stop_lbls(self, *args) -> None:
        entry = self.stop_price_spin.value()
        sl_pts = self.stop_sl_spin.value()
        tp_pts = self.stop_tp_spin.value()
        
        point = getattr(self, "_point", 0.00001)
        digits = getattr(self, "_digits", 5)
        tick_value = getattr(self, "_tick_value", None)
        tick_size = getattr(self, "_tick_size", None)
        lot_size = self.lot_spin.value()
        
        is_buy = self.buy_stop_btn.isChecked()
        
        if sl_pts > 0:
            if tick_value and tick_size and tick_size > 0:
                sl_usd = (sl_pts * point / tick_size) * tick_value * lot_size
                self.stop_sl_usd_label.setText(f"Risk: -{sl_usd:.2f} USD")
            else:
                self.stop_sl_usd_label.setText("Risk: -- USD")
            
            sl_price = (entry - sl_pts * point) if is_buy else (entry + sl_pts * point)
            self.stop_sl_price_label.setText(f"Cena: {sl_price:.{digits}f}")
        else:
            self.stop_sl_usd_label.setText("Bez SL")
            self.stop_sl_price_label.setText("")
            
        if tp_pts > 0:
            if tick_value and tick_size and tick_size > 0:
                tp_usd = (tp_pts * point / tick_size) * tick_value * lot_size
                self.stop_tp_usd_label.setText(f"Zisk: +{tp_usd:.2f} USD")
            else:
                self.stop_tp_usd_label.setText("Zisk: -- USD")
                
            tp_price = (entry + tp_pts * point) if is_buy else (entry - tp_pts * point)
            self.stop_tp_price_label.setText(f"Cena: {tp_price:.{digits}f}")
        else:
            self.stop_tp_usd_label.setText("Bez TP")
            self.stop_tp_price_label.setText("")

    def _on_place_stop(self) -> None:
        is_buy = self.buy_stop_btn.isChecked()
        params = {
            "symbol": self._symbol,
            "side": "BUY_STOP" if is_buy else "SELL_STOP",
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
        
        ask = tick["ask"]
        bid = tick["bid"]
        point = getattr(self, "_point", 0.00001)
        digits = getattr(self, "_digits", 5)
        tick_value = getattr(self, "_tick_value", None)
        tick_size = getattr(self, "_tick_size", None)
        lot_size = self.lot_spin.value()

        if sl_pts > 0:
            if tick_value and tick_size and tick_size > 0:
                sl_usd = (sl_pts * point / tick_size) * tick_value * lot_size
                self.sl_usd_label.setText(f"Risk: -{sl_usd:.2f} USD")
            else:
                self.sl_usd_label.setText("Risk: -- USD")
            buy_sl = ask - sl_pts * point
            sell_sl = bid + sl_pts * point
            self.sl_price_label.setText(f"B: {buy_sl:.{digits}f} | S: {sell_sl:.{digits}f}")
        else:
            self.sl_usd_label.setText("Bez SL")
            self.sl_price_label.setText("")
            
        if tp_pts > 0:
            if tick_value and tick_size and tick_size > 0:
                tp_usd = (tp_pts * point / tick_size) * tick_value * lot_size
                self.tp_usd_label.setText(f"Zisk: +{tp_usd:.2f} USD")
            else:
                self.tp_usd_label.setText("Zisk: -- USD")
            buy_tp = ask + tp_pts * point
            sell_tp = bid - tp_pts * point
            self.tp_price_label.setText(f"B: {buy_tp:.{digits}f} | S: {sell_tp:.{digits}f}")
        else:
            self.tp_usd_label.setText("Bez TP")
            self.tp_price_label.setText("")

    def update_tick(self, tick: dict | None) -> None:
        self._last_tick = tick
        if tick is None:
            self.price_label.setText("— / —")
            self.sl_usd_label.setText("Risk: —")
            self.sl_price_label.setText("")
            self.tp_usd_label.setText("Zisk: —")
            self.tp_price_label.setText("")
            return
        
        self.price_label.setText(
            f"Bid: {tick['bid']:.{self._digits}f}  |  Ask: {tick['ask']:.{self._digits}f}"
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
        
        # Omezíme pouze na páry z Quantum Advanced Multi-TF Matrix Screen tabulky
        allowed_symbols = {"XAUUSD", "EURUSD", "USDJPY", "EURJPY", "USDCAD", "GBPUSD", "GBPCHF", "AUDUSD"}
        filtered_positions = [p for p in positions if p["symbol"] in allowed_symbols]
        
        for p in filtered_positions:
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            # Symbol
            symbol_item = QTableWidgetItem(p["symbol"])
            symbol_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, symbol_item)
            
            # Timeframe (comment)
            comment_item = QTableWidgetItem(p.get("comment", ""))
            comment_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, comment_item)
            
            # @Price (open execution price colored by type)
            is_buy = p["type"] == "BUY"
            price_str = f"@ {p['price_open']:.2f}" if ("XAU" in p["symbol"] or "JPY" in p["symbol"]) else f"@ {p['price_open']:.5f}"
            price_item = QTableWidgetItem(price_str)
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            price_item.setForeground(
                Qt.GlobalColor.green if is_buy else Qt.GlobalColor.red
            )
            self.table.setItem(row, 2, price_item)
            
            # Profit / Loss
            pl_item = QTableWidgetItem(f"{p['profit']:.2f}")
            pl_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            pl_color = Qt.GlobalColor.green if p["profit"] >= 0 else Qt.GlobalColor.red
            pl_item.setForeground(pl_color)
            self.table.setItem(row, 3, pl_item)
            
            # Action: Close (❌) button
            close_btn = QPushButton("❌")
            close_btn.setToolTip("Zavřít tuto pozici")
            close_btn.setStyleSheet(
                "QPushButton { background-color: transparent; border: none; font-weight: bold; font-size: 11px; padding: 2px; }"
                "QPushButton:hover { background-color: #ef4444; border-radius: 4px; }"
            )
            ticket = p["ticket"]
            close_btn.clicked.connect(lambda checked, t=ticket: self._close_single_position(t))
            self.table.setCellWidget(row, 4, close_btn)
            
            total_pl += p["profit"]

        count = len(filtered_positions)
        if count == 0:
            self.positions_summary.setText("Žádné otevřené pozice.")
        else:
            self.positions_summary.setText(
                f"{count} pozic — celkové P/L: {total_pl:.2f}"
            )

    # -------------------------------------------------------- busy state
    def set_busy(self, busy: bool) -> None:
        """Při probíhající akci deaktivuje tlačítka (prevence dvojkliku)."""
        for btn in (self.buy_btn, self.sell_btn, self.close_btn, self.close_profit_btn, self.close_all_btn, self.save_defaults_btn, self.place_stop_btn, self.update_price_btn, self.buy_stop_btn, self.sell_stop_btn):
            btn.setEnabled(not busy)

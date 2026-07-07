# -*- coding: utf-8 -*-
"""Panel pro jeden symbol — vstupy parametrů, akční tlačítka, tabulka pozic.

Panel je soběstačný: dostane symbol a config, načte parametry, zobrazí live
cenu a pozice (přes signály z PollWorker předávané z MainWindow), a při
kliknutí na BUY/SELL/CLOSE/CLOSE ALL/CLOSE V ZISKU/ODESLAT STOP vysílá signál.

Vylepšení oproti původní verzi:
- Samostatný ``stop_lot_size`` (nezávislé riziko pro STOP příkazy).
- Sekce MARKET / STOP PŘÍKAZY / POZICE v QGroupBox pro vizuální hierarchii.
- Info řádek (Equity / Free margin / P/L páru) v hlavičce.
- Validace ``Invalid stops`` (retcode 10016): při SL/TP příliš blízko ceny
  se tlačítka deaktivují a UI uživatele varuje minimální vzdáleností.
- Validace lotu (min/max/step) na základě ``symbol_info``.
- Klávesové zkratky: Ctrl+B BUY, Ctrl+S SELL, Ctrl+Enter ODESLAT STOP.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QButtonGroup,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class SymbolPanel(QWidget):
    """UI pro jeden obchodovaný pár.

    Signály (vysílá MainWindow do ActionWorker):
        action_requested(str, dict) — (action, params)
        params_changed(str, dict) — (symbol, params) — pro uložení do configu
    """

    action_requested = pyqtSignal(str, dict)
    params_changed = pyqtSignal(str, dict)   # (symbol, params) — pro uložení do configu

    def __init__(self, symbol: str, params: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._symbol = symbol
        self._params = dict(params)
        self._last_tick: dict | None = None
        self._last_account: dict | None = None
        self._pair_pl: float = 0.0

        # Symbol info (lazy načteno při prvním ticku).
        self._point = 0.00001
        self._digits = 5
        self._tick_value = None
        self._tick_size = None
        self._stops_level = 0          # min. vzdálenost SL/TP od ceny (body)
        self._volume_min = 0.01
        self._volume_max = 1000.0
        self._volume_step = 0.01
        self._info_fetched = False

        self._build_ui()
        self._load_params()
        self._install_shortcuts()

    # --------------------------------------------------------------- styling
    @staticmethod
    def _spin_style() -> str:
        return (
            "QSpinBox, QDoubleSpinBox {"
            "  background:#1e293b; color:#f8fafc; border:1px solid #334155;"
            "  border-radius:3px; padding:1px 18px 1px 4px; max-height:22px; font-size:11px;"
            "}"
            "QSpinBox:focus, QDoubleSpinBox:focus { border-color:#38bdf8; }"
            "QSpinBox::up-button, QDoubleSpinBox::up-button {"
            "  subcontrol-origin: border; subcontrol-position: top right; width: 14px;"
            "  border-left: 1px solid #334155; border-bottom: 1px solid #334155; background: #1e293b;"
            "  border-top-right-radius: 3px;"
            "}"
            "QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover { background: #334155; }"
            "QSpinBox::down-button, QDoubleSpinBox::down-button {"
            "  subcontrol-origin: border; subcontrol-position: bottom right; width: 14px;"
            "  border-left: 1px solid #334155; background: #1e293b;"
            "  border-bottom-right-radius: 3px;"
            "}"
            "QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background: #334155; }"
            "QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {"
            "  width: 0; height: 0; border-left: 3px solid transparent; border-right: 3px solid transparent;"
            "  border-bottom: 4px solid #94a3b8;"
            "}"
            "QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {"
            "  width: 0; height: 0; border-left: 3px solid transparent; border-right: 3px solid transparent;"
            "  border-top: 4px solid #94a3b8;"
            "}"
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

    def _make_lbl(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(self._label_style())
        return l

    # ------------------------------------------------------------- tf builder
    def _make_tf_buttons(self, default: str = "M15") -> tuple[QWidget, QButtonGroup, dict[str, QPushButton]]:
        """Vytvoří skupinu checkable TF tlačítek (pro market i stop sekci)."""
        container = QWidget()
        lay = QHBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        group = QButtonGroup(self)
        buttons: dict[str, QPushButton] = {}
        ss = self._tf_btn_style()
        for tf in ["M1", "M5", "M15", "M30", "H1"]:
            btn = QPushButton(tf)
            btn.setCheckable(True)
            btn.setStyleSheet(ss)
            btn.setFixedHeight(20)
            group.addButton(btn)
            lay.addWidget(btn)
            buttons[tf] = btn
        buttons[default].setChecked(True)
        return container, group, buttons

    # --------------------------------------------------- sl/tp block builder
    def _make_sl_tp_block(self) -> dict[str, Any]:
        """Vytvoří jeden SL/TP blok (spinboxy + USD/price labely + layout).

        Vrací dict se všemi widgety a výsledným QHBoxLayout. Používá se 2×
        (market i stop sekce) — eliminuje duplikaci ~50 řádků.
        """
        spin_ss = self._spin_style()
        lay = QHBoxLayout()
        lay.setSpacing(4)
        lay.setContentsMargins(0, 0, 0, 0)

        sl_spin = QSpinBox()
        sl_spin.setRange(0, 100000)
        sl_spin.setSingleStep(10)
        sl_spin.setStyleSheet(spin_ss)
        sl_spin.setFixedWidth(75)
        sl_spin.setFixedHeight(22)

        sl_usd_label = QLabel("Bez SL")
        sl_usd_label.setStyleSheet("color:#ef4444; font-size:11px; font-weight:bold;")
        sl_price_label = QLabel("")
        sl_price_label.setStyleSheet("color:#64748b; font-size:9px;")

        tp_spin = QSpinBox()
        tp_spin.setRange(0, 100000)
        tp_spin.setSingleStep(10)
        tp_spin.setStyleSheet(spin_ss)
        tp_spin.setFixedWidth(75)
        tp_spin.setFixedHeight(22)

        tp_usd_label = QLabel("Bez TP")
        tp_usd_label.setStyleSheet("color:#22c55e; font-size:11px; font-weight:bold;")
        tp_price_label = QLabel("")
        tp_price_label.setStyleSheet("color:#64748b; font-size:9px;")

        # SL řádek
        sl_lay = QHBoxLayout()
        sl_lay.setSpacing(4)
        sl_lay.setContentsMargins(0, 0, 0, 0)
        sl_lay.addWidget(self._make_lbl("SL:"))
        sl_lay.addWidget(sl_spin)
        sl_lay.addWidget(sl_usd_label)
        sl_lay.addWidget(sl_price_label, 1)

        # TP řádek
        tp_lay = QHBoxLayout()
        tp_lay.setSpacing(4)
        tp_lay.setContentsMargins(0, 0, 0, 0)
        tp_lay.addWidget(self._make_lbl("TP:"))
        tp_lay.addWidget(tp_spin)
        tp_lay.addWidget(tp_usd_label)
        tp_lay.addWidget(tp_price_label, 1)

        wrap = QVBoxLayout()
        wrap.setContentsMargins(0, 0, 0, 0)
        wrap.setSpacing(2)
        wrap.addLayout(sl_lay)
        wrap.addLayout(tp_lay)

        return {
            "layout": wrap,
            "sl_spin": sl_spin, "sl_usd_label": sl_usd_label, "sl_price_label": sl_price_label,
            "tp_spin": tp_spin, "tp_usd_label": tp_usd_label, "tp_price_label": tp_price_label,
        }

    # ----------------------------------------------------------------- build
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 4, 6, 4)
        root.setSpacing(6)
        spin_ss = self._spin_style()

        # ── HEADER: symbol + live price + info řádek ─────────────────────
        hdr_top = QHBoxLayout()
        hdr_top.setSpacing(6)
        title = QLabel(self._symbol)
        title.setStyleSheet("font-size:16px; font-weight:bold; color:#f8fafc;")
        self.price_label = QLabel("— / —")
        self.price_label.setStyleSheet("font-size:12px; font-weight:bold; color:#38bdf8;")
        self.price_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        hdr_top.addWidget(title)
        hdr_top.addStretch()
        hdr_top.addWidget(self.price_label)
        root.addLayout(hdr_top)

        # Info řádek: Equity • Free • P/L pár
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color:#94a3b8; font-size:10px;")
        root.addWidget(self.info_label)

        # ════════════════════ MARKET sekce ═══════════════════════════════
        market_box = QGroupBox("MARKET")
        market_lay = QVBoxLayout(market_box)
        market_lay.setContentsMargins(8, 14, 8, 8)
        market_lay.setSpacing(4)

        # Row 1: Pozic, Lot, Dev, TF, Save
        params_grid = QGridLayout()
        params_grid.setSpacing(4)
        params_grid.setContentsMargins(0, 0, 0, 0)

        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 100)
        self.count_spin.setStyleSheet(spin_ss)
        self.count_spin.setFixedWidth(62)
        self.count_spin.setFixedHeight(22)

        self.lot_spin = QDoubleSpinBox()
        self.lot_spin.setDecimals(2)
        self.lot_spin.setRange(0.01, 1000.0)
        self.lot_spin.setSingleStep(0.01)
        self.lot_spin.setStyleSheet(spin_ss)
        self.lot_spin.setFixedWidth(64)
        self.lot_spin.setFixedHeight(22)
        self.lot_spin.valueChanged.connect(self._on_lot_changed)
        self.lot_spin.valueChanged.connect(self._update_sl_tp_labels)

        self.lot_hint_label = QLabel("")
        self.lot_hint_label.setStyleSheet("color:#f59e0b; font-size:9px;")
        self.lot_hint_label.setFixedHeight(12)

        self.dev_spin = QSpinBox()
        self.dev_spin.setRange(0, 10000)
        self.dev_spin.setSingleStep(5)
        self.dev_spin.setStyleSheet(spin_ss)
        self.dev_spin.setFixedWidth(62)
        self.dev_spin.setFixedHeight(22)
        self.dev_spin.setToolTip("Slippage v bodech")

        self.save_defaults_btn = QPushButton("📥")
        self.save_defaults_btn.setToolTip("Uložit jako výchozí")
        self.save_defaults_btn.setFixedSize(24, 24)
        self.save_defaults_btn.setStyleSheet(
            "QPushButton { background:#3b82f6; border:none; border-radius:3px; font-size:12px; padding:0px; }"
            "QPushButton:hover { background:#2563eb; }"
        )
        self.save_defaults_btn.clicked.connect(self._on_save_defaults)

        tf_container, self.tf_group, self.tf_buttons = self._make_tf_buttons()

        params_grid.addWidget(self._make_lbl("Pozic"), 0, 0)
        params_grid.addWidget(self._make_lbl("Lot"), 0, 1)
        params_grid.addWidget(self._make_lbl("Dev"), 0, 2)
        params_grid.addWidget(self._make_lbl("TF"), 0, 3)
        params_grid.addWidget(self.count_spin, 1, 0)
        params_grid.addWidget(self.lot_spin, 1, 1)
        params_grid.addWidget(self.dev_spin, 1, 2)
        params_grid.addWidget(tf_container, 1, 3)
        params_grid.addWidget(self.save_defaults_btn, 1, 4)
        market_lay.addLayout(params_grid)
        market_lay.addWidget(self.lot_hint_label)

        # SL/TP blok (market) — zde entry = ask/bid podle budoucí strany.
        mkt_block = self._make_sl_tp_block()
        self.sl_spin: QSpinBox = mkt_block["sl_spin"]
        self.sl_usd_label: QLabel = mkt_block["sl_usd_label"]
        self.sl_price_label: QLabel = mkt_block["sl_price_label"]
        self.tp_spin: QSpinBox = mkt_block["tp_spin"]
        self.tp_usd_label: QLabel = mkt_block["tp_usd_label"]
        self.tp_price_label: QLabel = mkt_block["tp_price_label"]
        self.sl_spin.valueChanged.connect(self._update_sl_tp_labels)
        self.tp_spin.valueChanged.connect(self._update_sl_tp_labels)
        market_lay.addLayout(mkt_block["layout"])

        # BUY / SELL
        buy_sell = QHBoxLayout()
        buy_sell.setSpacing(5)
        buy_sell.setContentsMargins(0, 2, 0, 0)
        self.buy_btn = QPushButton("▲  BUY")
        self.buy_btn.setFixedHeight(32)
        self.buy_btn.setStyleSheet(
            "QPushButton { background:#15803d; border:1px solid #22c55e; color:white;"
            "  font-size:13px; font-weight:bold; border-radius:4px; }"
            "QPushButton:hover { background:#166534; }"
            "QPushButton:disabled { background:#1e293b; color:#334155; border-color:#1e293b; }"
        )
        self.buy_btn.clicked.connect(lambda: self._emit_action("buy"))
        self.sell_btn = QPushButton("▼  SELL")
        self.sell_btn.setFixedHeight(32)
        self.sell_btn.setStyleSheet(
            "QPushButton { background:#b91c1c; border:1px solid #ef4444; color:white;"
            "  font-size:13px; font-weight:bold; border-radius:4px; }"
            "QPushButton:hover { background:#991b1b; }"
            "QPushButton:disabled { background:#1e293b; color:#334155; border-color:#1e293b; }"
        )
        self.sell_btn.clicked.connect(lambda: self._emit_action("sell"))
        buy_sell.addWidget(self.buy_btn, 1)
        buy_sell.addWidget(self.sell_btn, 1)
        market_lay.addLayout(buy_sell)

        # CLOSE tlačítka
        close_row = QHBoxLayout()
        close_row.setSpacing(4)
        close_row.setContentsMargins(0, 2, 0, 0)

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
        market_lay.addLayout(close_row)

        root.addWidget(market_box)

        # ════════════════════ STOP PŘÍKAZY sekce ═════════════════════════
        stop_box = QGroupBox("STOP PŘÍKAZY")
        stop_lay = QVBoxLayout(stop_box)
        stop_lay.setContentsMargins(8, 14, 8, 8)
        stop_lay.setSpacing(4)

        # Row 1: Typ stopu + Vstupní cena
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

        self.update_price_btn = QPushButton("🔃")
        self.update_price_btn.setToolTip("Nastavit aktuální tržní cenu")
        self.update_price_btn.setFixedSize(24, 24)
        self.update_price_btn.setStyleSheet(
            "QPushButton { background:#1e293b; color:#94a3b8; border:1px solid #334155; border-radius:3px; font-size:13px; }"
            "QPushButton:hover { background:#334155; }"
        )
        self.update_price_btn.clicked.connect(self._on_update_stop_price)
        stop_price_lay.addWidget(self.stop_price_spin, 1)
        stop_price_lay.addWidget(self.update_price_btn)

        stop_grid.addWidget(self._make_lbl("Typ stopu"), 0, 0)
        stop_grid.addWidget(self._make_lbl("Vstupní cena"), 0, 1)
        stop_grid.addLayout(stop_type_lay, 1, 0)
        stop_grid.addLayout(stop_price_lay, 1, 1)
        stop_lay.addLayout(stop_grid)

        # Row 2: STOP Lot (NOVÉ — nezávislý na market lotu)
        stop_lot_row = QHBoxLayout()
        stop_lot_row.setSpacing(4)
        stop_lot_row.setContentsMargins(0, 0, 0, 0)
        self.stop_lot_spin = QDoubleSpinBox()
        self.stop_lot_spin.setDecimals(2)
        self.stop_lot_spin.setRange(0.01, 1000.0)
        self.stop_lot_spin.setSingleStep(0.01)
        self.stop_lot_spin.setStyleSheet(spin_ss)
        self.stop_lot_spin.setFixedWidth(64)
        self.stop_lot_spin.setFixedHeight(22)
        self.stop_lot_spin.valueChanged.connect(self._on_stop_lot_changed)
        self.stop_lot_spin.valueChanged.connect(self._update_stop_lbls)
        self.stop_lot_hint_label = QLabel("")
        self.stop_lot_hint_label.setStyleSheet("color:#f59e0b; font-size:9px;")
        stop_lot_row.addWidget(self._make_lbl("Lot (STOP):"))
        stop_lot_row.addWidget(self.stop_lot_spin)
        stop_lot_row.addStretch()
        stop_lay.addLayout(stop_lot_row)
        stop_lay.addWidget(self.stop_lot_hint_label)

        # SL/TP blok (stop)
        stp_block = self._make_sl_tp_block()
        self.stop_sl_spin: QSpinBox = stp_block["sl_spin"]
        self.stop_sl_usd_label: QLabel = stp_block["sl_usd_label"]
        self.stop_sl_price_label: QLabel = stp_block["sl_price_label"]
        self.stop_tp_spin: QSpinBox = stp_block["tp_spin"]
        self.stop_tp_usd_label: QLabel = stp_block["tp_usd_label"]
        self.stop_tp_price_label: QLabel = stp_block["tp_price_label"]
        self.stop_sl_spin.valueChanged.connect(self._update_stop_lbls)
        self.stop_tp_spin.valueChanged.connect(self._update_stop_lbls)
        stop_lay.addLayout(stp_block["layout"])

        # Row: STOP TF + ODESLAT
        stop_action_row = QHBoxLayout()
        stop_action_row.setSpacing(4)
        stop_action_row.setContentsMargins(0, 2, 0, 0)
        stop_tf_container, self.stop_tf_group, self.stop_tf_buttons = self._make_tf_buttons()

        self.place_stop_btn = QPushButton("▶  ODESLAT STOP")
        self.place_stop_btn.setFixedHeight(24)
        self.place_stop_btn.setStyleSheet(
            "QPushButton { background:#4338ca; border:1px solid #6366f1; color:white;"
            "  font-size:10px; font-weight:bold; border-radius:4px; padding:0 12px; }"
            "QPushButton:hover { background:#3730a3; }"
            "QPushButton:disabled { background:#1e293b; color:#334155; border-color:#1e293b; }"
        )
        self.place_stop_btn.clicked.connect(self._on_place_stop)
        stop_action_row.addWidget(self._make_lbl("TF:"))
        stop_action_row.addWidget(stop_tf_container)
        stop_action_row.addStretch()
        stop_action_row.addWidget(self.place_stop_btn)
        stop_lay.addLayout(stop_action_row)

        root.addWidget(stop_box)

        # ════════════════════ POZICE sekce ═══════════════════════════════
        self.positions_box = QGroupBox("POZICE")
        pos_lay = QVBoxLayout(self.positions_box)
        pos_lay.setContentsMargins(8, 14, 8, 8)
        pos_lay.setSpacing(4)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Sym", "TF", "P/L", "@Price", "❌"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        h.resizeSection(4, 24)
        self.table.verticalHeader().setDefaultSectionSize(20)
        self.table.setMaximumHeight(140)
        self.table.setStyleSheet(
            "QTableWidget { font-size:10px; }"
            "QHeaderView::section { font-size:9px; padding:2px; }"
        )
        pos_lay.addWidget(self.table)

        self.positions_summary = QLabel("Žádné otevřené pozice.")
        self.positions_summary.setStyleSheet("color:#64748b; font-size:10px;")
        pos_lay.addWidget(self.positions_summary)

        root.addWidget(self.positions_box)
        root.addStretch(1)

    # ------------------------------------------------------ klávesové zkratky
    def _install_shortcuts(self) -> None:
        """Rychlé klávesy pro praxi: Ctrl+B BUY, Ctrl+S SELL, Ctrl+Enter STOP."""
        for seq, handler in (
            (QKeySequence("Ctrl+B"), lambda: self._emit_action("buy")),
            (QKeySequence("Ctrl+S"), lambda: self._emit_action("sell")),
            (QKeySequence("Ctrl+Return"), self._on_place_stop),
            (QKeySequence("Ctrl+R"), self._on_update_stop_price),
        ):
            sc = QShortcut(seq, self)
            sc.activated.connect(handler)

    # -------------------------------------------------------- params I/O
    def _load_params(self) -> None:
        self.count_spin.setValue(int(self._params.get("position_count", 1)))
        self.lot_spin.setValue(float(self._params.get("lot_size", 0.01)))
        self.stop_lot_spin.setValue(float(self._params.get("stop_lot_size", self._params.get("lot_size", 0.01))))
        self.sl_spin.setValue(int(self._params.get("sl", 200)))
        self.tp_spin.setValue(int(self._params.get("tp", 400)))
        self.dev_spin.setValue(int(self._params.get("deviation", 20)))
        self._update_sl_tp_labels()
        self._update_stop_lbls()

    def set_params(self, params: dict[str, Any]) -> None:
        """Aktualizuje vstupy zvenčí (např. po editaci configu)."""
        self._params = dict(params)
        self._load_params()

    def _current_params(self) -> dict[str, Any]:
        return {
            "position_count": self.count_spin.value(),
            "lot_size": self.lot_spin.value(),
            "stop_lot_size": self.stop_lot_spin.value(),
            "sl": self.sl_spin.value(),
            "tp": self.tp_spin.value(),
            "deviation": self.dev_spin.value(),
        }

    def _on_save_defaults(self) -> None:
        params = self._current_params()
        self._params = params
        self.params_changed.emit(self._symbol, params)

    # --------------------------------------------------------- lot validace
    def _check_lot(self, lot: float) -> tuple[bool, str]:
        """Ověří lot vůči volume_min/max/step. Vrací (ok, zpráva pro hint)."""
        if lot < self._volume_min:
            return False, f"⚠ Min lot: {self._volume_min:g}"
        if lot > self._volume_max:
            return False, f"⚠ Max lot: {self._volume_max:g}"
        if self._volume_step > 0:
            steps = round(lot / self._volume_step)
            nearest = round(steps * self._volume_step, 4)
            if abs(nearest - lot) > 1e-9:
                return True, f"Krok lotu {self._volume_step:g} → nejbližší {nearest:g}"
        return True, ""

    def _on_lot_changed(self) -> None:
        ok, msg = self._check_lot(self.lot_spin.value())
        self.lot_hint_label.setText("" if ok and not msg else (msg if ok else msg))
        self.lot_hint_label.setStyleSheet(
            "color:#f59e0b; font-size:9px;" if ok else "color:#ef4444; font-size:9px; font-weight:bold;"
        )

    def _on_stop_lot_changed(self) -> None:
        ok, msg = self._check_lot(self.stop_lot_spin.value())
        self.stop_lot_hint_label.setText("" if ok and not msg else msg)
        self.stop_lot_hint_label.setStyleSheet(
            "color:#f59e0b; font-size:9px;" if ok else "color:#ef4444; font-size:9px; font-weight:bold;"
        )

    # ---------------------------------------------------------- akce / emise
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
                point = self._point
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

    # ---------------------------------------- validace Invalid stops (10016)
    def _distance_ok(self, points: int) -> bool:
        """True, pokud je vzdálenost SL/TP (v bodech) nad minimálním stops_level.

        ``stops_level == 0`` znamená, že broker nemá omezení (vše projde).
        """
        if points <= 0:
            return True  # žádný stop → vždy OK
        if self._stops_level <= 0:
            return True
        return points >= self._stops_level

    def _set_market_buttons_blocked(self, blocked: bool, reason: str = "") -> None:
        """Povolí/zakáže BUY/SELL a ukáže důvod v tooltipu."""
        for btn in (self.buy_btn, self.sell_btn):
            btn.setEnabled(not blocked and not self._busy)
            btn.setToolTip(reason if blocked else "")

    def _set_stop_button_blocked(self, blocked: bool, reason: str = "") -> None:
        self.place_stop_btn.setEnabled(not blocked and not self._busy)
        self.place_stop_btn.setToolTip(reason if blocked else "")

    # ------------------------------------------------- market SL/TP labels
    def _update_sl_tp_labels(self, *args) -> None:
        tick = self._last_tick
        if not tick:
            return

        sl_pts = self.sl_spin.value()
        tp_pts = self.tp_spin.value()
        ask = tick["ask"]
        bid = tick["bid"]
        point = self._point
        digits = self._digits
        tick_value = self._tick_value
        tick_size = self._tick_size
        lot_size = self.lot_spin.value()

        # Validace stops_level — jeden důvod pro obě tlačítka (BLÍZKO SL nebo TP).
        sl_ok = self._distance_ok(sl_pts)
        tp_ok = self._distance_ok(tp_pts)
        blocked = not (sl_ok and tp_ok)
        if blocked:
            reason = f"SL/TP příliš blízko ceny (min: {self._stops_level} bodů)"
        else:
            reason = ""
        self._set_market_buttons_blocked(blocked, reason)

        if sl_pts > 0:
            if tick_value and tick_size and tick_size > 0:
                sl_usd = (sl_pts * point / tick_size) * tick_value * lot_size
                self.sl_usd_label.setText(f"-{sl_usd:.2f} USD")
            else:
                self.sl_usd_label.setText("-- USD")
            self.sl_usd_label.setStyleSheet(
                "color:#ef4444; font-size:11px; font-weight:bold;"
                if sl_ok else "color:#f59e0b; font-size:11px; font-weight:bold;"
            )
            buy_sl = ask - sl_pts * point
            sell_sl = bid + sl_pts * point
            self.sl_price_label.setText(
                f"B: {buy_sl:.{digits}f} | S: {sell_sl:.{digits}f}"
                if sl_ok else f"⚠ Min: {self._stops_level} bodů"
            )
            self.sl_price_label.setStyleSheet(
                "color:#64748b; font-size:9px;" if sl_ok else "color:#f59e0b; font-size:9px; font-weight:bold;"
            )
        else:
            self.sl_usd_label.setText("Bez SL")
            self.sl_usd_label.setStyleSheet("color:#ef4444; font-size:11px; font-weight:bold;")
            self.sl_price_label.setText("")

        if tp_pts > 0:
            if tick_value and tick_size and tick_size > 0:
                tp_usd = (tp_pts * point / tick_size) * tick_value * lot_size
                self.tp_usd_label.setText(f"+{tp_usd:.2f} USD")
            else:
                self.tp_usd_label.setText("-- USD")
            self.tp_usd_label.setStyleSheet(
                "color:#22c55e; font-size:11px; font-weight:bold;"
                if tp_ok else "color:#f59e0b; font-size:11px; font-weight:bold;"
            )
            buy_tp = ask + tp_pts * point
            sell_tp = bid - tp_pts * point
            self.tp_price_label.setText(
                f"B: {buy_tp:.{digits}f} | S: {sell_tp:.{digits}f}"
                if tp_ok else f"⚠ Min: {self._stops_level} bodů"
            )
            self.tp_price_label.setStyleSheet(
                "color:#64748b; font-size:9px;" if tp_ok else "color:#f59e0b; font-size:9px; font-weight:bold;"
            )
        else:
            self.tp_usd_label.setText("Bez TP")
            self.tp_usd_label.setStyleSheet("color:#22c55e; font-size:11px; font-weight:bold;")
            self.tp_price_label.setText("")

    # ---------------------------------------------------- stop SL/TP labels
    def _update_stop_lbls(self, *args) -> None:
        entry = self.stop_price_spin.value()
        sl_pts = self.stop_sl_spin.value()
        tp_pts = self.stop_tp_spin.value()

        point = self._point
        digits = self._digits
        tick_value = self._tick_value
        tick_size = self._tick_size
        lot_size = self.stop_lot_spin.value()
        is_buy = self.buy_stop_btn.isChecked()

        sl_ok = self._distance_ok(sl_pts)
        tp_ok = self._distance_ok(tp_pts)
        blocked = not (sl_ok and tp_ok)
        reason = (
            f"SL/TP příliš blízko ceny (min: {self._stops_level} bodů)"
            if blocked else ""
        )
        self._set_stop_button_blocked(blocked, reason)

        if sl_pts > 0:
            if tick_value and tick_size and tick_size > 0:
                sl_usd = (sl_pts * point / tick_size) * tick_value * lot_size
                self.stop_sl_usd_label.setText(f"-{sl_usd:.2f} USD")
            else:
                self.stop_sl_usd_label.setText("-- USD")
            self.stop_sl_usd_label.setStyleSheet(
                "color:#ef4444; font-size:11px; font-weight:bold;"
                if sl_ok else "color:#f59e0b; font-size:11px; font-weight:bold;"
            )
            sl_price = (entry - sl_pts * point) if is_buy else (entry + sl_pts * point)
            self.stop_sl_price_label.setText(
                f"Cena: {sl_price:.{digits}f}"
                if sl_ok else f"⚠ Min: {self._stops_level} bodů"
            )
            self.stop_sl_price_label.setStyleSheet(
                "color:#64748b; font-size:9px;" if sl_ok else "color:#f59e0b; font-size:9px; font-weight:bold;"
            )
        else:
            self.stop_sl_usd_label.setText("Bez SL")
            self.stop_sl_usd_label.setStyleSheet("color:#ef4444; font-size:11px; font-weight:bold;")
            self.stop_sl_price_label.setText("")

        if tp_pts > 0:
            if tick_value and tick_size and tick_size > 0:
                tp_usd = (tp_pts * point / tick_size) * tick_value * lot_size
                self.stop_tp_usd_label.setText(f"+{tp_usd:.2f} USD")
            else:
                self.stop_tp_usd_label.setText("-- USD")
            self.stop_tp_usd_label.setStyleSheet(
                "color:#22c55e; font-size:11px; font-weight:bold;"
                if tp_ok else "color:#f59e0b; font-size:11px; font-weight:bold;"
            )
            tp_price = (entry + tp_pts * point) if is_buy else (entry - tp_pts * point)
            self.stop_tp_price_label.setText(
                f"Cena: {tp_price:.{digits}f}"
                if tp_ok else f"⚠ Min: {self._stops_level} bodů"
            )
            self.stop_tp_price_label.setStyleSheet(
                "color:#64748b; font-size:9px;" if tp_ok else "color:#f59e0b; font-size:9px; font-weight:bold;"
            )
        else:
            self.stop_tp_usd_label.setText("Bez TP")
            self.stop_tp_usd_label.setStyleSheet("color:#22c55e; font-size:11px; font-weight:bold;")
            self.stop_tp_price_label.setText("")

    def _on_place_stop(self) -> None:
        is_buy = self.buy_stop_btn.isChecked()
        params = {
            "symbol": self._symbol,
            "side": "BUY_STOP" if is_buy else "SELL_STOP",
            "lot_size": self.stop_lot_spin.value(),   # ← STOP lot (nezávislý)
            "price": self.stop_price_spin.value(),
            "deviation": self.dev_spin.value(),
        }

        entry = self.stop_price_spin.value()
        sl_pts = self.stop_sl_spin.value()
        tp_pts = self.stop_tp_spin.value()
        point = self._point
        is_buy = params["side"] == "BUY_STOP"

        params["sl"] = (entry - sl_pts * point) if (sl_pts > 0 and is_buy) else ((entry + sl_pts * point) if sl_pts > 0 else 0.0)
        params["tp"] = (entry + tp_pts * point) if (tp_pts > 0 and is_buy) else ((entry - tp_pts * point) if tp_pts > 0 else 0.0)

        checked_btn = self.stop_tf_group.checkedButton()
        if checked_btn:
            params["comment"] = checked_btn.text()

        self.action_requested.emit("place_stop", params)

    # ------------------------------------------------------- live updates
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

        # Načtení symbol_info (point, digits, tick_value, stops_level, volume_*).
        if not self._info_fetched:
            import mt5_service
            info = mt5_service.get_symbol_info(self._symbol)
            if info:
                self._point = info["point"]
                self._digits = info["digits"]
                self._tick_value = info["tick_value"]
                self._tick_size = info["tick_size"]
                self._stops_level = info.get("stops_level", 0)
                self._volume_min = info.get("volume_min", 0.01)
                self._volume_max = info.get("volume_max", 1000.0)
                self._volume_step = info.get("volume_step", 0.01)
                self._info_fetched = True

                # Inicializace stop ceny + decimalizace.
                if self.stop_price_spin.value() == 0.0:
                    self.stop_price_spin.setValue(tick["ask"])
                self.stop_price_spin.setDecimals(self._digits)
                self.stop_price_spin.setSingleStep(self._point * 10)

                # Aplikace omezení lotu.
                self.lot_spin.setSingleStep(self._volume_step if self._volume_step > 0 else 0.01)
                self.stop_lot_spin.setSingleStep(self._volume_step if self._volume_step > 0 else 0.01)
                self._on_lot_changed()
                self._on_stop_lot_changed()

        self._update_sl_tp_labels()
        self._update_stop_lbls()

    def update_account(self, acc: dict | None) -> None:
        """Aktualizuje info řádek v hlavičce (Equity / Free / P/L pár)."""
        self._last_account = acc
        self._refresh_info_label()

    def _refresh_info_label(self) -> None:
        acc = self._last_account
        if not acc:
            self.info_label.setText("")
            return
        cur = acc.get("currency", "USD")
        equity = acc.get("equity", 0.0)
        free = acc.get("margin_free", equity)
        pl = self._pair_pl
        pl_color = "#22c55e" if pl >= 0 else "#ef4444"
        pl_sign = "+" if pl >= 0 else ""
        self.info_label.setText(
            f"Equity: <b>{equity:,.2f} {cur}</b>  •  "
            f"Free: <b>{free:,.2f}</b>  •  "
            f"P/L pár: <span style='color:{pl_color}'><b>{pl_sign}{pl:.2f}</b></span>"
        )

    def update_positions(self, positions: list[dict]) -> None:
        self.table.setRowCount(0)
        total_pl = 0.0

        # Omezíme pouze na páry z Quantum Advanced Multi-TF Matrix Screen tabulky.
        allowed_symbols = {"XAUUSD", "EURUSD", "USDJPY", "EURJPY", "USDCAD", "GBPUSD", "GBPCHF", "AUDUSD"}

        # P/L tohoto konkrétního symbolu (pro info řádek).
        self._pair_pl = sum(p["profit"] for p in positions if p["symbol"] == self._symbol)

        filtered_positions = [p for p in positions if p["symbol"] in allowed_symbols]

        for p in filtered_positions:
            row = self.table.rowCount()
            self.table.insertRow(row)

            symbol_item = QTableWidgetItem(p["symbol"])
            symbol_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, symbol_item)

            comment_item = QTableWidgetItem(p.get("comment", ""))
            comment_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, comment_item)

            pl_item = QTableWidgetItem(f"{p['profit']:.2f}")
            pl_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            pl_color = Qt.GlobalColor.green if p["profit"] >= 0 else Qt.GlobalColor.red
            pl_item.setForeground(pl_color)
            self.table.setItem(row, 2, pl_item)

            is_buy = p["type"] == "BUY"
            price_str = f"@ {p['price_open']:.2f}" if ("XAU" in p["symbol"] or "JPY" in p["symbol"]) else f"@ {p['price_open']:.5f}"
            price_item = QTableWidgetItem(price_str)
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            price_item.setForeground(
                Qt.GlobalColor.green if is_buy else Qt.GlobalColor.red
            )
            self.table.setItem(row, 3, price_item)

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
            self.positions_box.setTitle("POZICE")
            self.positions_summary.setText("Žádné otevřené pozice.")
        else:
            self.positions_box.setTitle(f"POZICE ({count})")
            color = "#22c55e" if total_pl >= 0 else "#ef4444"
            sign = "+" if total_pl >= 0 else ""
            self.positions_summary.setText(
                f"Celkem <span style='color:{color}'><b>{sign}{total_pl:.2f}</b></span>"
            )

        self._refresh_info_label()

    # -------------------------------------------------------- busy state
    _busy: bool = False

    def set_busy(self, busy: bool) -> None:
        """Při probíhající akci deaktivuje tlačítka (prevence dvojkliku)."""
        self._busy = busy
        for btn in (
            self.buy_btn, self.sell_btn, self.close_btn, self.close_profit_btn,
            self.close_all_btn, self.save_defaults_btn, self.place_stop_btn,
            self.update_price_btn, self.buy_stop_btn, self.sell_stop_btn,
        ):
            btn.setEnabled(not busy)
        # Po uvolnění busy znovu aplikujeme případnou blokaci kvůli stops_level.
        if not busy:
            self._update_sl_tp_labels()
            self._update_stop_lbls()

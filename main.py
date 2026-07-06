"""Trading Panel pro MetaTrader 5 — entry point.

Spuštění:
    python main.py
"""

from __future__ import annotations

import logging
import sys

from PyQt6.QtWidgets import QApplication

from ui.main_window import MainWindow


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler("trading.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> int:
    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("Trading Panel MT5")

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

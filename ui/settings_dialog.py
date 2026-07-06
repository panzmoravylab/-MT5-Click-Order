"""Modální dialog pro nastavení připojení k MT5."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.workers import ConnectWorker


class SettingsDialog(QDialog):
    """Dialog pro zadání loginu, hesla, serveru a cesty k terminálu.

    Tlačítko „Test připojení“ ověří, že zadané údaje fungují, než se uloží.
    """

    def __init__(self, config: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nastavení — připojení k MetaTrader 5")
        self.setMinimumWidth(480)
        self._config = config
        self._connect_worker: ConnectWorker | None = None

        self._build_ui()
        self._load_values()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel("Přihlášení k MT5 účtu")
        title.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(title)

        hint = QLabel(
            "Login = číslo účtu MT5 (nalezneš v terminálu: Soubor → Otevřít účet). "
            "Heslo HESLO OBCHODNÍKA (trader password), nikoli investorské."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(hint)

        form = QFormLayout()
        form.setSpacing(8)

        self.login_edit = QLineEdit()
        self.login_edit.setPlaceholderText("např. 12345678")

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("obchodní heslo k účtu")

        self.server_edit = QLineEdit()
        self.server_edit.setPlaceholderText("např. ICMarketsSC-Demo, Exness-Real")

        # Cesta k terminálu s tlačítkem Procházet.
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(r"C:\Program Files\MetaTrader 5\terminal64.exe")
        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit, 1)
        browse_btn = QPushButton("Procházet…")
        browse_btn.clicked.connect(self._browse_terminal)
        path_row.addWidget(browse_btn)
        path_container = QWidget()
        path_container.setLayout(path_row)

        form.addRow("Login:", self.login_edit)
        form.addRow("Heslo:", self.password_edit)
        form.addRow("Server:", self.server_edit)
        form.addRow("Cesta k terminálu:", path_container)
        layout.addLayout(form)

        # Tlačítka.
        button_row = QHBoxLayout()

        self.test_btn = QPushButton("Test připojení")
        self.test_btn.clicked.connect(self._test_connection)
        button_row.addWidget(self.test_btn)

        button_row.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        button_row.addWidget(buttons)
        layout.addLayout(button_row)

    def _load_values(self) -> None:
        from config_manager import get_mt5_credentials

        cred = get_mt5_credentials(self._config)
        self.login_edit.setText(str(cred["login"]) if cred["login"] else "")
        self.password_edit.setText(cred["password"])
        self.server_edit.setText(cred["server"])
        self.path_edit.setText(cred["terminal_path"])

    def _browse_terminal(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Vyber terminal64.exe",
            self.path_edit.text() or r"C:\Program Files\MetaTrader 5",
            "MT5 Terminal (terminal64.exe);;Všechny soubory (*.*)",
        )
        if path:
            self.path_edit.setText(path)

    # -------------------------------------------------------- hodnoty / save
    def values(self) -> dict:
        """Vrátí zadané hodnoty (login jako int)."""
        from config_manager import get_mt5_credentials

        cred = get_mt5_credentials(self._config)  # výchozí struktura
        try:
            login = int(self.login_edit.text().strip())
        except ValueError:
            login = 0
        cred["login"] = login
        cred["password"] = self.password_edit.text()
        cred["server"] = self.server_edit.text().strip()
        cred["terminal_path"] = self.path_edit.text().strip()
        return cred

    # ----------------------------------------------------------- test conn.
    def _test_connection(self) -> None:
        values = self.values()
        if values["login"] == 0 or not values["password"] or not values["server"]:
            QMessageBox.warning(
                self, "Chybí údaje", "Vyplň login, heslo i server před testem."
            )
            return

        self.test_btn.setEnabled(False)
        self.test_btn.setText("Připojuji…")

        self._connect_worker = ConnectWorker(
            login=values["login"],
            password=values["password"],
            server=values["server"],
            terminal_path=values["terminal_path"],
        )
        self._connect_worker.connected.connect(self._on_test_ok)
        self._connect_worker.failed.connect(self._on_test_fail)
        self._connect_worker.start()

    def _on_test_ok(self, msg: str) -> None:
        self.test_btn.setEnabled(True)
        self.test_btn.setText("Test připojení")
        QMessageBox.information(self, "Připojeno", msg)

    def _on_test_fail(self, msg: str) -> None:
        self.test_btn.setEnabled(True)
        self.test_btn.setText("Test připojení")
        QMessageBox.warning(self, "Připojení selhalo", msg)

from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.application.usecases.connect_wechat import ConnectWeChatUseCase


class SessionPage(QWidget):
    def __init__(self, connect_use_case: ConnectWeChatUseCase) -> None:
        super().__init__()
        self._connect_use_case = connect_use_case

        self._running_value = QLabel("Unknown")
        self._logged_in_value = QLabel("Unknown")
        self._driver_value = QLabel(self._connect_use_case.driver_name)
        self._detail_box = QTextEdit()
        self._detail_box.setReadOnly(True)
        self._connect_button = QPushButton("Connect WeChat")

        self._build_ui()
        self._connect_button.clicked.connect(self._handle_connect)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        status_group = QGroupBox("WeChat Session")
        status_form = QFormLayout(status_group)
        status_form.addRow("Running", self._running_value)
        status_form.addRow("Logged In", self._logged_in_value)
        status_form.addRow("Driver", self._driver_value)

        layout.addWidget(status_group)
        layout.addWidget(self._connect_button)
        layout.addWidget(self._detail_box)

    def _handle_connect(self) -> None:
        result = self._connect_use_case.execute()
        self._running_value.setText("Yes" if result.is_running else "No")
        self._logged_in_value.setText("Yes" if result.is_logged_in else "No")
        self._detail_box.setPlainText(result.message)


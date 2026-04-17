from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.application.usecases.send_message import SendMessageUseCase


class _SendMessageWorker(QObject):
    finished = Signal(bool, str)

    def __init__(self, send_message_use_case: SendMessageUseCase, target: str, text: str) -> None:
        super().__init__()
        self._send_message_use_case = send_message_use_case
        self._target = target
        self._text = text

    def run(self) -> None:
        result = self._send_message_use_case.execute(
            target=self._target,
            text=self._text,
        )
        self.finished.emit(result.success, result.message)


class MessagePage(QWidget):
    def __init__(self, send_message_use_case: SendMessageUseCase) -> None:
        super().__init__()
        self._send_message_use_case = send_message_use_case
        self._send_thread: QThread | None = None
        self._send_worker: _SendMessageWorker | None = None
        self._build_ui()
        self.target_input.textChanged.connect(self._sync_send_enabled)
        self.message_input.textChanged.connect(self._sync_send_enabled)
        self.send_button.clicked.connect(self._handle_send)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        compose_group = QGroupBox("Compose Message")
        compose_form = QFormLayout(compose_group)

        self.target_input = QLineEdit()
        self.message_input = QTextEdit()
        self.send_button = QPushButton("Send")
        self.result_label = QLabel("Ready.")
        self.send_button.setEnabled(False)

        compose_form.addRow("Target", self.target_input)
        compose_form.addRow("Message", self.message_input)

        layout.addWidget(compose_group)
        layout.addWidget(self.send_button)
        layout.addWidget(self.result_label)

    def _sync_send_enabled(self) -> None:
        has_target = bool(self.target_input.text().strip())
        has_text = bool(self.message_input.toPlainText().strip())
        is_busy = self._send_thread is not None and self._send_thread.isRunning()
        self.send_button.setEnabled(has_target and has_text and not is_busy)

    def _handle_send(self) -> None:
        target = self.target_input.text()
        text = self.message_input.toPlainText()

        self.result_label.setText("Sending message...")
        self.send_button.setEnabled(False)

        thread = QThread(self)
        worker = _SendMessageWorker(
            send_message_use_case=self._send_message_use_case,
            target=target,
            text=text,
        )
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._handle_send_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_send_thread)

        self._send_thread = thread
        self._send_worker = worker
        thread.start()

    def _handle_send_finished(self, success: bool, message: str) -> None:
        self.result_label.setText(message)
        self._sync_send_enabled()

    def _clear_send_thread(self) -> None:
        self._send_thread = None
        self._send_worker = None
        self._sync_send_enabled()

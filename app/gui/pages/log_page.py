from __future__ import annotations

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtWidgets import QCheckBox, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from app.application.dto.read_messages_result import ChatMessageDTO
from app.application.usecases.read_current_chat_messages import ReadCurrentChatMessagesUseCase


class _ReadMessagesWorker(QObject):
    finished = Signal(bool, str, list, str)

    def __init__(self, use_case: ReadCurrentChatMessagesUseCase) -> None:
        super().__init__()
        self._use_case = use_case

    def run(self) -> None:
        try:
            result = self._use_case.execute()
            self.finished.emit(result.success, result.chat_title, result.messages, result.message)
        except Exception as exc:  # noqa: BLE001
            self.finished.emit(False, "", [], f"Unexpected error: {exc}")


class LogPage(QWidget):
    def __init__(self, read_current_chat_messages_use_case: ReadCurrentChatMessagesUseCase) -> None:
        super().__init__()
        self._read_current_chat_messages_use_case = read_current_chat_messages_use_case
        self._thread: QThread | None = None
        self._worker: _ReadMessagesWorker | None = None
        self._closing = False
        self._last_chat_title = ""
        self._last_messages: list[ChatMessageDTO] = []
        self._last_new_messages: list[ChatMessageDTO] = []
        self._history_messages: list[ChatMessageDTO] = []
        self._timer = QTimer(self)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self._handle_refresh)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.status_label = QLabel("Read the currently open chat here.")
        self.refresh_button = QPushButton("Refresh Current Chat")
        self.auto_refresh_checkbox = QCheckBox("Auto Refresh Every 3s")
        self.only_new_checkbox = QCheckBox("Only Show New Messages")
        self.only_new_checkbox.setChecked(True)
        self.append_history_checkbox = QCheckBox("Append New Messages To History")
        self.append_history_checkbox.setChecked(True)
        self.clear_button = QPushButton("Clear History")
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlainText("Current chat messages will appear here.")
        self.refresh_button.clicked.connect(self._handle_refresh)
        self.auto_refresh_checkbox.toggled.connect(self._handle_auto_refresh_toggled)
        self.only_new_checkbox.toggled.connect(self._rerender_messages)
        self.append_history_checkbox.toggled.connect(self._rerender_messages)
        self.clear_button.clicked.connect(self._clear_history)
        layout.addWidget(self.status_label)
        layout.addWidget(self.refresh_button)
        layout.addWidget(self.auto_refresh_checkbox)
        layout.addWidget(self.only_new_checkbox)
        layout.addWidget(self.append_history_checkbox)
        layout.addWidget(self.clear_button)
        layout.addWidget(self.log_output)

    def _handle_refresh(self) -> None:
        if self._closing:
            return
        if self._thread is not None and self._thread.isRunning():
            return

        self.status_label.setText("Reading current chat...")
        self.refresh_button.setEnabled(False)

        thread = QThread(self)
        worker = _ReadMessagesWorker(self._read_current_chat_messages_use_case)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._handle_refresh_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_thread)

        self._thread = thread
        self._worker = worker
        thread.start()

    def _handle_refresh_finished(self, success: bool, chat_title: str, messages: list, detail: str) -> None:
        if self._closing:
            return
        title = chat_title or "Unknown Chat"
        normalized_messages = self._normalize_messages(messages)
        new_messages = self._extract_new_messages(chat_title=title, messages=normalized_messages) if success else []
        if success:
            change_hint = self._build_change_hint(chat_title=title, messages=normalized_messages)
            new_hint = f" | {len(new_messages)} new" if new_messages else ""
            self.status_label.setText(f"Current chat: {title} | {detail}{change_hint}")
            if new_hint:
                self.status_label.setText(f"{self.status_label.text()}{new_hint}")
        else:
            self.status_label.setText(detail or f"Failed to read current chat: {title}")
        if success and normalized_messages:
            self._update_history(chat_title=title, current_messages=normalized_messages, new_messages=new_messages)
            self._last_chat_title = title
            self._last_messages = normalized_messages
            self._last_new_messages = new_messages
            self._rerender_messages()
        elif success:
            if title != self._last_chat_title:
                self._history_messages = []
            self._last_chat_title = title
            self._last_messages = []
            self._last_new_messages = []
            self._rerender_messages()
        else:
            self.log_output.setPlainText(detail or f"Failed to read messages from: {title}")

    def _clear_thread(self) -> None:
        self._thread = None
        self._worker = None
        if not self._closing:
            self.refresh_button.setEnabled(True)

    def _handle_auto_refresh_toggled(self, checked: bool) -> None:
        if self._closing:
            return
        if checked:
            self._timer.start()
            self.status_label.setText("Auto refresh enabled. Reading current chat every 3 seconds without switching focus.")
            self._handle_refresh()
        else:
            self._timer.stop()
            self.status_label.setText("Auto refresh disabled.")

    def _build_change_hint(self, *, chat_title: str, messages: list[str]) -> str:
        if chat_title != self._last_chat_title:
            return " | chat changed"
        if not self._last_messages:
            return ""
        if self._message_signatures(messages) == self._message_signatures(self._last_messages):
            return " | unchanged"
        return " | updated"

    def _extract_new_messages(self, *, chat_title: str, messages: list[ChatMessageDTO]) -> list[ChatMessageDTO]:
        if chat_title != self._last_chat_title:
            return [self._with_new_flag(message, True) for message in messages]
        if not self._last_messages:
            return [self._with_new_flag(message, True) for message in messages]

        current_signatures = self._message_signatures(messages)
        last_signatures = self._message_signatures(self._last_messages)
        if current_signatures == last_signatures:
            return []

        max_overlap = min(len(last_signatures), len(current_signatures))
        for overlap in range(max_overlap, 0, -1):
            if last_signatures[-overlap:] == current_signatures[:overlap]:
                return [self._with_new_flag(message, True) for message in messages[overlap:]]

        return [self._with_new_flag(message, True) for message in messages]

    def _rerender_messages(self) -> None:
        if not self._last_messages and not self._history_messages:
            self.log_output.setPlainText("(No visible message text detected.)")
            return

        if self.only_new_checkbox.isChecked():
            if self._last_new_messages:
                self.log_output.setPlainText(self._format_messages(self._last_new_messages))
            else:
                self.log_output.setPlainText("(No new visible messages.)")
            return

        display_messages = self._history_messages if self.append_history_checkbox.isChecked() else self._last_messages
        self.log_output.setPlainText(self._format_messages(display_messages, new_messages=self._last_new_messages))

    def _format_messages(
        self,
        messages: list[ChatMessageDTO],
        *,
        new_messages: list[ChatMessageDTO] | None = None,
    ) -> str:
        new_signatures = {self._message_signature(message) for message in (new_messages or [])}
        formatted_messages = []
        for index, item in enumerate(messages, start=1):
            prefix = "[NEW] " if self._message_signature(item) in new_signatures else ""
            meta_parts = [self._kind_label(item.kind)]
            if item.sender:
                meta_parts.insert(0, item.sender)
            meta_line = " | ".join(meta_parts)
            formatted_messages.append(
                f"[{index}] {meta_line}\n{prefix}{item.content}"
            )
        return "\n\n------\n\n".join(formatted_messages)

    def _normalize_messages(self, messages: list) -> list[ChatMessageDTO]:
        normalized: list[ChatMessageDTO] = []
        for item in messages:
            if isinstance(item, ChatMessageDTO):
                normalized.append(item)
                continue
            if isinstance(item, dict):
                content = str(item.get("content", "")).strip()
                if not content:
                    continue
                normalized.append(
                    ChatMessageDTO(
                        content=content,
                        sender=str(item.get("sender", "")).strip(),
                        kind=str(item.get("kind", "text")).strip() or "text",
                        is_new=bool(item.get("is_new", False)),
                    )
                )
                continue
            content = str(item).strip()
            if content:
                normalized.append(ChatMessageDTO(content=content))
        return normalized

    def _message_signatures(self, messages: list[ChatMessageDTO]) -> list[str]:
        return [self._message_signature(message) for message in messages]

    def _message_signature(self, message: ChatMessageDTO) -> str:
        return f"{message.kind}|{message.sender}|{message.content}"

    def _with_new_flag(self, message: ChatMessageDTO, is_new: bool) -> ChatMessageDTO:
        return ChatMessageDTO(
            content=message.content,
            sender=message.sender,
            kind=message.kind,
            is_new=is_new,
        )

    def _update_history(
        self,
        *,
        chat_title: str,
        current_messages: list[ChatMessageDTO],
        new_messages: list[ChatMessageDTO],
    ) -> None:
        if chat_title != self._last_chat_title:
            self._history_messages = list(current_messages)
            return

        if not self.append_history_checkbox.isChecked():
            self._history_messages = list(current_messages)
            return

        history_signatures = {self._message_signature(message) for message in self._history_messages}
        for message in new_messages:
            signature = self._message_signature(message)
            if signature in history_signatures:
                continue
            self._history_messages.append(message)
            history_signatures.add(signature)

        if not self._history_messages:
            self._history_messages = list(current_messages)

    def _clear_history(self) -> None:
        self._history_messages = []
        self._last_new_messages = []
        self.log_output.setPlainText("(History cleared.)")

    def shutdown(self) -> None:
        self._closing = True
        self._timer.stop()
        self.refresh_button.setEnabled(False)
        self.auto_refresh_checkbox.setEnabled(False)
        self.only_new_checkbox.setEnabled(False)
        if self._thread is not None and self._thread.isRunning():
            if self._worker is not None:
                try:
                    self._worker.finished.disconnect(self._handle_refresh_finished)
                except (RuntimeError, TypeError):
                    pass
            try:
                self._thread.finished.disconnect(self._clear_thread)
            except (RuntimeError, TypeError):
                pass
            self._thread.quit()
            self._thread.wait(3000)
            if self._thread.isRunning():
                self._thread.terminate()
                self._thread.wait(1000)

    def _kind_label(self, kind: str) -> str:
        labels = {
            "text": "Text",
            "system": "System",
            "notification": "Notification",
            "non_text": "Non-text",
        }
        return labels.get(kind, kind or "Text")

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.shutdown()
        super().closeEvent(event)

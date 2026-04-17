from __future__ import annotations

import time

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtWidgets import QCheckBox, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget

from app.application.dto.auto_reply import AutoReplyActionDTO, AutoReplyRuleDTO
from app.application.dto.read_messages_result import ChatMessageDTO
from app.application.dto.read_visible_chats_result import ChatSnapshotDTO
from app.application.usecases.plan_auto_replies import PlanAutoRepliesUseCase
from app.application.usecases.read_visible_chats import ReadVisibleChatsUseCase
from app.application.usecases.send_message import SendMessageUseCase

_DEFAULT_AUTO_REPLY_RULES = """你好 => 你好，我已经收到消息了，稍后回复你。
在吗 => 在的，我稍后回复你。
收到 => 好的，收到。"""


class _ReadVisibleChatsWorker(QObject):
    finished = Signal(bool, list, str)

    def __init__(self, use_case: ReadVisibleChatsUseCase, *, unread_only: bool) -> None:
        super().__init__()
        self._use_case = use_case
        self._unread_only = unread_only

    def run(self) -> None:
        try:
            result = self._use_case.execute(unread_only=self._unread_only)
            self.finished.emit(result.success, result.chats, result.message)
        except Exception as exc:  # noqa: BLE001
            self.finished.emit(False, [], f"Unexpected error: {exc}")


class _SendAutoRepliesWorker(QObject):
    finished = Signal(bool, list, str)

    def __init__(self, send_message_use_case: SendMessageUseCase, *, actions: list[AutoReplyActionDTO]) -> None:
        super().__init__()
        self._send_message_use_case = send_message_use_case
        self._actions = actions

    def run(self) -> None:
        logs: list[str] = []
        success = True
        for action in self._actions:
            result = self._send_message_use_case.execute(action.chat_title, action.reply_text)
            if result.success:
                logs.append(f'[Auto Reply] [{action.chat_title}] "{action.reply_text}"')
                continue
            success = False
            logs.append(f'[Auto Reply Failed] [{action.chat_title}] {result.message}')
        detail = f"Auto replied {len(self._actions)} messages." if success else "Some auto replies failed."
        self.finished.emit(success, logs, detail)


class TaskPage(QWidget):
    def __init__(
        self,
        read_visible_chats_use_case: ReadVisibleChatsUseCase,
        send_message_use_case: SendMessageUseCase,
        plan_auto_replies_use_case: PlanAutoRepliesUseCase,
    ) -> None:
        super().__init__()
        self._read_visible_chats_use_case = read_visible_chats_use_case
        self._send_message_use_case = send_message_use_case
        self._plan_auto_replies_use_case = plan_auto_replies_use_case
        self._thread: QThread | None = None
        self._worker: QObject | None = None
        self._closing = False
        self._last_chat_signatures: dict[str, list[str]] = {}
        self._last_polled_chat_titles: set[str] = set()
        self._auto_reply_handled_signatures: set[str] = set()
        self._auto_reply_last_sent_at: dict[str, float] = {}
        self._pending_auto_reply_actions: list[AutoReplyActionDTO] = []
        self._pending_auto_reply_signatures: list[str] = []
        self._history_lines: list[str] = []
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self._handle_refresh)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.status_label = QLabel("Monitor all visible chats here.")
        self.refresh_button = QPushButton("Poll Visible Chats")
        self.auto_refresh_checkbox = QCheckBox("Monitor Visible Chats Every 5s")
        self.unread_only_checkbox = QCheckBox("Only Poll Chats With Red Dot")
        self.unread_only_checkbox.setChecked(True)
        self.auto_reply_checkbox = QCheckBox("Enable Rule-based Auto Reply")
        self.auto_reply_whitelist = QTextEdit()
        self.auto_reply_blacklist = QTextEdit()
        self.auto_reply_cooldown_input = QLineEdit()
        self.auto_reply_rules = QTextEdit()
        self.auto_reply_whitelist.setPlaceholderText("Auto Reply Whitelist Chats, one per line. Leave empty to allow all.")
        self.auto_reply_blacklist.setPlaceholderText("Auto Reply Blacklist Chats, one per line.")
        self.auto_reply_cooldown_input.setPlaceholderText("Cooldown seconds per chat")
        self.auto_reply_cooldown_input.setText("300")
        self.auto_reply_rules.setPlaceholderText("每行一条规则，格式：关键词 => 自动回复内容")
        self.auto_reply_rules.setPlainText(_DEFAULT_AUTO_REPLY_RULES)
        self.clear_button = QPushButton("Clear Monitor History")
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlainText("Visible chat updates will appear here.")

        self.refresh_button.clicked.connect(self._handle_refresh)
        self.auto_refresh_checkbox.toggled.connect(self._handle_auto_refresh_toggled)
        self.clear_button.clicked.connect(self._clear_history)

        layout.addWidget(self.status_label)
        layout.addWidget(self.refresh_button)
        layout.addWidget(self.auto_refresh_checkbox)
        layout.addWidget(self.unread_only_checkbox)
        layout.addWidget(self.auto_reply_checkbox)
        layout.addWidget(QLabel("Auto Reply Whitelist Chats"))
        layout.addWidget(self.auto_reply_whitelist)
        layout.addWidget(QLabel("Auto Reply Blacklist Chats"))
        layout.addWidget(self.auto_reply_blacklist)
        layout.addWidget(QLabel("Auto Reply Cooldown Seconds"))
        layout.addWidget(self.auto_reply_cooldown_input)
        layout.addWidget(QLabel("Auto Reply Rules"))
        layout.addWidget(self.auto_reply_rules)
        layout.addWidget(self.clear_button)
        layout.addWidget(self.output)

    def _handle_refresh(self) -> None:
        if self._closing or self._thread is not None and self._thread.isRunning():
            return

        self.status_label.setText("Polling visible chats...")
        self.refresh_button.setEnabled(False)

        thread = QThread(self)
        worker = _ReadVisibleChatsWorker(
            self._read_visible_chats_use_case,
            unread_only=self.unread_only_checkbox.isChecked(),
        )
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

    def _handle_refresh_finished(self, success: bool, chats: list, detail: str) -> None:
        if self._closing:
            return

        normalized_chats = [chat for item in chats if isinstance(item, ChatSnapshotDTO) for chat in [item]]
        if not success:
            self.status_label.setText(detail or "Failed to monitor visible chats.")
            self.output.setPlainText(detail or "Failed to monitor visible chats.")
            return

        new_lines, new_chat_messages = self._collect_new_lines(normalized_chats)
        visible_counts = ", ".join(f"{chat.chat_title}:{len(chat.messages)}" for chat in normalized_chats[:5])
        summary_suffix = f" | {visible_counts}" if visible_counts else ""
        self.status_label.setText(f"{detail} | {len(new_lines)} new updates{summary_suffix}")
        if new_lines:
            self._history_lines.extend(new_lines)
            self.output.setPlainText("\n\n".join(self._history_lines))
        elif not self._history_lines:
            self.output.setPlainText("(No visible chat updates detected yet.)")

        self._maybe_start_auto_reply(new_chat_messages)

    def _collect_new_lines(self, chats: list[ChatSnapshotDTO]) -> tuple[list[str], list[ChatSnapshotDTO]]:
        new_lines: list[str] = []
        new_signature_map: dict[str, list[str]] = {}
        current_chat_titles = {chat.chat_title for chat in chats}
        new_chat_messages: list[ChatSnapshotDTO] = []

        for chat in chats:
            current_signatures = [self._message_signature(message) for message in chat.messages]
            previous_signatures = self._last_chat_signatures.get(chat.chat_title, [])
            is_newly_polled_chat = chat.chat_title not in self._last_polled_chat_titles
            appended_messages = self._extract_appended_messages(
                chat.messages,
                previous_signatures,
                force_emit_all=is_newly_polled_chat,
            )
            if appended_messages:
                new_chat_messages.append(ChatSnapshotDTO(chat_title=chat.chat_title, messages=appended_messages))
            for message in appended_messages:
                sender_prefix = f"{message.sender} | " if message.sender else ""
                new_lines.append(f"[{chat.chat_title}] {sender_prefix}{self._kind_label(message.kind)}\n{message.content}")
            new_signature_map[chat.chat_title] = current_signatures

        self._last_chat_signatures = new_signature_map
        self._last_polled_chat_titles = current_chat_titles
        return new_lines, new_chat_messages

    def _maybe_start_auto_reply(self, chats: list[ChatSnapshotDTO]) -> None:
        if not self.auto_reply_checkbox.isChecked():
            return

        eligible_chats = self._filter_auto_reply_chats(chats)
        if not eligible_chats:
            return

        rules = self._parse_auto_reply_rules(self.auto_reply_rules.toPlainText())
        plan = self._plan_auto_replies_use_case.execute(
            chats=eligible_chats,
            rules=rules,
            handled_signatures=self._auto_reply_handled_signatures,
        )
        cooldown_seconds = self._parse_cooldown_seconds()
        if cooldown_seconds > 0:
            plan.actions = self._apply_auto_reply_cooldown(plan.actions, cooldown_seconds=cooldown_seconds)
        for signature in plan.ignored_signatures:
            self._auto_reply_handled_signatures.add(signature)
        if not plan.actions:
            return

        self.status_label.setText(f"{self.status_label.text()} | auto replying {len(plan.actions)}")
        self._pending_auto_reply_actions = plan.actions
        self._pending_auto_reply_signatures = [action.message_signature for action in plan.actions]
        if self._thread is None:
            self._start_auto_reply_worker()

    def _handle_auto_reply_finished(self, success: bool, logs: list, detail: str) -> None:
        if self._closing:
            return

        for signature in getattr(self, "_pending_auto_reply_signatures", []):
            self._auto_reply_handled_signatures.add(signature)
        self._pending_auto_reply_signatures = []

        normalized_logs = [str(item).strip() for item in logs if str(item).strip()]
        now = time.time()
        for log in normalized_logs:
            if log.startswith("[Auto Reply] ["):
                try:
                    chat_title = log.split("] [", 1)[1].split("]", 1)[0]
                except IndexError:
                    continue
                self._auto_reply_last_sent_at[self._normalize_chat_title(chat_title)] = now
        if normalized_logs:
            self._history_lines.extend(normalized_logs)
            self.output.setPlainText("\n\n".join(self._history_lines))

        prefix = "Auto reply complete." if success else "Auto reply finished with errors."
        self.status_label.setText(f"{prefix} {detail}")

    def _extract_appended_messages(
        self,
        messages: list[ChatMessageDTO],
        previous_signatures: list[str],
        *,
        force_emit_all: bool = False,
    ) -> list[ChatMessageDTO]:
        current_signatures = [self._message_signature(message) for message in messages]
        if force_emit_all:
            return messages
        if not previous_signatures:
            return messages
        if current_signatures == previous_signatures:
            return []

        max_overlap = min(len(previous_signatures), len(current_signatures))
        for overlap in range(max_overlap, 0, -1):
            if previous_signatures[-overlap:] == current_signatures[:overlap]:
                return messages[overlap:]

        return messages

    def _parse_auto_reply_rules(self, raw_text: str) -> list[AutoReplyRuleDTO]:
        rules: list[AutoReplyRuleDTO] = []
        for raw_line in raw_text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=>" in line:
                trigger, reply = line.split("=>", 1)
            elif "->" in line:
                trigger, reply = line.split("->", 1)
            else:
                continue
            trigger = trigger.strip()
            reply = reply.strip()
            if not trigger or not reply:
                continue
            rules.append(AutoReplyRuleDTO(trigger=trigger, reply_text=reply))
        return rules

    def _filter_auto_reply_chats(self, chats: list[ChatSnapshotDTO]) -> list[ChatSnapshotDTO]:
        whitelist = self._parse_chat_list(self.auto_reply_whitelist.toPlainText())
        blacklist = self._parse_chat_list(self.auto_reply_blacklist.toPlainText())
        filtered: list[ChatSnapshotDTO] = []
        for chat in chats:
            normalized_title = self._normalize_chat_title(chat.chat_title)
            if blacklist and normalized_title in blacklist:
                continue
            if whitelist and normalized_title not in whitelist:
                continue
            filtered.append(chat)
        return filtered

    def _parse_chat_list(self, raw_text: str) -> set[str]:
        return {
            self._normalize_chat_title(line)
            for line in raw_text.splitlines()
            if self._normalize_chat_title(line)
        }

    def _normalize_chat_title(self, value: str) -> str:
        return " ".join(value.strip().lower().split())

    def _parse_cooldown_seconds(self) -> int:
        raw_value = self.auto_reply_cooldown_input.text().strip()
        if not raw_value:
            return 0
        try:
            return max(0, int(raw_value))
        except ValueError:
            return 0

    def _apply_auto_reply_cooldown(
        self,
        actions: list[AutoReplyActionDTO],
        *,
        cooldown_seconds: int,
    ) -> list[AutoReplyActionDTO]:
        if cooldown_seconds <= 0:
            return actions
        now = time.time()
        filtered: list[AutoReplyActionDTO] = []
        chat_seen_this_round: set[str] = set()
        for action in actions:
            normalized_title = self._normalize_chat_title(action.chat_title)
            if normalized_title in chat_seen_this_round:
                continue
            last_sent_at = self._auto_reply_last_sent_at.get(normalized_title)
            if last_sent_at is not None and now - last_sent_at < cooldown_seconds:
                continue
            filtered.append(action)
            chat_seen_this_round.add(normalized_title)
        return filtered

    def _message_signature(self, message: ChatMessageDTO) -> str:
        return f"{message.kind}|{message.sender}|{message.content}"

    def _kind_label(self, kind: str) -> str:
        labels = {
            "text": "Text",
            "system": "System",
            "notification": "Notification",
            "non_text": "Non-text",
        }
        return labels.get(kind, kind or "Text")

    def _handle_auto_refresh_toggled(self, checked: bool) -> None:
        if self._closing:
            return
        if checked:
            self._timer.start()
            self.status_label.setText("Visible chat monitor enabled. Polling every 5 seconds.")
            self._handle_refresh()
        else:
            self._timer.stop()
            self.status_label.setText("Visible chat monitor disabled.")

    def _clear_history(self) -> None:
        self._history_lines = []
        self._last_chat_signatures = {}
        self._last_polled_chat_titles = set()
        self._auto_reply_handled_signatures = set()
        self._auto_reply_last_sent_at = {}
        self.output.setPlainText("(Monitor history cleared.)")

    def _clear_thread(self) -> None:
        self._thread = None
        self._worker = None
        if self._pending_auto_reply_actions and not self._closing:
            QTimer.singleShot(0, self._start_auto_reply_worker)
            return
        if not self._closing:
            self.refresh_button.setEnabled(True)

    def _start_auto_reply_worker(self) -> None:
        if self._closing or not self._pending_auto_reply_actions or self._thread is not None:
            return

        self.refresh_button.setEnabled(False)
        thread = QThread(self)
        worker = _SendAutoRepliesWorker(self._send_message_use_case, actions=self._pending_auto_reply_actions)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._handle_auto_reply_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_thread)

        self._thread = thread
        self._worker = worker
        self._pending_auto_reply_actions = []
        thread.start()

    def _shutdown_active_thread(self) -> None:
        if self._thread is None or not self._thread.isRunning():
            return
        if self._worker is not None:
            for handler in (self._handle_refresh_finished, self._handle_auto_reply_finished):
                try:
                    self._worker.finished.disconnect(handler)  # type: ignore[attr-defined]
                except (RuntimeError, TypeError, AttributeError):
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

    def shutdown(self) -> None:
        self._closing = True
        self._timer.stop()
        self.refresh_button.setEnabled(False)
        self.auto_refresh_checkbox.setEnabled(False)
        self.unread_only_checkbox.setEnabled(False)
        self.auto_reply_checkbox.setEnabled(False)
        self.auto_reply_whitelist.setEnabled(False)
        self.auto_reply_blacklist.setEnabled(False)
        self.auto_reply_cooldown_input.setEnabled(False)
        self.auto_reply_rules.setEnabled(False)
        self.clear_button.setEnabled(False)
        self._pending_auto_reply_actions = []
        self._pending_auto_reply_signatures = []
        self._shutdown_active_thread()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.shutdown()
        super().closeEvent(event)

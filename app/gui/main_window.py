from __future__ import annotations

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMainWindow, QStatusBar, QTabWidget

from app.application.usecases.connect_wechat import ConnectWeChatUseCase
from app.application.usecases.plan_auto_replies import PlanAutoRepliesUseCase
from app.application.usecases.read_current_chat_messages import ReadCurrentChatMessagesUseCase
from app.application.usecases.read_visible_chats import ReadVisibleChatsUseCase
from app.application.usecases.send_message import SendMessageUseCase
from app.gui.pages.log_page import LogPage
from app.gui.pages.message_page import MessagePage
from app.gui.pages.session_page import SessionPage
from app.gui.pages.task_page import TaskPage
from app.infrastructure.config.settings import AppSettings


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings: AppSettings,
        connect_use_case: ConnectWeChatUseCase,
        send_message_use_case: SendMessageUseCase,
        plan_auto_replies_use_case: PlanAutoRepliesUseCase,
        read_current_chat_messages_use_case: ReadCurrentChatMessagesUseCase,
        read_visible_chats_use_case: ReadVisibleChatsUseCase,
    ) -> None:
        super().__init__()
        self._settings = settings
        self._connect_use_case = connect_use_case
        self._send_message_use_case = send_message_use_case
        self._plan_auto_replies_use_case = plan_auto_replies_use_case
        self._read_current_chat_messages_use_case = read_current_chat_messages_use_case
        self._read_visible_chats_use_case = read_visible_chats_use_case

        self.setWindowTitle("wx-gui")
        self.resize(1080, 720)

        self._tabs = QTabWidget()
        self._status_bar = QStatusBar()

        self._session_page = SessionPage(connect_use_case=self._connect_use_case)
        self._message_page = MessagePage(send_message_use_case=self._send_message_use_case)
        self._task_page = TaskPage(
            read_visible_chats_use_case=self._read_visible_chats_use_case,
            send_message_use_case=self._send_message_use_case,
            plan_auto_replies_use_case=self._plan_auto_replies_use_case,
        )
        self._log_page = LogPage(read_current_chat_messages_use_case=self._read_current_chat_messages_use_case)

        self._tabs.addTab(self._session_page, "Session")
        self._tabs.addTab(self._message_page, "Message")
        self._tabs.addTab(self._task_page, "Task")
        self._tabs.addTab(self._log_page, "Logs")

        self.setCentralWidget(self._tabs)
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage(
            f"Platform: {self._settings.platform_name} | Driver: {self._settings.default_driver}"
        )

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        self._task_page.shutdown()
        self._log_page.shutdown()
        super().closeEvent(event)

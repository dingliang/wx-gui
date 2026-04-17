from __future__ import annotations

from app.application.usecases.connect_wechat import ConnectWeChatUseCase
from app.application.usecases.plan_auto_replies import PlanAutoRepliesUseCase
from app.application.usecases.read_current_chat_messages import ReadCurrentChatMessagesUseCase
from app.application.usecases.read_visible_chats import ReadVisibleChatsUseCase
from app.application.usecases.send_message import SendMessageUseCase
from app.automation.drivers.accessibility_driver import MacOSAccessibilityDriver
from app.gui.main_window import MainWindow
from app.infrastructure.config.settings import load_settings
from app.infrastructure.logging.logger import configure_logger


def build_main_window() -> MainWindow:
    settings = load_settings()
    configure_logger(settings)

    driver = MacOSAccessibilityDriver(settings=settings)
    connect_use_case = ConnectWeChatUseCase(driver=driver)
    send_message_use_case = SendMessageUseCase(driver=driver)
    plan_auto_replies_use_case = PlanAutoRepliesUseCase()
    read_current_chat_messages_use_case = ReadCurrentChatMessagesUseCase(driver=driver)
    read_visible_chats_use_case = ReadVisibleChatsUseCase(driver=driver)

    return MainWindow(
        settings=settings,
        connect_use_case=connect_use_case,
        send_message_use_case=send_message_use_case,
        plan_auto_replies_use_case=plan_auto_replies_use_case,
        read_current_chat_messages_use_case=read_current_chat_messages_use_case,
        read_visible_chats_use_case=read_visible_chats_use_case,
    )

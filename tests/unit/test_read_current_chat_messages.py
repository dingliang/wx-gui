from __future__ import annotations

from app.application.dto.read_messages_result import ChatMessageDTO
from app.application.usecases.read_current_chat_messages import ReadCurrentChatMessagesUseCase


class FakeDriver:
    name = "fake"

    def is_running(self) -> bool:
        return True

    def is_logged_in(self) -> bool:
        return True

    def activate(self) -> None:
        return None

    def search_chat(self, keyword: str) -> bool:
        return True

    def open_chat(self, name: str) -> None:
        return None

    def send_text(self, text: str) -> None:
        return None

    def send_file(self, file_path: str) -> None:
        return None

    def read_current_chat_messages(self) -> dict[str, object]:
        return {
            "chat_title": "sample-chat",
            "messages": [
                {"content": "09:12", "kind": "text"},
                {"content": "你撤回了一条消息", "kind": "system"},
                "hello",
            ],
        }

    def capture_state(self) -> dict[str, str]:
        return {}


def test_read_current_chat_messages_use_case_returns_messages() -> None:
    use_case = ReadCurrentChatMessagesUseCase(driver=FakeDriver())

    result = use_case.execute()

    assert result.success is True
    assert result.chat_title == "sample-chat"
    assert result.messages == [
        ChatMessageDTO(content="09:12", kind="text"),
        ChatMessageDTO(content="你撤回了一条消息", kind="system"),
        ChatMessageDTO(content="hello", kind="text"),
    ]

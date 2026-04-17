from __future__ import annotations

from app.application.dto.read_messages_result import ChatMessageDTO
from app.application.usecases.read_visible_chats import ReadVisibleChatsUseCase


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
        return {}

    def read_visible_chat_snapshots(self, unread_only: bool = False) -> dict[str, object]:
        assert unread_only is True
        return {
            "chats": [
                {
                    "chat_title": "sample-chat",
                    "messages": [
                        {"content": "hello", "kind": "text", "sender": "alice"},
                        {"content": "[非文本消息]", "kind": "non_text", "sender": "bob"},
                    ],
                },
                {
                    "chat_title": "sample-helper",
                    "messages": [
                        {"content": "你撤回了一条消息", "kind": "system"},
                    ],
                },
            ]
        }

    def capture_state(self) -> dict[str, str]:
        return {}


def test_read_visible_chats_use_case_returns_structured_snapshots() -> None:
    use_case = ReadVisibleChatsUseCase(driver=FakeDriver())

    result = use_case.execute(unread_only=True)

    assert result.success is True
    assert len(result.chats) == 2
    assert result.chats[0].chat_title == "sample-chat"
    assert result.chats[0].messages == [
        ChatMessageDTO(content="hello", kind="text", sender="alice"),
        ChatMessageDTO(content="[非文本消息]", kind="non_text", sender="bob"),
    ]
    assert result.chats[1].messages == [
        ChatMessageDTO(content="你撤回了一条消息", kind="system"),
    ]

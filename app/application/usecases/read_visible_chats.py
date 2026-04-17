from __future__ import annotations

from app.application.dto.read_messages_result import ChatMessageDTO
from app.application.dto.read_visible_chats_result import ChatSnapshotDTO, ReadVisibleChatsResultDTO
from app.automation.exceptions import DriverError
from app.automation.protocols.wechat_driver import WeChatDriver


class ReadVisibleChatsUseCase:
    def __init__(self, driver: WeChatDriver) -> None:
        self._driver = driver

    def execute(self, *, unread_only: bool = False) -> ReadVisibleChatsResultDTO:
        try:
            payload = self._driver.read_visible_chat_snapshots(unread_only=unread_only)
        except DriverError as exc:
            return ReadVisibleChatsResultDTO(
                success=False,
                chats=[],
                message=str(exc),
            )

        chats = payload.get("chats", [])
        if not isinstance(chats, list):
            chats = []

        normalized_chats = [chat for item in chats if (chat := self._normalize_chat(item)) is not None]
        return ReadVisibleChatsResultDTO(
            success=True,
            chats=normalized_chats,
            message=f"Read {len(normalized_chats)} visible chats.",
        )

    def _normalize_chat(self, item: object) -> ChatSnapshotDTO | None:
        if not isinstance(item, dict):
            return None

        title = str(item.get("chat_title", "")).strip()
        if not title:
            return None

        messages = item.get("messages", [])
        if not isinstance(messages, list):
            messages = []

        normalized_messages: list[ChatMessageDTO] = []
        for message in messages:
            normalized = self._normalize_message(message)
            if normalized is None:
                continue
            normalized_messages.append(normalized)

        return ChatSnapshotDTO(chat_title=title, messages=normalized_messages)

    def _normalize_message(self, item: object) -> ChatMessageDTO | None:
        if isinstance(item, ChatMessageDTO):
            return item if item.content.strip() else None

        if isinstance(item, dict):
            content = str(item.get("content", "")).strip()
            if not content:
                return None
            return ChatMessageDTO(
                content=content,
                sender=str(item.get("sender", "")).strip(),
                kind=str(item.get("kind", "text")).strip() or "text",
                is_new=bool(item.get("is_new", False)),
            )

        content = str(item).strip()
        if not content:
            return None
        return ChatMessageDTO(content=content)

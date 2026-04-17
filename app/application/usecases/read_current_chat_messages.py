from __future__ import annotations

from app.application.dto.read_messages_result import ChatMessageDTO, ReadMessagesResultDTO
from app.automation.exceptions import DriverError
from app.automation.protocols.wechat_driver import WeChatDriver


class ReadCurrentChatMessagesUseCase:
    def __init__(self, driver: WeChatDriver) -> None:
        self._driver = driver

    def execute(self) -> ReadMessagesResultDTO:
        try:
            payload = self._driver.read_current_chat_messages()
        except DriverError as exc:
            return ReadMessagesResultDTO(
                success=False,
                chat_title="",
                messages=[],
                message=str(exc),
            )

        messages = payload.get("messages", [])
        chat_title = payload.get("chat_title", "")
        if not isinstance(messages, list):
            messages = []
        normalized_messages = self._normalize_messages(messages)

        return ReadMessagesResultDTO(
            success=True,
            chat_title=str(chat_title),
            messages=normalized_messages,
            message=f"Read {len(normalized_messages)} message lines from the current chat.",
        )

    def _normalize_messages(self, messages: list[object]) -> list[ChatMessageDTO]:
        normalized: list[ChatMessageDTO] = []
        for item in messages:
            message = self._normalize_message(item)
            if message is None:
                continue
            normalized.append(message)
        return normalized

    def _normalize_message(self, item: object) -> ChatMessageDTO | None:
        if isinstance(item, ChatMessageDTO):
            if not item.content.strip():
                return None
            return item

        if isinstance(item, dict):
            content = str(item.get("content", "")).strip()
            if not content:
                return None

            sender = str(item.get("sender", "")).strip()
            kind = str(item.get("kind", "")).strip() or self._infer_kind(content)
            is_new = bool(item.get("is_new", False))
            return ChatMessageDTO(
                content=content,
                sender=sender,
                kind=kind,
                is_new=is_new,
            )

        content = str(item).strip()
        if not content:
            return None
        return ChatMessageDTO(content=content, kind=self._infer_kind(content))

    def _infer_kind(self, content: str) -> str:
        if content == "[非文本消息]":
            return "non_text"
        if "撤回了一条消息" in content:
            return "system"
        if "加入群聊" in content or "群公告" in content or "以下为新消息" in content:
            return "notification"
        return "text"

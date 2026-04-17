from __future__ import annotations

from dataclasses import dataclass, field

from app.application.dto.read_messages_result import ChatMessageDTO


@dataclass
class ChatSnapshotDTO:
    chat_title: str
    messages: list[ChatMessageDTO] = field(default_factory=list)


@dataclass
class ReadVisibleChatsResultDTO:
    success: bool
    chats: list[ChatSnapshotDTO] = field(default_factory=list)
    message: str = ""

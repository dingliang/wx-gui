from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChatMessageDTO:
    content: str
    kind: str = "text"
    sender: str = ""
    is_new: bool = False


@dataclass
class ReadMessagesResultDTO:
    success: bool
    chat_title: str
    messages: list[ChatMessageDTO] = field(default_factory=list)
    message: str = ""

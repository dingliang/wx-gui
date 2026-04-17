from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AutoReplyRuleDTO:
    trigger: str
    reply_text: str
    match_mode: str = "contains"


@dataclass
class AutoReplyActionDTO:
    chat_title: str
    trigger_content: str
    reply_text: str
    sender: str = ""
    message_signature: str = ""


@dataclass
class AutoReplyPlanResultDTO:
    actions: list[AutoReplyActionDTO] = field(default_factory=list)
    ignored_signatures: list[str] = field(default_factory=list)
    message: str = ""

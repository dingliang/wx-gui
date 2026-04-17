from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Attachment:
    path: Path


@dataclass
class MessageContent:
    text: str
    attachments: list[Attachment] = field(default_factory=list)

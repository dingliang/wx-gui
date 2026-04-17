from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SendMessageResultDTO:
    success: bool
    message: str

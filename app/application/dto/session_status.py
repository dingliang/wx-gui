from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SessionStatusDTO:
    is_running: bool
    is_logged_in: bool
    message: str

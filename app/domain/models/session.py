from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class WeChatSession:
    is_running: bool
    is_logged_in: bool
    client_version: str | None = None
    last_checked_at: datetime | None = None

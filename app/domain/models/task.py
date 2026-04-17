from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TaskStep:
    name: str
    target: str
    payload: dict[str, str] = field(default_factory=dict)


@dataclass
class AutomationTask:
    id: str
    name: str
    steps: list[TaskStep]
    created_at: datetime
    status: str = "draft"

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class AppSettings(BaseModel):
    app_name: str = "wx-gui"
    platform_name: str = "macOS"
    wechat_app_name: str = "微信"
    default_driver: str = "macos-accessibility"
    default_action_delay_ms: int = 300
    max_retry_count: int = 2
    screenshot_on_error: bool = True
    chat_match_similarity_threshold: float = 0.72
    data_dir: Path = Field(default_factory=lambda: Path.cwd() / "data")
    log_dir: Path = Field(default_factory=lambda: Path.cwd() / "data" / "logs")
    screenshot_dir: Path = Field(default_factory=lambda: Path.cwd() / "data" / "screenshots")


def load_settings() -> AppSettings:
    settings = AppSettings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    settings.screenshot_dir.mkdir(parents=True, exist_ok=True)
    return settings

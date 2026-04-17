from __future__ import annotations

from app.infrastructure.config.settings import load_settings


def test_load_settings_creates_data_directories() -> None:
    settings = load_settings()

    assert settings.data_dir.exists()
    assert settings.log_dir.exists()
    assert settings.screenshot_dir.exists()

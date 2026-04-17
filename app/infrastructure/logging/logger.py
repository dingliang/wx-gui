from __future__ import annotations

from pathlib import Path

from loguru import logger

from app.infrastructure.config.settings import AppSettings


def configure_logger(settings: AppSettings) -> None:
    logger.remove()
    log_path = Path(settings.log_dir) / "app.log"
    logger.add(log_path, rotation="10 MB", encoding="utf-8")


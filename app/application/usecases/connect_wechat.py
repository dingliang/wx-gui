from __future__ import annotations

from app.application.dto.session_status import SessionStatusDTO
from app.automation.exceptions import DriverError
from app.automation.protocols.wechat_driver import WeChatDriver


class ConnectWeChatUseCase:
    def __init__(self, driver: WeChatDriver) -> None:
        self._driver = driver

    @property
    def driver_name(self) -> str:
        return self._driver.name

    def execute(self) -> SessionStatusDTO:
        try:
            is_running = self._driver.is_running()
            is_logged_in = self._driver.is_logged_in() if is_running else False
            diagnostics = self._driver.capture_state()
            last_error = diagnostics.get("last_error", "").strip()
        except DriverError as exc:
            return SessionStatusDTO(
                is_running=False,
                is_logged_in=False,
                message=str(exc),
            )

        if last_error:
            message = last_error
        elif not is_running:
            message = "WeChat is not running on this Mac yet."
        elif not is_logged_in:
            message = "WeChat is running, but no logged-in session was detected."
        else:
            message = "WeChat is available and ready for automation."

        return SessionStatusDTO(
            is_running=is_running,
            is_logged_in=is_logged_in,
            message=message,
        )

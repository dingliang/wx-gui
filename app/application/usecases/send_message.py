from __future__ import annotations

from app.application.dto.send_message_result import SendMessageResultDTO
from app.automation.exceptions import DriverError
from app.automation.protocols.wechat_driver import WeChatDriver


class SendMessageUseCase:
    def __init__(self, driver: WeChatDriver) -> None:
        self._driver = driver

    def execute(self, target: str, text: str) -> SendMessageResultDTO:
        normalized_target = target.strip()
        normalized_text = text.strip()

        if not normalized_target:
            return SendMessageResultDTO(success=False, message="Please provide a target chat name.")
        if not normalized_text:
            return SendMessageResultDTO(success=False, message="Please provide a message to send.")

        try:
            self._driver.open_chat(normalized_target)
            self._driver.send_text(normalized_text)
        except DriverError as exc:
            return SendMessageResultDTO(success=False, message=str(exc))

        return SendMessageResultDTO(
            success=True,
            message=f'Message sent to "{normalized_target}".',
        )

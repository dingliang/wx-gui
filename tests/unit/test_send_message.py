from __future__ import annotations

from app.application.usecases.send_message import SendMessageUseCase


class FakeDriver:
    name = "fake"

    def __init__(self) -> None:
        self.opened: list[str] = []
        self.sent: list[str] = []

    def is_running(self) -> bool:
        return True

    def is_logged_in(self) -> bool:
        return True

    def activate(self) -> None:
        return None

    def search_chat(self, keyword: str) -> bool:
        return True

    def open_chat(self, name: str) -> None:
        self.opened.append(name)

    def send_text(self, text: str) -> None:
        self.sent.append(text)

    def send_file(self, file_path: str) -> None:
        return None

    def capture_state(self) -> dict[str, str]:
        return {}


def test_send_message_use_case_sends_to_driver() -> None:
    driver = FakeDriver()
    use_case = SendMessageUseCase(driver=driver)

    result = use_case.execute(target="Alice", text="Hello")

    assert result.success is True
    assert driver.opened == ["Alice"]
    assert driver.sent == ["Hello"]

from __future__ import annotations

import subprocess

from app.automation.exceptions import AccessibilityPermissionError, DriverError


class AppleScriptDriver:
    name = "macos-applescript"

    def run(self, script: str, timeout: float = 5.0) -> str:
        try:
            completed = subprocess.run(
                ["osascript", "-e", script],
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise AccessibilityPermissionError(
                "AppleScript call timed out. Please allow Accessibility and Automation access for Terminal/Codex."
            ) from exc

        if completed.returncode != 0:
            error_message = completed.stderr.strip() or "AppleScript execution failed."
            lowered = error_message.lower()
            if (
                "not authorized" in lowered
                or "not permitted" in lowered
                or "不允许辅助访问" in error_message
                or "辅助访问" in error_message
            ):
                raise AccessibilityPermissionError(error_message)
            raise DriverError(error_message)
        return completed.stdout.strip()

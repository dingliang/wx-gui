class DriverError(Exception):
    """Base automation driver error."""


class AccessibilityPermissionError(DriverError):
    """Raised when macOS accessibility automation permissions are missing."""


class WindowNotFoundError(DriverError):
    """Raised when the WeChat window cannot be located."""


class LoginRequiredError(DriverError):
    """Raised when WeChat is open but not logged in."""


class TargetNotFoundError(DriverError):
    """Raised when a contact or chat cannot be found."""

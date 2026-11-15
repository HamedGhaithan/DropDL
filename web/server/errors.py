"""Exceptions shared by the server modules."""
from __future__ import annotations


class ApiError(Exception):
    """An error the API reports to the browser as {"error": {"code", "message"}}.

    `code` is stable and machine-readable (the web UI translates it); `message` is the English fallback.
    """

    def __init__(self, status: int, code: str, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retry_after = retry_after


class RunError(Exception):
    """A download failed. Carries the same stable code and a message that is safe to show to the visitor."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

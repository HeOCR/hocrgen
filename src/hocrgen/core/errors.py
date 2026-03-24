from __future__ import annotations

from typing import Any


class HocrgenError(Exception):
    """Base error for hocrgen."""


class ConfigValidationError(HocrgenError):
    def __init__(self, message: str, details: list[Any] | None = None) -> None:
        self.message = message
        self.details = details or []
        super().__init__(message, self.details)

    def __str__(self) -> str:
        if not self.details:
            return self.message
        return f"{self.message}: {self.details}"


class StageExecutionError(HocrgenError):
    """Raised when a pipeline stage cannot complete."""

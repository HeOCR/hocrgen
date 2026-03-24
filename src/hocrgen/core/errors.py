from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class HocrgenError(Exception):
    """Base error for hocrgen."""


@dataclass
class ConfigValidationError(HocrgenError):
    message: str
    details: list[Any] = field(default_factory=list)

    def __str__(self) -> str:
        if not self.details:
            return self.message
        return f"{self.message}: {self.details}"


class StageExecutionError(HocrgenError):
    """Raised when a pipeline stage cannot complete."""

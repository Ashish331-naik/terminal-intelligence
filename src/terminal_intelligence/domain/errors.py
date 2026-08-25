"""Errors raised while constructing or decoding domain values."""

from __future__ import annotations


class DomainValidationError(ValueError):
    """Raised when a domain model violates its value or schema contract."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        self.field = field
        super().__init__(message)

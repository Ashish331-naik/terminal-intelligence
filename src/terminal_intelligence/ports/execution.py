"""Ports used by application execution workflows."""

from typing import Protocol

from terminal_intelligence.domain import ExecutionRequest, ExecutionResult


class CommandExecutor(Protocol):
    """Execute one immutable command request."""

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Return the complete result after the child has been reaped."""

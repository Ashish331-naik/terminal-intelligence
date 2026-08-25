"""Framework-independent domain models for Terminal Intelligence."""

from terminal_intelligence.domain.enums import (
    ApprovalOutcome,
    CommandRisk,
    ExecutionStatus,
    VerificationStatus,
)
from terminal_intelligence.domain.errors import DomainValidationError
from terminal_intelligence.domain.models import (
    ApprovalDecision,
    CommandProposal,
    ExecutionRequest,
    ExecutionResult,
    UserRequest,
    VerificationResult,
)

__all__ = [
    "ApprovalDecision",
    "ApprovalOutcome",
    "CommandProposal",
    "CommandRisk",
    "DomainValidationError",
    "ExecutionRequest",
    "ExecutionResult",
    "ExecutionStatus",
    "UserRequest",
    "VerificationResult",
    "VerificationStatus",
]

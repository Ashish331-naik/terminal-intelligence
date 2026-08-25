"""Enumerations used by the Stage 1 domain models."""

from enum import StrEnum


class CommandRisk(StrEnum):
    """Risk severity assigned to a command proposal."""

    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalOutcome(StrEnum):
    """Recorded outcome of an approval decision."""

    APPROVED = "approved"
    REJECTED = "rejected"


class ExecutionStatus(StrEnum):
    """Outcome of an execution attempt."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    START_FAILED = "start_failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class VerificationStatus(StrEnum):
    """Outcome of checking an execution result."""

    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"

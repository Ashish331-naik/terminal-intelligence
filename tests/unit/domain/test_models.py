"""Construction, defaults, immutability, and edge cases for domain models."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from terminal_intelligence.domain import (
    ApprovalDecision,
    ApprovalOutcome,
    CommandProposal,
    CommandRisk,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    UserRequest,
    VerificationResult,
    VerificationStatus,
)
from terminal_intelligence.domain.errors import DomainValidationError

REQUEST_ID = UUID("00000000-0000-0000-0000-000000000001")
PROPOSAL_ID = UUID("00000000-0000-0000-0000-000000000002")
DECISION_ID = UUID("00000000-0000-0000-0000-000000000003")
EXECUTION_ID = UUID("00000000-0000-0000-0000-000000000004")
RESULT_ID = UUID("00000000-0000-0000-0000-000000000005")
VERIFICATION_ID = UUID("00000000-0000-0000-0000-000000000006")
SUBMITTED_AT = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
FINISHED_AT = datetime(2026, 8, 25, 12, 1, tzinfo=UTC)


def test_valid_models_and_defaults() -> None:
    request = UserRequest(REQUEST_ID, "find port 8000", SUBMITTED_AT)
    proposal = CommandProposal(PROPOSAL_ID, REQUEST_ID, ("lsof", "-i", ":8000"), SUBMITTED_AT)
    approval = ApprovalDecision(
        DECISION_ID,
        REQUEST_ID,
        PROPOSAL_ID,
        ApprovalOutcome.APPROVED,
        "user:alice",
        SUBMITTED_AT,
    )
    execution = ExecutionRequest(
        EXECUTION_ID,
        REQUEST_ID,
        PROPOSAL_ID,
        proposal.argv,
        SUBMITTED_AT,
        approval.decision_id,
        "/tmp",
    )
    result = ExecutionResult(
        RESULT_ID,
        REQUEST_ID,
        EXECUTION_ID,
        ExecutionStatus.SUCCEEDED,
        FINISHED_AT,
        SUBMITTED_AT,
        0,
        "output",
        "warning",
    )
    verification = VerificationResult(
        VERIFICATION_ID,
        REQUEST_ID,
        EXECUTION_ID,
        VerificationStatus.PASSED,
        FINISHED_AT,
    )

    assert request.text == "find port 8000"
    assert proposal.risk is CommandRisk.UNKNOWN
    assert approval.reason is None
    assert execution.approval_decision_id == DECISION_ID
    assert result.stderr == "warning"
    assert verification.details is None


def test_models_are_immutable_and_slot_based() -> None:
    request = UserRequest(REQUEST_ID, "request", SUBMITTED_AT)

    with pytest.raises(AttributeError):
        setattr(request, "text", "changed")  # noqa: B010
    with pytest.raises((AttributeError, TypeError)):
        setattr(request, "new_field", "not allowed")  # noqa: B010


def test_command_argv_preserves_empty_and_unicode_arguments() -> None:
    proposal = CommandProposal(
        PROPOSAL_ID,
        REQUEST_ID,
        ("printf", "", "hello world", "привет"),
        SUBMITTED_AT,
    )

    assert proposal.argv == ("printf", "", "hello world", "привет")


def test_failed_execution_can_use_nonzero_exit_code_without_error_text() -> None:
    result = ExecutionResult(
        RESULT_ID,
        REQUEST_ID,
        EXECUTION_ID,
        ExecutionStatus.FAILED,
        FINISHED_AT,
        SUBMITTED_AT,
        2,
    )

    assert result.exit_code == 2
    assert result.error is None


def test_execution_result_defaults_output_to_empty_strings() -> None:
    result = ExecutionResult(
        RESULT_ID,
        REQUEST_ID,
        EXECUTION_ID,
        ExecutionStatus.SUCCEEDED,
        FINISHED_AT,
        exit_code=0,
    )

    assert result.stdout == ""
    assert result.stderr == ""


def test_rejected_approval_requires_reason() -> None:
    with pytest.raises(DomainValidationError, match="require a reason"):
        ApprovalDecision(
            DECISION_ID,
            REQUEST_ID,
            PROPOSAL_ID,
            ApprovalOutcome.REJECTED,
            "user:alice",
            SUBMITTED_AT,
        )


def test_failed_and_inconclusive_verification_require_details() -> None:
    for status in (VerificationStatus.FAILED, VerificationStatus.INCONCLUSIVE):
        with pytest.raises(DomainValidationError, match="requires details"):
            VerificationResult(VERIFICATION_ID, REQUEST_ID, EXECUTION_ID, status, FINISHED_AT)


def test_execution_times_must_be_ordered() -> None:
    with pytest.raises(DomainValidationError, match="cannot precede"):
        ExecutionResult(
            RESULT_ID,
            REQUEST_ID,
            EXECUTION_ID,
            ExecutionStatus.SUCCEEDED,
            SUBMITTED_AT,
            FINISHED_AT,
            0,
        )

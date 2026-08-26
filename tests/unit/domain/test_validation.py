"""Invalid-value and enum validation tests for domain models."""

from datetime import UTC, datetime, timedelta, timezone
from math import inf, nan
from typing import cast
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
EXECUTION_ID = UUID("00000000-0000-0000-0000-000000000004")
SUBMITTED_AT = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
FINISHED_AT = datetime(2026, 8, 25, 12, 1, tzinfo=UTC)


def test_request_rejects_blank_text() -> None:
    with pytest.raises(DomainValidationError, match="text"):
        UserRequest(REQUEST_ID, "  ", SUBMITTED_AT)


def test_request_rejects_naive_timestamp() -> None:
    with pytest.raises(DomainValidationError, match="timezone-aware"):
        UserRequest(REQUEST_ID, "request", datetime(2026, 8, 25, 12, 0))


def test_request_rejects_non_uuid_identifier() -> None:
    with pytest.raises(DomainValidationError, match="request_id"):
        UserRequest(cast(UUID, "not-a-uuid"), "request", SUBMITTED_AT)


def test_proposal_rejects_empty_or_nul_argv() -> None:
    with pytest.raises(DomainValidationError, match="executable"):
        CommandProposal(PROPOSAL_ID, REQUEST_ID, (), SUBMITTED_AT)
    with pytest.raises(DomainValidationError, match="executable"):
        CommandProposal(PROPOSAL_ID, REQUEST_ID, ("  ",), SUBMITTED_AT)
    with pytest.raises(DomainValidationError, match="NUL"):
        CommandProposal(PROPOSAL_ID, REQUEST_ID, ("echo", "bad\x00value"), SUBMITTED_AT)


def test_proposal_rejects_mutable_argv() -> None:
    with pytest.raises(DomainValidationError, match="immutable tuple"):
        CommandProposal(PROPOSAL_ID, REQUEST_ID, cast(tuple[str, ...], ["echo"]), SUBMITTED_AT)


def test_proposal_rejects_invalid_risk_enum() -> None:
    with pytest.raises(DomainValidationError, match="risk"):
        CommandProposal(
            PROPOSAL_ID,
            REQUEST_ID,
            ("echo",),
            SUBMITTED_AT,
            cast(CommandRisk, "unsafe-value"),
        )


def test_execution_request_rejects_blank_optional_values() -> None:
    with pytest.raises(DomainValidationError, match="working_directory"):
        ExecutionRequest(
            EXECUTION_ID,
            REQUEST_ID,
            PROPOSAL_ID,
            ("echo",),
            SUBMITTED_AT,
            working_directory="  ",
        )


def test_execution_request_rejects_invalid_timeout_and_environment() -> None:
    for timeout in (0, -1, inf, nan, True):
        with pytest.raises(DomainValidationError, match="timeout_seconds"):
            ExecutionRequest(
                EXECUTION_ID,
                REQUEST_ID,
                PROPOSAL_ID,
                ("echo",),
                SUBMITTED_AT,
                timeout_seconds=timeout,
            )

    with pytest.raises(DomainValidationError, match="unique"):
        ExecutionRequest(
            EXECUTION_ID,
            REQUEST_ID,
            PROPOSAL_ID,
            ("echo",),
            SUBMITTED_AT,
            environment=(("KEY", "one"), ("KEY", "two")),
        )

    with pytest.raises(DomainValidationError, match="NUL"):
        ExecutionRequest(
            EXECUTION_ID,
            REQUEST_ID,
            PROPOSAL_ID,
            ("echo",),
            SUBMITTED_AT,
            environment=(("KEY", "bad\x00value"),),
        )


def test_execution_result_rejects_invalid_status_combinations() -> None:
    with pytest.raises(DomainValidationError, match="exit_code 0"):
        ExecutionResult(
            UUID("00000000-0000-0000-0000-000000000005"),
            REQUEST_ID,
            EXECUTION_ID,
            ExecutionStatus.FAILED,
            FINISHED_AT,
            exit_code=0,
        )
    with pytest.raises(DomainValidationError, match="exit_code or error"):
        ExecutionResult(
            UUID("00000000-0000-0000-0000-000000000005"),
            REQUEST_ID,
            EXECUTION_ID,
            ExecutionStatus.FAILED,
            FINISHED_AT,
        )
    with pytest.raises(DomainValidationError, match="requires an error"):
        ExecutionResult(
            UUID("00000000-0000-0000-0000-000000000005"),
            REQUEST_ID,
            EXECUTION_ID,
            ExecutionStatus.TIMED_OUT,
            FINISHED_AT,
        )


def test_start_failed_result_rejects_started_process_state() -> None:
    for kwargs in (
        {"exit_code": 1},
        {"started_at": SUBMITTED_AT},
        {"stdout": "unexpected output"},
        {"stderr": "unexpected error"},
    ):
        with pytest.raises(DomainValidationError):
            ExecutionResult(
                UUID("00000000-0000-0000-0000-000000000005"),
                REQUEST_ID,
                EXECUTION_ID,
                ExecutionStatus.START_FAILED,
                FINISHED_AT,
                error="could not start",
                **kwargs,
            )


def test_execution_result_rejects_bool_exit_code() -> None:
    with pytest.raises(DomainValidationError, match="exit_code"):
        ExecutionResult(
            UUID("00000000-0000-0000-0000-000000000005"),
            REQUEST_ID,
            EXECUTION_ID,
            ExecutionStatus.SUCCEEDED,
            FINISHED_AT,
            exit_code=cast(int, True),
        )


def test_execution_result_rejects_negative_duration() -> None:
    with pytest.raises(DomainValidationError, match="duration_ms"):
        ExecutionResult(
            UUID("00000000-0000-0000-0000-000000000005"),
            REQUEST_ID,
            EXECUTION_ID,
            ExecutionStatus.SUCCEEDED,
            FINISHED_AT,
            exit_code=0,
            duration_ms=-1,
        )


def test_verification_rejects_invalid_status_enum() -> None:
    with pytest.raises(DomainValidationError, match="status"):
        VerificationResult(
            UUID("00000000-0000-0000-0000-000000000006"),
            REQUEST_ID,
            EXECUTION_ID,
            cast(VerificationStatus, "unknown"),
            FINISHED_AT,
        )


def test_approval_and_execution_enums_reject_unknown_values() -> None:
    with pytest.raises(DomainValidationError, match="outcome"):
        ApprovalDecision(
            UUID("00000000-0000-0000-0000-000000000003"),
            REQUEST_ID,
            PROPOSAL_ID,
            cast(ApprovalOutcome, "maybe"),
            "user:alice",
            SUBMITTED_AT,
        )

    with pytest.raises(DomainValidationError, match="status"):
        ExecutionResult(
            UUID("00000000-0000-0000-0000-000000000005"),
            REQUEST_ID,
            EXECUTION_ID,
            cast(ExecutionStatus, "unknown"),
            FINISHED_AT,
            exit_code=0,
        )


def test_non_utc_timestamp_is_rejected() -> None:
    non_utc = datetime(2026, 8, 25, 13, 0, tzinfo=timezone(timedelta(hours=1)))

    with pytest.raises(DomainValidationError, match="UTC"):
        UserRequest(REQUEST_ID, "request", non_utc)


def test_enum_members_are_closed_sets() -> None:
    assert {member.value for member in CommandRisk} == {
        "unknown",
        "low",
        "medium",
        "high",
        "critical",
    }
    assert {member.value for member in ApprovalOutcome} == {"approved", "rejected"}
    assert {member.value for member in ExecutionStatus} == {
        "succeeded",
        "failed",
        "start_failed",
        "timed_out",
        "cancelled",
    }
    assert {member.value for member in VerificationStatus} == {
        "passed",
        "failed",
        "inconclusive",
    }

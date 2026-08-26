"""Serialization and deserialization tests for domain models."""

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


def test_user_request_round_trips() -> None:
    model = UserRequest(REQUEST_ID, "find port 8000", SUBMITTED_AT)

    assert UserRequest.from_dict(model.to_dict()) == model
    assert model.to_dict()["submitted_at"] == "2026-08-25T12:00:00Z"


def test_command_proposal_round_trips_and_serializes_argv_as_array() -> None:
    model = CommandProposal(
        PROPOSAL_ID,
        REQUEST_ID,
        ("lsof", "-i", ":8000"),
        SUBMITTED_AT,
        CommandRisk.HIGH,
        "Inspect the process using the port.",
    )

    payload = model.to_dict()

    assert payload["argv"] == ["lsof", "-i", ":8000"]
    assert payload["risk"] == "high"
    assert CommandProposal.from_dict(payload) == model


def test_all_remaining_models_round_trip() -> None:
    approval = ApprovalDecision(
        DECISION_ID,
        REQUEST_ID,
        PROPOSAL_ID,
        ApprovalOutcome.REJECTED,
        "user:alice",
        SUBMITTED_AT,
        "The request was declined.",
    )
    execution = ExecutionRequest(
        EXECUTION_ID,
        REQUEST_ID,
        PROPOSAL_ID,
        ("lsof", "-i", ":8000"),
        SUBMITTED_AT,
        DECISION_ID,
        "/tmp",
        3.5,
        (("LANG", "C.UTF-8"),),
    )
    result = ExecutionResult(
        RESULT_ID,
        REQUEST_ID,
        EXECUTION_ID,
        ExecutionStatus.TIMED_OUT,
        FINISHED_AT,
        SUBMITTED_AT,
        error="The process exceeded its time limit.",
        duration_ms=3500,
        stdout_truncated=True,
        stderr_truncated=False,
    )
    verification = VerificationResult(
        VERIFICATION_ID,
        REQUEST_ID,
        EXECUTION_ID,
        VerificationStatus.INCONCLUSIVE,
        FINISHED_AT,
        "The result could not be verified.",
    )

    assert ApprovalDecision.from_dict(approval.to_dict()) == approval
    assert ExecutionRequest.from_dict(execution.to_dict()) == execution
    assert ExecutionResult.from_dict(result.to_dict()) == result
    assert execution.to_dict()["environment"] == [["LANG", "C.UTF-8"]]
    assert result.to_dict()["duration_ms"] == 3500
    assert result.to_dict()["stdout_truncated"] is True
    assert VerificationResult.from_dict(verification.to_dict()) == verification


def test_optional_fields_are_serialized_as_null() -> None:
    payloads = [
        CommandProposal(PROPOSAL_ID, REQUEST_ID, ("echo",), SUBMITTED_AT).to_dict(),
        ApprovalDecision(
            DECISION_ID,
            REQUEST_ID,
            PROPOSAL_ID,
            ApprovalOutcome.APPROVED,
            "user:alice",
            SUBMITTED_AT,
        ).to_dict(),
        ExecutionRequest(
            EXECUTION_ID,
            REQUEST_ID,
            PROPOSAL_ID,
            ("echo",),
            SUBMITTED_AT,
        ).to_dict(),
        ExecutionResult(
            RESULT_ID,
            REQUEST_ID,
            EXECUTION_ID,
            ExecutionStatus.SUCCEEDED,
            FINISHED_AT,
            exit_code=0,
        ).to_dict(),
        VerificationResult(
            VERIFICATION_ID,
            REQUEST_ID,
            EXECUTION_ID,
            VerificationStatus.PASSED,
            FINISHED_AT,
        ).to_dict(),
    ]

    assert payloads[0]["rationale"] is None
    assert payloads[1]["reason"] is None
    assert payloads[2]["approval_decision_id"] is None
    assert payloads[2]["working_directory"] is None
    assert payloads[3]["started_at"] is None
    assert payloads[3]["error"] is None
    assert payloads[4]["details"] is None


def test_optional_serialized_fields_can_be_omitted() -> None:
    proposal_data = CommandProposal(PROPOSAL_ID, REQUEST_ID, ("echo",), SUBMITTED_AT).to_dict()
    proposal_data.pop("risk")
    proposal_data.pop("rationale")

    execution_data = ExecutionRequest(
        EXECUTION_ID, REQUEST_ID, PROPOSAL_ID, ("echo",), SUBMITTED_AT
    ).to_dict()
    execution_data.pop("approval_decision_id")
    execution_data.pop("working_directory")

    result_data = ExecutionResult(
        RESULT_ID,
        REQUEST_ID,
        EXECUTION_ID,
        ExecutionStatus.SUCCEEDED,
        FINISHED_AT,
        exit_code=0,
    ).to_dict()
    result_data.pop("started_at")
    result_data.pop("stdout")
    result_data.pop("stderr")
    result_data.pop("error")

    assert CommandProposal.from_dict(proposal_data).risk is CommandRisk.UNKNOWN
    assert ExecutionRequest.from_dict(execution_data).approval_decision_id is None
    parsed_result = ExecutionResult.from_dict(result_data)
    assert parsed_result.stdout == ""
    assert parsed_result.stderr == ""
    assert parsed_result.error is None


def test_deserialization_rejects_unknown_or_missing_schema_fields() -> None:
    payload = UserRequest(REQUEST_ID, "request", SUBMITTED_AT).to_dict()

    unknown = dict(payload)
    unknown["unexpected"] = True
    with pytest.raises(DomainValidationError, match="unknown fields"):
        UserRequest.from_dict(unknown)

    missing = dict(payload)
    del missing["request_id"]
    with pytest.raises(DomainValidationError, match="request_id"):
        UserRequest.from_dict(missing)

    wrong_version = dict(payload)
    wrong_version["schema_version"] = 2
    with pytest.raises(DomainValidationError, match="schema_version"):
        UserRequest.from_dict(wrong_version)

    boolean_version = dict(payload)
    boolean_version["schema_version"] = True
    with pytest.raises(DomainValidationError, match="schema_version"):
        UserRequest.from_dict(boolean_version)


def test_deserialization_rejects_invalid_uuid_enum_timestamp_and_argv() -> None:
    proposal = CommandProposal(PROPOSAL_ID, REQUEST_ID, ("echo",), SUBMITTED_AT).to_dict()

    invalid_uuid = dict(proposal)
    invalid_uuid["proposal_id"] = "not-a-uuid"
    with pytest.raises(DomainValidationError, match="proposal_id"):
        CommandProposal.from_dict(invalid_uuid)

    invalid_enum = dict(proposal)
    invalid_enum["risk"] = "unknown-risk"
    with pytest.raises(DomainValidationError, match="risk"):
        CommandProposal.from_dict(invalid_enum)

    invalid_timestamp = dict(proposal)
    invalid_timestamp["proposed_at"] = "2026-08-25T12:00:00"
    with pytest.raises(DomainValidationError, match="proposed_at"):
        CommandProposal.from_dict(invalid_timestamp)

    invalid_argv = dict(proposal)
    invalid_argv["argv"] = "echo"
    with pytest.raises(DomainValidationError, match="serialized array"):
        CommandProposal.from_dict(invalid_argv)


def test_deserialization_rejects_wrong_output_types() -> None:
    result = ExecutionResult(
        RESULT_ID,
        REQUEST_ID,
        EXECUTION_ID,
        ExecutionStatus.SUCCEEDED,
        FINISHED_AT,
        exit_code=0,
    ).to_dict()

    invalid_stdout = dict(result)
    invalid_stdout["stdout"] = 42
    with pytest.raises(DomainValidationError, match="stdout"):
        ExecutionResult.from_dict(invalid_stdout)

    invalid_exit_code = dict(result)
    invalid_exit_code["exit_code"] = True
    with pytest.raises(DomainValidationError, match="exit_code"):
        ExecutionResult.from_dict(invalid_exit_code)

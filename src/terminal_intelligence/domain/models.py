"""Immutable, framework-independent Stage 1 domain models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from uuid import UUID

from terminal_intelligence.domain.enums import (
    ApprovalOutcome,
    CommandRisk,
    ExecutionStatus,
    VerificationStatus,
)
from terminal_intelligence.domain.errors import DomainValidationError

SerializedModel = dict[str, object]
_MISSING = object()
_SCHEMA_VERSION = 1


def _ensure_mapping(data: Mapping[str, object]) -> None:
    if not isinstance(data, Mapping):
        raise DomainValidationError("serialized model must be a mapping")
    if any(not isinstance(key, str) for key in data):
        raise DomainValidationError("serialized model keys must be strings")


def _ensure_schema(data: Mapping[str, object], fields: set[str]) -> None:
    _ensure_mapping(data)
    schema_version = data.get("schema_version", _MISSING)
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != _SCHEMA_VERSION
    ):
        raise DomainValidationError("unsupported or missing schema_version", field="schema_version")
    unknown = set(data) - fields
    if unknown:
        names = ", ".join(sorted(unknown))
        raise DomainValidationError(f"unknown fields: {names}")


def _required(data: Mapping[str, object], field: str) -> object:
    value = data.get(field, _MISSING)
    if value is _MISSING:
        raise DomainValidationError(f"missing required field: {field}", field=field)
    return value


def _required_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainValidationError(f"{field} must be a non-empty string", field=field)
    return value


def _optional_string(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _required_string(value, field)


def _uuid(value: object, field: str) -> UUID:
    if not isinstance(value, UUID):
        raise DomainValidationError(f"{field} must be a UUID", field=field)
    return value


def _serialized_uuid(value: object, field: str) -> UUID:
    if not isinstance(value, str):
        raise DomainValidationError(f"{field} must be a UUID string", field=field)
    try:
        return UUID(value)
    except (ValueError, AttributeError, TypeError) as error:
        raise DomainValidationError(f"{field} must be a UUID string", field=field) from error


def _datetime(value: object, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise DomainValidationError(f"{field} must be a datetime", field=field)
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainValidationError(f"{field} must be timezone-aware UTC", field=field)
    if value.utcoffset() != timedelta(0):
        raise DomainValidationError(f"{field} must be UTC", field=field)
    return value


def _serialized_datetime(value: object, field: str) -> datetime:
    text = _required_string(value, field)
    if "T" not in text:
        raise DomainValidationError(f"{field} must be an RFC 3339 datetime", field=field)
    normalized = f"{text[:-1]}+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise DomainValidationError(f"{field} must be an RFC 3339 datetime", field=field) from error
    return _datetime(parsed, field)


def _datetime_value(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _enum[E: Enum](value: object, enum_type: type[E], field: str) -> E:
    if not isinstance(value, enum_type):
        raise DomainValidationError(f"{field} has an invalid value", field=field)
    return value


def _serialized_enum[E: Enum](value: object, enum_type: type[E], field: str) -> E:
    if not isinstance(value, str):
        raise DomainValidationError(f"{field} must be a string enum value", field=field)
    try:
        return enum_type(value)
    except ValueError as error:
        raise DomainValidationError(f"{field} has an invalid value", field=field) from error


def _argv(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise DomainValidationError("argv must be an immutable tuple", field="argv")
    if not value or not isinstance(value[0], str) or not value[0].strip():
        raise DomainValidationError("argv must contain a non-empty executable", field="argv")
    for argument in value:
        if not isinstance(argument, str):
            raise DomainValidationError("argv entries must be strings", field="argv")
        if "\x00" in argument:
            raise DomainValidationError(
                "argv entries must not contain NUL characters", field="argv"
            )
    return value


def _serialized_argv(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise DomainValidationError("argv must be a serialized array", field="argv")
    return tuple(value)


def _optional_error(value: object, field: str = "error") -> str | None:
    return _optional_string(value, field)


@dataclass(frozen=True, slots=True)
class UserRequest:
    """The original natural-language request supplied by a user."""

    request_id: UUID
    text: str
    submitted_at: datetime

    def __post_init__(self) -> None:
        _uuid(self.request_id, "request_id")
        _required_string(self.text, "text")
        _datetime(self.submitted_at, "submitted_at")

    def to_dict(self) -> SerializedModel:
        return {
            "schema_version": _SCHEMA_VERSION,
            "request_id": str(self.request_id),
            "text": self.text,
            "submitted_at": _datetime_value(self.submitted_at),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> UserRequest:
        fields = {"schema_version", "request_id", "text", "submitted_at"}
        _ensure_schema(data, fields)
        return cls(
            request_id=_serialized_uuid(_required(data, "request_id"), "request_id"),
            text=_required_string(_required(data, "text"), "text"),
            submitted_at=_serialized_datetime(_required(data, "submitted_at"), "submitted_at"),
        )


@dataclass(frozen=True, slots=True)
class CommandProposal:
    """An immutable candidate argv for a user request."""

    proposal_id: UUID
    request_id: UUID
    argv: tuple[str, ...]
    proposed_at: datetime
    risk: CommandRisk = CommandRisk.UNKNOWN
    rationale: str | None = None

    def __post_init__(self) -> None:
        _uuid(self.proposal_id, "proposal_id")
        _uuid(self.request_id, "request_id")
        _argv(self.argv)
        _datetime(self.proposed_at, "proposed_at")
        _enum(self.risk, CommandRisk, "risk")
        _optional_string(self.rationale, "rationale")

    def to_dict(self) -> SerializedModel:
        return {
            "schema_version": _SCHEMA_VERSION,
            "proposal_id": str(self.proposal_id),
            "request_id": str(self.request_id),
            "argv": list(self.argv),
            "proposed_at": _datetime_value(self.proposed_at),
            "risk": self.risk.value,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> CommandProposal:
        fields = {
            "schema_version",
            "proposal_id",
            "request_id",
            "argv",
            "proposed_at",
            "risk",
            "rationale",
        }
        _ensure_schema(data, fields)
        return cls(
            proposal_id=_serialized_uuid(_required(data, "proposal_id"), "proposal_id"),
            request_id=_serialized_uuid(_required(data, "request_id"), "request_id"),
            argv=_serialized_argv(_required(data, "argv")),
            proposed_at=_serialized_datetime(_required(data, "proposed_at"), "proposed_at"),
            risk=_serialized_enum(data.get("risk", CommandRisk.UNKNOWN.value), CommandRisk, "risk"),
            rationale=_optional_string(data.get("rationale"), "rationale"),
        )


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    """A recorded approval outcome for a command proposal."""

    decision_id: UUID
    request_id: UUID
    proposal_id: UUID
    outcome: ApprovalOutcome
    actor_id: str
    decided_at: datetime
    reason: str | None = None

    def __post_init__(self) -> None:
        _uuid(self.decision_id, "decision_id")
        _uuid(self.request_id, "request_id")
        _uuid(self.proposal_id, "proposal_id")
        _enum(self.outcome, ApprovalOutcome, "outcome")
        _required_string(self.actor_id, "actor_id")
        _datetime(self.decided_at, "decided_at")
        reason = _optional_string(self.reason, "reason")
        if self.outcome is ApprovalOutcome.REJECTED and reason is None:
            raise DomainValidationError("rejected decisions require a reason", field="reason")

    def to_dict(self) -> SerializedModel:
        return {
            "schema_version": _SCHEMA_VERSION,
            "decision_id": str(self.decision_id),
            "request_id": str(self.request_id),
            "proposal_id": str(self.proposal_id),
            "outcome": self.outcome.value,
            "actor_id": self.actor_id,
            "decided_at": _datetime_value(self.decided_at),
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ApprovalDecision:
        fields = {
            "schema_version",
            "decision_id",
            "request_id",
            "proposal_id",
            "outcome",
            "actor_id",
            "decided_at",
            "reason",
        }
        _ensure_schema(data, fields)
        return cls(
            decision_id=_serialized_uuid(_required(data, "decision_id"), "decision_id"),
            request_id=_serialized_uuid(_required(data, "request_id"), "request_id"),
            proposal_id=_serialized_uuid(_required(data, "proposal_id"), "proposal_id"),
            outcome=_serialized_enum(_required(data, "outcome"), ApprovalOutcome, "outcome"),
            actor_id=_required_string(_required(data, "actor_id"), "actor_id"),
            decided_at=_serialized_datetime(_required(data, "decided_at"), "decided_at"),
            reason=_optional_string(data.get("reason"), "reason"),
        )


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    """An immutable command snapshot prepared for an execution adapter."""

    execution_request_id: UUID
    request_id: UUID
    proposal_id: UUID
    argv: tuple[str, ...]
    requested_at: datetime
    approval_decision_id: UUID | None = None
    working_directory: str | None = None

    def __post_init__(self) -> None:
        _uuid(self.execution_request_id, "execution_request_id")
        _uuid(self.request_id, "request_id")
        _uuid(self.proposal_id, "proposal_id")
        _argv(self.argv)
        _datetime(self.requested_at, "requested_at")
        if self.approval_decision_id is not None:
            _uuid(self.approval_decision_id, "approval_decision_id")
        _optional_string(self.working_directory, "working_directory")

    def to_dict(self) -> SerializedModel:
        return {
            "schema_version": _SCHEMA_VERSION,
            "execution_request_id": str(self.execution_request_id),
            "request_id": str(self.request_id),
            "proposal_id": str(self.proposal_id),
            "argv": list(self.argv),
            "requested_at": _datetime_value(self.requested_at),
            "approval_decision_id": (
                str(self.approval_decision_id) if self.approval_decision_id is not None else None
            ),
            "working_directory": self.working_directory,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ExecutionRequest:
        fields = {
            "schema_version",
            "execution_request_id",
            "request_id",
            "proposal_id",
            "argv",
            "requested_at",
            "approval_decision_id",
            "working_directory",
        }
        _ensure_schema(data, fields)
        raw_approval_id = data.get("approval_decision_id")
        return cls(
            execution_request_id=_serialized_uuid(
                _required(data, "execution_request_id"), "execution_request_id"
            ),
            request_id=_serialized_uuid(_required(data, "request_id"), "request_id"),
            proposal_id=_serialized_uuid(_required(data, "proposal_id"), "proposal_id"),
            argv=_serialized_argv(_required(data, "argv")),
            requested_at=_serialized_datetime(_required(data, "requested_at"), "requested_at"),
            approval_decision_id=(
                None
                if raw_approval_id is None
                else _serialized_uuid(raw_approval_id, "approval_decision_id")
            ),
            working_directory=_optional_string(data.get("working_directory"), "working_directory"),
        )


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """The captured outcome of one execution attempt."""

    result_id: UUID
    request_id: UUID
    execution_request_id: UUID
    status: ExecutionStatus
    finished_at: datetime
    started_at: datetime | None = None
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None

    def __post_init__(self) -> None:
        _uuid(self.result_id, "result_id")
        _uuid(self.request_id, "request_id")
        _uuid(self.execution_request_id, "execution_request_id")
        _enum(self.status, ExecutionStatus, "status")
        _datetime(self.finished_at, "finished_at")
        if self.started_at is not None:
            _datetime(self.started_at, "started_at")
            if self.finished_at < self.started_at:
                raise DomainValidationError(
                    "finished_at cannot precede started_at", field="finished_at"
                )
        if isinstance(self.exit_code, bool) or (
            self.exit_code is not None and not isinstance(self.exit_code, int)
        ):
            raise DomainValidationError("exit_code must be an integer or None", field="exit_code")
        if not isinstance(self.stdout, str):
            raise DomainValidationError("stdout must be a string", field="stdout")
        if not isinstance(self.stderr, str):
            raise DomainValidationError("stderr must be a string", field="stderr")
        error = _optional_error(self.error)
        if self.status is ExecutionStatus.SUCCEEDED:
            if self.exit_code != 0:
                raise DomainValidationError(
                    "successful results require exit_code 0", field="exit_code"
                )
            if error is not None:
                raise DomainValidationError(
                    "successful results cannot contain an error", field="error"
                )
        elif (
            self.status
            in {
                ExecutionStatus.START_FAILED,
                ExecutionStatus.TIMED_OUT,
                ExecutionStatus.CANCELLED,
            }
            and error is None
        ):
            raise DomainValidationError("this execution status requires an error", field="error")
        elif self.status is ExecutionStatus.FAILED:
            if self.exit_code == 0 and error is None:
                raise DomainValidationError(
                    "failed results with exit_code 0 require an error", field="error"
                )
            if self.exit_code is None and error is None:
                raise DomainValidationError(
                    "failed results require an exit_code or error", field="error"
                )

    def to_dict(self) -> SerializedModel:
        return {
            "schema_version": _SCHEMA_VERSION,
            "result_id": str(self.result_id),
            "request_id": str(self.request_id),
            "execution_request_id": str(self.execution_request_id),
            "status": self.status.value,
            "finished_at": _datetime_value(self.finished_at),
            "started_at": (
                _datetime_value(self.started_at) if self.started_at is not None else None
            ),
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ExecutionResult:
        fields = {
            "schema_version",
            "result_id",
            "request_id",
            "execution_request_id",
            "status",
            "finished_at",
            "started_at",
            "exit_code",
            "stdout",
            "stderr",
            "error",
        }
        _ensure_schema(data, fields)
        raw_started_at = data.get("started_at")
        raw_exit_code = data.get("exit_code")
        if raw_exit_code is not None and (
            isinstance(raw_exit_code, bool) or not isinstance(raw_exit_code, int)
        ):
            raise DomainValidationError("exit_code must be an integer or None", field="exit_code")
        raw_stdout = data.get("stdout", "")
        raw_stderr = data.get("stderr", "")
        if not isinstance(raw_stdout, str):
            raise DomainValidationError("stdout must be a string", field="stdout")
        if not isinstance(raw_stderr, str):
            raise DomainValidationError("stderr must be a string", field="stderr")
        return cls(
            result_id=_serialized_uuid(_required(data, "result_id"), "result_id"),
            request_id=_serialized_uuid(_required(data, "request_id"), "request_id"),
            execution_request_id=_serialized_uuid(
                _required(data, "execution_request_id"), "execution_request_id"
            ),
            status=_serialized_enum(_required(data, "status"), ExecutionStatus, "status"),
            finished_at=_serialized_datetime(_required(data, "finished_at"), "finished_at"),
            started_at=(
                None
                if raw_started_at is None
                else _serialized_datetime(raw_started_at, "started_at")
            ),
            exit_code=raw_exit_code,
            stdout=raw_stdout,
            stderr=raw_stderr,
            error=_optional_error(data.get("error")),
        )


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """The outcome of verifying an execution result."""

    verification_id: UUID
    request_id: UUID
    execution_request_id: UUID
    status: VerificationStatus
    verified_at: datetime
    details: str | None = None

    def __post_init__(self) -> None:
        _uuid(self.verification_id, "verification_id")
        _uuid(self.request_id, "request_id")
        _uuid(self.execution_request_id, "execution_request_id")
        _enum(self.status, VerificationStatus, "status")
        _datetime(self.verified_at, "verified_at")
        details = _optional_string(self.details, "details")
        if (
            self.status in {VerificationStatus.FAILED, VerificationStatus.INCONCLUSIVE}
            and details is None
        ):
            raise DomainValidationError(
                "failed or inconclusive verification requires details", field="details"
            )

    def to_dict(self) -> SerializedModel:
        return {
            "schema_version": _SCHEMA_VERSION,
            "verification_id": str(self.verification_id),
            "request_id": str(self.request_id),
            "execution_request_id": str(self.execution_request_id),
            "status": self.status.value,
            "verified_at": _datetime_value(self.verified_at),
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> VerificationResult:
        fields = {
            "schema_version",
            "verification_id",
            "request_id",
            "execution_request_id",
            "status",
            "verified_at",
            "details",
        }
        _ensure_schema(data, fields)
        return cls(
            verification_id=_serialized_uuid(_required(data, "verification_id"), "verification_id"),
            request_id=_serialized_uuid(_required(data, "request_id"), "request_id"),
            execution_request_id=_serialized_uuid(
                _required(data, "execution_request_id"), "execution_request_id"
            ),
            status=_serialized_enum(_required(data, "status"), VerificationStatus, "status"),
            verified_at=_serialized_datetime(_required(data, "verified_at"), "verified_at"),
            details=_optional_string(data.get("details"), "details"),
        )

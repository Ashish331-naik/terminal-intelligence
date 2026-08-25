# Stage 1 Overview

## Purpose

Stage 1 builds upon the Stage 0 repository foundation by implementing the
pure, framework-independent **Domain Core** of the Terminal Intelligence Layer
(`src/terminal_intelligence/domain/`).

The product vision describes this safe terminal execution flow:

```text
natural-language request (UserRequest)
        -> structured command candidate (CommandProposal)
        -> risk classification and governance (ApprovalDecision)
        -> immutable execution snapshot (ExecutionRequest)
        -> bounded subprocess execution (ExecutionResult)
        -> semantic intent verification (VerificationResult)
        -> automated failure diagnosis and repair
```

Stage 1 formally models this entire lifecycle as immutable, slotted data
classes, closed-set string enumerations, and validation invariants before
introducing application orchestration, shell adapters, or LLM integrations.

## What Stage 1 Establishes

1. **Ubiquitous Domain Models**:
   - `UserRequest`: Captures intent with unique `request_id` and UTC timestamp.
   - `CommandProposal`: Represents candidate `argv` as an immutable tuple with `CommandRisk` and rationale.
   - `ApprovalDecision`: Records human/policy decisions with mandatory rejection reasons.
   - `ExecutionRequest`: Freezes an execution-ready snapshot to prevent downstream mutation.
   - `ExecutionResult`: Encapsulates process status, exit codes, stdout/stderr, and timing.
   - `VerificationResult`: Validates goal achievement (`PASSED`, `FAILED`, `INCONCLUSIVE`).

2. **Closed-Set Enumerations**:
   - `CommandRisk` (`unknown`, `low`, `medium`, `high`, `critical`)
   - `ApprovalOutcome` (`approved`, `rejected`)
   - `ExecutionStatus` (`succeeded`, `failed`, `start_failed`, `timed_out`, `cancelled`)
   - `VerificationStatus` (`passed`, `failed`, `inconclusive`)

3. **Defensive Validation Engine**:
   - Enforces non-empty executables and tuples for `argv`.
   - Protects against POSIX C-level string termination vulnerabilities by rejecting NUL bytes (`\x00`).
   - Strictly enforces timezone-aware UTC timestamps (+00:00).
   - Guards against Python`s `bool-is-int` subclassing pitfall for exit codes.

4. **Schema Versioning & Bidirectional Serialization**:
   - Explicit `to_dict()` and `from_dict()` methods on every entity.
   - Strictly enforces `schema_version == 1` and rejects unexpected extra fields.
   - Standard RFC 3339 Zulu formatting for datetimes.

5. **Exhaustive Test Coverage**:
   - 30 unit tests across model construction, validation invariants, and serialization round-tripping.
   - 100% statement and branch coverage across core domain modules.

## Non-Goals in Stage 1

- No subprocess execution or operating system calls (`subprocess.Popen`, `os.system`).
- No LLM prompt engineering, API clients, or heuristic parsers.
- No third-party validation or serialization dependencies (Pydantic, Marshmallow, attrs).
- No mutable in-memory state or global registries.

## Definition of Done

Stage 1 is complete when all domain models, enums, errors, and serialization
methods are implemented under `src/terminal_intelligence/domain/`, exported via
`__all__`, fully typed under strict Mypy checking, tested across 30 unit tests,
and verified through `make verify`.

# Terminal Intelligence: Code Walkthrough (Stages 0–2)

This document provides a comprehensive tour of the Terminal Intelligence Layer codebase, detailing its architectural layers, domain models, ports, and adapters.

```text
src/terminal_intelligence/
├── __init__.py
├── domain/
│   ├── __init__.py
│   ├── enums.py       # Domain enumerations (CommandRisk, ApprovalOutcome, ExecutionStatus, etc.)
│   ├── errors.py      # DomainValidationError definition
│   └── models.py      # Immutable domain dataclasses (UserRequest, CommandProposal, ExecutionRequest, ExecutionResult, etc.)
├── ports/
│   ├── __init__.py
│   └── execution.py   # CommandExecutor protocol definition
└── adapters/
    ├── __init__.py
    └── process/
        ├── __init__.py
        └── subprocess_executor.py  # SubprocessExecutor direct-argv OS process adapter
```

---

## 1. Domain Layer (`src/terminal_intelligence/domain/`)

The domain layer contains pure, framework-independent data structures, business invariants, and serialization logic. It imports only standard-library types (`dataclasses`, `uuid`, `datetime`, `enum`, `math`) and has zero dependencies on `os`, `subprocess`, or platform APIs.

### Enumerations ([`enums.py`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/enums.py))
- [`CommandRisk`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/enums.py#L6-L14): `UNKNOWN`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.
- [`ApprovalOutcome`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/enums.py#L16-L21): `APPROVED`, `REJECTED`.
- [`ExecutionStatus`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/enums.py#L23-L31):
  - `SUCCEEDED`: Command ran and completed with exit code `0`.
  - `FAILED`: Command ran and exited with non-zero code or external signal.
  - `START_FAILED`: Operating system failed to spawn the binary (e.g. not found, permission denied, invalid cwd).
  - `TIMED_OUT`: Command exceeded its configured timeout deadline and was terminated.
  - `CANCELLED`: Execution was cancelled before completion.
- [`VerificationStatus`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/enums.py#L33-L39): `PASSED`, `FAILED`, `INCONCLUSIVE`.

### Domain Errors ([`errors.py`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/errors.py))
- [`DomainValidationError`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/errors.py#L6-L12): Subclass of `ValueError`. Raised when a domain model constructor or deserializer encounters invalid types, out-of-range values, NUL characters, un-ordered timestamps, or schema violations.

### Domain Models ([`models.py`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/models.py))
All models are defined as frozen, slotted dataclasses (`@dataclass(frozen=True, slots=True)`), ensuring strict immutability and memory efficiency.

1. **[`UserRequest`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/models.py#L193-L224)**: Represents the original user prompt (`request_id`, `text`, `submitted_at`).
2. **[`CommandProposal`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/models.py#L225-L276)**: Represents a proposed candidate argument vector (`proposal_id`, `request_id`, `argv: tuple[str, ...]`, `risk`, `rationale`, `proposed_at`).
3. **[`ApprovalDecision`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/models.py#L277-L335)**: Records human or policy approval (`decision_id`, `outcome`, `actor_id`, `reason`, `decided_at`). Rejected decisions require a reason.
4. **[`ExecutionRequest`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/models.py#L336-L422)**: The execution payload passed to executor adapters:
   - `argv: tuple[str, ...]`: Non-empty argument vector, no NUL bytes.
   - `timeout_seconds: float`: Finite, positive execution timeout.
   - `environment: tuple[tuple[str, str], ...]`: Immutable child environment pairs, no duplicate keys, no NUL bytes.
   - `working_directory: str | None`: Optional directory path.
5. **[`ExecutionResult`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/models.py#L423-L595)**: The structured result returned after execution:
   - `status: ExecutionStatus`
   - `exit_code: int | None`
   - `stdout: str` / `stderr: str`
   - `duration_ms: int` (monotonic elapsed duration)
   - `stdout_truncated: bool` / `stderr_truncated: bool`
   - `error: str | None`
6. **[`VerificationResult`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/models.py#L596-L655)**: Captures downstream outcome verification.

---

## 2. Ports Layer (`src/terminal_intelligence/ports/`)

The ports layer defines the interface contracts that application use cases use to interact with external mechanisms.

### [`CommandExecutor`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/ports/execution.py)
```python
class CommandExecutor(Protocol):
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Return the complete result after the child has been reaped."""
```
The port enforces complete ownership of the child process: an execution call returns only after the process has terminated, output has been drained, and resources have been cleaned up.

---

## 3. Adapters Layer (`src/terminal_intelligence/adapters/process/`)

### [`SubprocessExecutor`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/adapters/process/subprocess_executor.py)

The `SubprocessExecutor` implements `CommandExecutor` using Python's standard `subprocess` library.

#### Key Mechanics:
1. **Spawn Configuration ([`_start_process`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/adapters/process/subprocess_executor.py#L100-L115))**:
   - `shell=False` is hardcoded.
   - `stdin=subprocess.DEVNULL` disconnects child input.
   - `stdout=PIPE` and `stderr=PIPE` set up separate streams.
   - `env=dict(request.environment)` replaces child environment.
   - `start_new_session=True` (POSIX) isolates child in a new process group.
2. **Stream Capture & Drain ([`_start_capture_threads`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/adapters/process/subprocess_executor.py#L117-L134) & [`_read_stream`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/adapters/process/subprocess_executor.py#L136-L149))**:
   - Two background threads drain stdout and stderr concurrently in `8192`-byte chunks.
   - Data is buffered up to `max_output_bytes` (default 1 MiB); subsequent bytes are drained and discarded to prevent pipe buffer deadlocks.
3. **Timeout & Termination ([`_wait_for_process`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/adapters/process/subprocess_executor.py#L163-L170) & [`_terminate_after_timeout`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/adapters/process/subprocess_executor.py#L171-L179))**:
   - `process.wait(timeout=request.timeout_seconds)` blocks for completion.
   - On timeout, sends `SIGTERM` to the process group, waits a grace period (`0.2s`), and escalates to `SIGKILL` if still running.
4. **Result Construction ([`_result`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/adapters/process/subprocess_executor.py#L209-L243))**:
   - `duration_ms` is computed from `time.monotonic()`.
   - Output bytes are decoded using `utf-8` with `errors="replace"`.
   - `finished_at` wall-clock timestamp is recorded.

---

## 4. Test Suite Structure (`tests/unit/`)

```text
tests/unit/
├── test_package.py                   # Stage 0: Packaging and importability
├── domain/
│   ├── test_models.py                # Model construction, slots, immutability
│   ├── test_validation.py            # Negative testing, NUL bytes, bad types
│   └── test_serialization.py         # JSON dict round-trip and schema tests
└── adapters/
    └── test_subprocess_executor.py   # Subprocess lifecycle, streams, signals, timeouts
```

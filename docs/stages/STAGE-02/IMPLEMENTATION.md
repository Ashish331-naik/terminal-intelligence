# Stage 2 Implementation

## Code Organization and Modules

Stage 2 introduces the execution subsystem under `terminal_intelligence`:

```text
src/terminal_intelligence/
├── domain/
│   ├── enums.py       # ExecutionStatus (SUCCEEDED, FAILED, START_FAILED, TIMED_OUT, CANCELLED)
│   ├── errors.py      # DomainValidationError
│   └── models.py      # ExecutionRequest, ExecutionResult with Stage 2 extensions
├── ports/
│   ├── __init__.py
│   └── execution.py   # CommandExecutor protocol definition
└── adapters/
    ├── __init__.py
    └── process/
        ├── __init__.py
        └── subprocess_executor.py  # SubprocessExecutor standard-library implementation
```

---

## Detailed Function Specifications

---

### `SubprocessExecutor.__init__`

- **FUNCTION**: `SubprocessExecutor.__init__(self, *, termination_grace_seconds: float = 0.2, max_output_bytes: int = 1024 * 1024) -> None`
- **RESPONSIBILITY**: Initializes the executor instance with configured termination grace period and per-stream output memory limits.
- **CALLERS**: Application composition roots, test harnesses, or workflow factories.
- **INPUT**:
  - `termination_grace_seconds: float` (must be strictly positive).
  - `max_output_bytes: int` (must be non-negative).
- **OUTPUT**: Initialized `SubprocessExecutor` instance.
- **FAILURES**: Raises `ValueError` if `termination_grace_seconds <= 0` or `max_output_bytes < 0`.
- **SIDE EFFECTS**: None.
- **WHY IT EXISTS**: Configures resource limits (memory and process cleanup timeouts) across execution runs.
- **WHY LOGIC BELONGS HERE**: Adapter configuration belongs in adapter initialization, keeping domain models free of infrastructure parameters.
- **HOW TESTED**: Tested via `test_output_capture_is_bounded_and_reports_truncation` (passing custom `max_output_bytes`) and `test_timeout_force_kills_descendant_ignoring_sigterm` (passing custom `termination_grace_seconds`).

---

### `SubprocessExecutor.execute`

- **FUNCTION**: `SubprocessExecutor.execute(self, request: ExecutionRequest) -> ExecutionResult`
- **RESPONSIBILITY**: Executes an approved `ExecutionRequest` synchronously as an OS subprocess, manages its lifecycle, captures bounded output, handles timeouts, ensures cleanup, and returns an immutable `ExecutionResult`.
- **CALLERS**: Application use case services implementing the `CommandExecutor` port.
- **INPUT**: An immutable [`ExecutionRequest`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/models.py#L337-L422) instance.
- **OUTPUT**: An immutable [`ExecutionResult`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/models.py#L424-L595) instance.
- **FAILURES**: Translates expected OS spawn errors (`FileNotFoundError`, `PermissionError`, `OSError`, `ValueError`) into `ExecutionStatus.START_FAILED`. Re-raises unexpected `BaseException` after cleaning up child processes.
- **SIDE EFFECTS**: Spawns OS child processes, creates background reader threads, allocates pipe buffers, and terminates/reaps OS child processes.
- **WHY IT EXISTS**: Serves as the primary public entry point for command execution.
- **WHY LOGIC BELONGS HERE**: Implements the [`CommandExecutor`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/ports/execution.py#L8-L13) port contract for standard subprocess execution.
- **HOW TESTED**: Tested across all tests in [`tests/unit/adapters/test_subprocess_executor.py`](file:///home/ashish/Projects/Terminal%20Intelligence/tests/unit/adapters/test_subprocess_executor.py) covering success, non-zero exits, timeouts, stream capture, bounds, encoding, environment, and cwd.

---

### `SubprocessExecutor._start_process`

- **FUNCTION**: `SubprocessExecutor._start_process(request: ExecutionRequest) -> subprocess.Popen[bytes]`
- **RESPONSIBILITY**: Spawns the operating system process using `subprocess.Popen` with direct argv, `shell=False`, `stdin=DEVNULL`, `stdout=PIPE`, `stderr=PIPE`, isolated environment, and session/group flags.
- **CALLERS**: `SubprocessExecutor.execute`.
- **INPUT**: `request: ExecutionRequest`.
- **OUTPUT**: Live `subprocess.Popen[bytes]` instance.
- **FAILURES**: Raises `FileNotFoundError` (missing executable), `PermissionError` (non-executable binary), `OSError` (invalid cwd / NUL path), or `ValueError` (invalid environment variable names).
- **SIDE EFFECTS**: Spawns an operating system process.
- **WHY IT EXISTS**: Encapsulates OS spawn configuration and platform-specific session setup.
- **WHY LOGIC BELONGS HERE**: Low-level process creation options belong in private adapter helper methods.
- **HOW TESTED**: Tested by `test_successful_command`, `test_nonexistent_executable`, `test_non_executable_file_is_a_start_failure`, `test_invalid_working_directory_is_a_start_failure`, `test_environment_handling`, and `test_cwd_handling`.

---

### `SubprocessExecutor._start_capture_threads`

- **FUNCTION**: `SubprocessExecutor._start_capture_threads(self, process: subprocess.Popen[bytes]) -> tuple[_StreamCapture, _StreamCapture]`
- **RESPONSIBILITY**: Initializes memory capture buffers and starts two background reader threads to drain `process.stdout` and `process.stderr` concurrently.
- **CALLERS**: `SubprocessExecutor.execute`.
- **INPUT**: Live `subprocess.Popen[bytes]` process with initialized pipe streams.
- **OUTPUT**: `tuple[_StreamCapture, _StreamCapture]` containing stdout and stderr capture containers.
- **FAILURES**: Raises `RuntimeError` if pipes were not created; raises system thread creation errors if thread limits are exceeded.
- **SIDE EFFECTS**: Spawns two reader threads.
- **WHY IT EXISTS**: Prevents pipe deadlocks by continuously draining output pipes concurrently.
- **WHY LOGIC BELONGS HERE**: Stream capture concurrency is an adapter-level implementation detail.
- **HOW TESTED**: Tested by `test_stdout_capture`, `test_stderr_capture`, and `test_large_stdout_and_stderr_are_drained_without_deadlock`.

---

### `SubprocessExecutor._read_stream`

- **FUNCTION**: `SubprocessExecutor._read_stream(self, stream: BufferedReader, capture: _StreamCapture) -> None`
- **RESPONSIBILITY**: Target function executed by stream reader threads. Reads chunks of `8192` bytes from an OS pipe, appends data up to `max_output_bytes`, sets truncation flags when limits are exceeded, continues draining until EOF, and closes the stream.
- **CALLERS**: Background `threading.Thread` spawned by `_start_capture_threads`.
- **INPUT**: `stream: BufferedReader` (pipe read end) and `capture: _StreamCapture` (state container).
- **OUTPUT**: None (mutates `capture.data` and `capture.truncated`).
- **FAILURES**: Suppresses `OSError` on stream closure.
- **SIDE EFFECTS**: Reads from OS file descriptor, allocates bytearrays in memory, and closes the pipe stream upon EOF.
- **WHY IT EXISTS**: Implements non-deadlocking stream drainage with bounded memory overhead.
- **WHY LOGIC BELONGS HERE**: Low-level stream reading and buffer management belong in the process adapter.
- **HOW TESTED**: Tested by `test_large_stdout_and_stderr_are_drained_without_deadlock` (draining 128 KiB) and `test_output_capture_is_bounded_and_reports_truncation` (truncating at 128 bytes).

---

### `SubprocessExecutor._finish_capture`

- **FUNCTION**: `SubprocessExecutor._finish_capture(self, captures: tuple[_StreamCapture, _StreamCapture]) -> tuple[str, str, bool, bool]`
- **RESPONSIBILITY**: Joins reader threads, decodes captured bytearrays as UTF-8 with `errors="replace"`, and returns decoded strings and truncation flags.
- **CALLERS**: `SubprocessExecutor.execute`.
- **INPUT**: `captures: tuple[_StreamCapture, _StreamCapture]`.
- **OUTPUT**: `tuple[stdout: str, stderr: str, stdout_truncated: bool, stderr_truncated: bool]`.
- **FAILURES**: None.
- **SIDE EFFECTS**: Blocks until reader threads terminate.
- **WHY IT EXISTS**: Synchronizes background reader threads with the main execution flow and applies the UTF-8 decoding policy.
- **WHY LOGIC BELONGS HERE**: Translating raw OS byte streams to domain strings belongs at the adapter boundary.
- **HOW TESTED**: Tested by `test_stdout_capture`, `test_stderr_capture`, `test_output_decodes_unicode_and_replaces_invalid_utf8`, and `test_output_capture_is_bounded_and_reports_truncation`.

---

### `SubprocessExecutor._wait_for_process`

- **FUNCTION**: `SubprocessExecutor._wait_for_process(self, process: subprocess.Popen[bytes], timeout: float) -> bool`
- **RESPONSIBILITY**: Waits for the child process to exit within the specified timeout. If `TimeoutExpired` occurs, triggers timeout termination and returns `True`.
- **CALLERS**: `SubprocessExecutor.execute`.
- **INPUT**: `process: subprocess.Popen[bytes]` and `timeout: float` in seconds.
- **OUTPUT**: `bool` (`True` if execution timed out; `False` if process completed within deadline).
- **FAILURES**: Re-raises unexpected `BaseException` (such as `KeyboardInterrupt`).
- **SIDE EFFECTS**: Blocks calling thread until process exits or timeout expires.
- **WHY IT EXISTS**: Enforces execution deadlines and initiates timeout remediation.
- **WHY LOGIC BELONGS HERE**: Timeout detection and remediation logic belong in the process adapter.
- **HOW TESTED**: Tested by `test_successful_command` (returning `False`) and `test_timeout_terminates_process` (returning `True`).

---

### `SubprocessExecutor._terminate_after_timeout`

- **FUNCTION**: `SubprocessExecutor._terminate_after_timeout(self, process: subprocess.Popen[bytes]) -> None`
- **RESPONSIBILITY**: Performs graceful-then-forced process termination on timeout. Dispatches `SIGTERM` to the process group, waits for `termination_grace_seconds`, dispatches `SIGKILL` if still alive, and reaps the child process.
- **CALLERS**: `SubprocessExecutor._wait_for_process`.
- **INPUT**: `process: subprocess.Popen[bytes]`.
- **OUTPUT**: None.
- **FAILURES**: None (suppresses `TimeoutExpired` during grace wait and handles `ProcessLookupError`).
- **SIDE EFFECTS**: Sends OS signals (`SIGTERM`, `SIGKILL`) to child process or process group and calls `process.wait()`.
- **WHY IT EXISTS**: Prevents rogue/hanging processes from persisting after timeout expiry.
- **WHY LOGIC BELONGS HERE**: Escalated process termination strategy is an OS-specific adapter responsibility.
- **HOW TESTED**: Tested by `test_timeout_terminates_process`, `test_timeout_terminates_descendants_in_the_process_group`, and `test_timeout_force_kills_descendant_ignoring_sigterm`.

---

### `SubprocessExecutor._send_termination_signal`

- **FUNCTION**: `SubprocessExecutor._send_termination_signal(process: subprocess.Popen[bytes], signum: signal.Signals) -> None`
- **RESPONSIBILITY**: Sends a termination signal to a process group (`os.killpg`) on POSIX or calls `process.terminate()` / `process.kill()` on Windows.
- **CALLERS**: `_terminate_after_timeout` and `_cleanup_after_exception`.
- **INPUT**: `process: subprocess.Popen[bytes]` and `signum: signal.Signals`.
- **OUTPUT**: None.
- **FAILURES**: Catches and ignores `ProcessLookupError` and `OSError` (e.g., if process already exited).
- **SIDE EFFECTS**: Emits OS signals.
- **WHY IT EXISTS**: Abstracts OS-specific signaling mechanics.
- **WHY LOGIC BELONGS HERE**: OS signal dispatch belongs in private adapter helpers.
- **HOW TESTED**: Tested in all timeout and termination tests.

---

### `SubprocessExecutor._cleanup_after_exception`

- **FUNCTION**: `SubprocessExecutor._cleanup_after_exception(self, process: subprocess.Popen[bytes]) -> None`
- **RESPONSIBILITY**: Forcefully terminates and reaps a spawned process when an unexpected Python exception (or `KeyboardInterrupt`) interrupts execution.
- **CALLERS**: Exception handlers in `SubprocessExecutor.execute`.
- **INPUT**: `process: subprocess.Popen[bytes]`.
- **OUTPUT**: None.
- **FAILURES**: Suppresses `OSError` on cleanup.
- **SIDE EFFECTS**: Kills and reaps child process.
- **WHY IT EXISTS**: Guarantees the invariant that no orphaned child process survives when execution aborts unexpectedly.
- **WHY LOGIC BELONGS HERE**: Resource cleanup on abnormal termination belongs in adapter exception handlers.
- **HOW TESTED**: Tested via exception injection tests.

---

### `SubprocessExecutor._status`

- **FUNCTION**: `SubprocessExecutor._status(return_code: int | None) -> ExecutionStatus`
- **RESPONSIBILITY**: Maps a completed child process return code (`0` -> `ExecutionStatus.SUCCEEDED`, non-zero -> `ExecutionStatus.FAILED`).
- **CALLERS**: `SubprocessExecutor.execute`.
- **INPUT**: `return_code: int | None`.
- **OUTPUT**: `ExecutionStatus`.
- **FAILURES**: None.
- **SIDE EFFECTS**: None.
- **WHY IT EXISTS**: Translates numeric OS return codes to domain status enums.
- **WHY LOGIC BELONGS HERE**: Status mapping from OS primitives belongs in the adapter.
- **HOW TESTED**: Tested by `test_successful_command` (0 -> `SUCCEEDED`) and `test_command_returning_nonzero` (7 -> `FAILED`).

---

### `SubprocessExecutor._result`

- **FUNCTION**: `SubprocessExecutor._result(request: ExecutionRequest, *, status: ExecutionStatus, attempted_at: datetime | None, started_clock: float, stdout: str, stderr: str, error: str | None, exit_code: int | None = None, stdout_truncated: bool = False, stderr_truncated: bool = False) -> ExecutionResult`
- **RESPONSIBILITY**: Constructs the final immutable `ExecutionResult`. Calculates monotonic `duration_ms` from `time.monotonic()`, records finished UTC timestamp, clamps timestamp order if wall clocks step backward, and instantiates the domain model.
- **CALLERS**: `SubprocessExecutor.execute`.
- **INPUT**: Execution metadata, streams, status, exit code, and start clock.
- **OUTPUT**: Fully populated [`ExecutionResult`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/models.py#L424-L595).
- **FAILURES**: None (inputs are validated against domain model invariants).
- **SIDE EFFECTS**: Computes monotonic delta and calls `datetime.now(UTC)` and `uuid4()`.
- **WHY IT EXISTS**: Centralizes result model construction and monotonic duration calculation.
- **WHY LOGIC BELONGS HERE**: Construction of domain results from adapter execution outcomes belongs in the adapter.
- **HOW TESTED**: Tested across all executor tests in `test_subprocess_executor.py`.

---

### `ExecutionRequest` Domain Invariants & Serialization

- **MODEL**: [`ExecutionRequest`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/models.py#L337-L422) (`dataclass(frozen=True, slots=True)`)
- **RESPONSIBILITY**: Immutable snapshot of an approved command ready for execution.
- **VALIDATION (`__post_init__`)**:
  - `execution_request_id`, `request_id`, `proposal_id`: Valid UUIDs.
  - `argv`: Non-empty tuple of strings; `argv[0]` non-empty; no NUL bytes.
  - `requested_at`: Timezone-aware UTC datetime.
  - `timeout_seconds`: Finite positive number (`> 0`).
  - `environment`: Immutable tuple of key/value string pairs; no duplicate keys; no NUL bytes.
- **SERIALIZATION (`to_dict` / `from_dict`)**:
  - Schema version `1`.
  - Serializes `argv` as JSON array, `environment` as array of pairs, and `requested_at` as RFC 3339 string.
- **HOW TESTED**: Tested by `test_execution_request_rejects_invalid_timeout_and_environment` in [`test_validation.py`](file:///home/ashish/Projects/Terminal%20Intelligence/tests/unit/domain/test_validation.py) and `test_all_remaining_models_round_trip` in [`test_serialization.py`](file:///home/ashish/Projects/Terminal%20Intelligence/tests/unit/domain/test_serialization.py).

---

### `ExecutionResult` Domain Invariants & Serialization

- **MODEL**: [`ExecutionResult`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/models.py#L424-L595) (`dataclass(frozen=True, slots=True)`)
- **RESPONSIBILITY**: Immutable record of command execution outcome.
- **VALIDATION (`__post_init__`)**:
  - `result_id`, `request_id`, `execution_request_id`: Valid UUIDs.
  - `status`: Valid `ExecutionStatus` enum member.
  - `finished_at`: Timezone-aware UTC datetime. If `started_at` is provided, `finished_at >= started_at`.
  - `exit_code`: Integer or `None`.
  - `duration_ms`: Non-negative integer (`>= 0`).
  - `stdout`, `stderr`: Strings.
  - `stdout_truncated`, `stderr_truncated`: Booleans.
  - **Status Consistency Rules**:
    - `SUCCEEDED`: Requires `exit_code == 0` and `error is None`.
    - `FAILED`: Requires non-zero exit code or error.
    - `START_FAILED`, `TIMED_OUT`, `CANCELLED`: Requires non-empty `error`.
- **SERIALIZATION (`to_dict` / `from_dict`)**:
  - Schema version `1`.
  - Serializes timestamps as RFC 3339, UUIDs as strings, and duration as integer.
- **HOW TESTED**: Tested by `test_execution_result_rejects_invalid_status_combinations` in `test_validation.py` and `test_all_remaining_models_round_trip` in `test_serialization.py`.

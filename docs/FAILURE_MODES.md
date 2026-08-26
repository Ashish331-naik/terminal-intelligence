# Terminal Intelligence: Failure Modes and Error Taxonomy

This document provides a comprehensive catalog of failure modes, error taxonomies, and remediation behaviors across the Terminal Intelligence Layer.

---

## 1. Failure Taxonomy Matrix

| Failure Mode | Trigger Condition | Detection Phase | Result / Exception | Exit Code | Stdout / Stderr | Error Field |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Domain Validation Error** | Malformed input (empty argv, NUL bytes, duplicate env, negative timeout) | Domain constructor / Deserialization | Raises `DomainValidationError` | N/A | N/A | N/A |
| **Missing Executable** | Binary not found in PATH or at specified path | `_start_process` (`Popen`) | Returns `START_FAILED` | `None` | `""` / `""` | `"FileNotFoundError: [Errno 2] ..."` |
| **Permission Denied** | Target file not executable or permission restricted | `_start_process` (`Popen`) | Returns `START_FAILED` | `None` | `""` / `""` | `"PermissionError: [Errno 13] ..."` |
| **Invalid CWD / Env** | Missing directory or invalid env key at spawn | `_start_process` (`Popen`) | Returns `START_FAILED` | `None` | `""` / `""` | `"OSError: ..."` / `"ValueError: ..."` |
| **Command Non-Zero Exit** | Binary executes but exits with code `1..255` | `_wait_for_process` | Returns `FAILED` | `1..255` | Captured stdout & stderr | `None` |
| **Command Killed by Signal** | Process terminated by external OS signal (e.g. SIGKILL, SIGSEGV) | `_wait_for_process` | Returns `FAILED` | Negative int (e.g. `-9`, `-11`) | Captured stdout & stderr | `None` |
| **Execution Timeout** | Execution exceeds `timeout_seconds` | `_wait_for_process` | Returns `TIMED_OUT` | Retcode / Signal | Partial captured output | `"process exceeded its timeout"` |
| **Output Truncated** | Stream output exceeds `max_output_bytes` | `_read_stream` | Truncation flag set | As returned | Truncated to cap | As returned |
| **Internal / Bug** | Unexpected Python error or `KeyboardInterrupt` | Any execution phase | Re-raises exception after child cleanup | N/A | N/A | N/A |

---

## 2. Detailed Failure Mode Analysis

---

### Category 1: Domain Validation Errors (Pre-Execution)

- **Condition**: An invalid argument vector (empty `argv`, whitespace-only `argv[0]`, NUL bytes), non-positive timeout (`timeout_seconds <= 0`), duplicate environment keys, invalid RFC 3339 timestamps, or mismatched schema versions.
- **Handling**: Construction immediately raises [`DomainValidationError`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/errors.py#L6-L12).
- **Process Impact**: Zero. No OS process is spawned, no threads are created, and no system resources are allocated.
- **Remediation**: Upstream request creators or planning agents must fix request formatting before invoking execution.

---

### Category 2: OS Spawn Failures (`ExecutionStatus.START_FAILED`)

- **Condition**:
  1. `FileNotFoundError`: Executable does not exist or bare executable name cannot be resolved via `PATH`.
  2. `PermissionError`: File exists but lacks executable permissions (`chmod +x`), or user lacks directory access.
  3. `OSError`: Specified `working_directory` does not exist or is a regular file.
  4. `ValueError`: Environment variable name contains `=` or invalid bytes.
- **Handling**: Caught in [`SubprocessExecutor.execute`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/adapters/process/subprocess_executor.py#L51-L86) and converted to:
  - `status = ExecutionStatus.START_FAILED`
  - `exit_code = None`
  - `started_at = None`
  - `stdout = ""` and `stderr = ""`
  - `error = "ExceptionName: detail"`
- **Process Impact**: No child process remains running.
- **Remediation**: Planning and diagnosis agents inspect `result.error` to determine whether the binary was missing or path permissions were insufficient.

---

### Category 3: Command Execution Failures (`ExecutionStatus.FAILED`)

- **Condition**: The target binary spawns successfully and runs to completion, but exits with a non-zero return code (e.g. `1`, `2`, `127`, `255`), or is terminated by an external signal (e.g. `SIGSEGV` -> exit code `-11`).
- **Handling**:
  - `status = ExecutionStatus.FAILED`
  - `exit_code = process.returncode`
  - `started_at = timestamp`
  - `stdout = captured_stdout`
  - `stderr = captured_stderr`
  - `error = None` (the error diagnostic is the command's own `stderr`).
- **Process Impact**: Process has terminated and been fully reaped by `process.wait()`.
- **Remediation**: Downstream verification inspects `stderr` and `exit_code` to plan diagnostic and repair actions.

---

### Category 4: Execution Timeouts (`ExecutionStatus.TIMED_OUT`)

- **Condition**: The execution time exceeds `request.timeout_seconds`.
- **Handling**:
  1. `_wait_for_process` catches `subprocess.TimeoutExpired`.
  2. `_terminate_after_timeout` sends `SIGTERM` to the process group (`os.killpg`).
  3. Waits up to `termination_grace_seconds` (default `0.2s`).
  4. Escalates to `_FORCE_KILL` (`SIGKILL`) if child processes remain alive.
  5. Reaps the child process.
  6. Drains any remaining partial stdout/stderr captured before termination.
  7. Returns:
     - `status = ExecutionStatus.TIMED_OUT`
     - `exit_code = process.returncode` (e.g. `-15` or `-9`)
     - `stdout = partial_stdout`
     - `stderr = partial_stderr`
     - `error = "process exceeded its timeout"`
- **Process Impact**: Direct child and process group descendants are terminated and reaped.
- **Remediation**: Increase timeout if the command is expected to be long-running, or diagnose infinite loops / hanging I/O.

---

### Category 5: Stream Truncation and Buffer Bounds

- **Condition**: A process produces more stdout or stderr data than `max_output_bytes` (default: 1 MiB).
- **Handling**:
  - Reader threads append data up to `max_output_bytes`.
  - Once limit is reached, `capture.truncated` is set to `True`.
  - Reader threads continue draining and discarding surplus bytes from the pipe until EOF to prevent child write deadlocks.
  - Returned `ExecutionResult` sets `stdout_truncated = True` or `stderr_truncated = True`.
- **Process Impact**: Process runs to completion without deadlocking on full pipe buffers. Host memory remains protected.
- **Remediation**: Consumers know that captured output represents a prefix of total stream output.

---

### Category 6: Edge Cases and Concurrency Hazards

#### A. Detached Grandchildren (Escaped Process Groups)
- **Scenario**: A child process spawns a daemonized background process (`setsid()` or `daemon()`).
- **Hazard**: The grandchild leaves the process group and will not receive group signals on timeout.
- **Mitigation**: Process group signaling cleans up all cooperative descendants; non-cooperative daemonized processes require system-level container or cgroup isolation in production deployments.

#### B. Surviving Descendants Holding Open Pipes
- **Scenario**: A background child process inherits stdout/stderr file descriptors and outlives the parent.
- **Hazard**: Reader threads waiting for EOF could block indefinitely if joined without limits.
- **Mitigation**: Reader threads must use daemon threads and timeout-bounded joins, and parent read handles must be closed during cleanup.

#### C. POSIX PID Recycling
- **Scenario**: A timed-out child terminates gracefully on `SIGTERM` and is reaped; subsequent `SIGKILL` is sent to the same PID.
- **Hazard**: Kernel may reallocate the PID to an unrelated process before `SIGKILL` is called.
- **Mitigation**: The executor must only send `_FORCE_KILL` if graceful termination did not already reap the process (`process.poll() is None`).

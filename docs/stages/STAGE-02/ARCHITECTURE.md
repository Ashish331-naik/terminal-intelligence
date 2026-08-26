# Stage 2 Architecture: Deterministic Command Execution

## Purpose

Stage 2 establishes the direct operating-system execution boundary of the Terminal Intelligence Layer. It provides a deterministic, secure, and synchronous execution mechanism that translates an immutable domain [`ExecutionRequest`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/models.py#L337-L422) into an operating system subprocess and converts the captured outcome into an immutable [`ExecutionResult`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/models.py#L424-L595).

---

## Architectural Boundaries

The execution architecture strictly adheres to inward dependency rules and the Hexagonal (Ports and Adapters) pattern:

```text
+-------------------------------------------------------------------------+
|                        Application Boundary                             |
|                                                                         |
|   [Use Case: Run Approved Command]                                      |
|                 |                                                       |
|                 v                                                       |
|   +---------------------------+                                         |
|   | ports.CommandExecutor     | <---+ (Protocol owned by application)   |
|   +---------------------------+     |                                   |
+-----------------|-------------------|-----------------------------------+
                  |                   |
                  v                   |
+-------------------------------------+-----------------------------------+
|                        Adapter Boundary                                 |
|                                                                         |
|   +------------------------------------+                                |
|   | adapters.process.SubprocessExecutor|                                |
|   +------------------------------------+                                |
|                 |                                                       |
|                 v                                                       |
|        [subprocess.Popen] (shell=False, stdin=DEVNULL)                  |
|                 |                                                       |
+-----------------|-------------------------------------------------------+
                  |
                  v
+-------------------------------------------------------------------------+
|                    Operating System Boundary                            |
|                                                                         |
|   POSIX: start_new_session=True -> Process Group (killpg SIGTERM/KILL)  |
|   Windows: CREATE_NEW_PROCESS_GROUP -> Process Handle                   |
|   Pipes: Anonymous non-blocking OS pipes (stdout / stderr)              |
+-------------------------------------------------------------------------+
```

### Dependency Invariant
- `domain/` owns immutable request/result values and domain validation rules. It has zero knowledge of `subprocess`, `os`, `signal`, or platform APIs.
- `ports/` defines the abstract execution contract ([`CommandExecutor`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/ports/execution.py#L8-L13)) required by the application.
- `adapters/process/` implements [`CommandExecutor`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/ports/execution.py#L8-L13) via standard-library `subprocess.Popen`. It encapsulates platform differences, process groups, pipe readers, and signal handling.
- `application/` and `cli/` interact with execution exclusively through the `CommandExecutor` port.

---

## Request and Result Contracts

### 1. `ExecutionRequest` Domain Contract
An immutable dataclass defining what to run and its containment constraints:
- `execution_request_id: UUID`: Unique identifier for this execution attempt.
- `request_id: UUID`: Root correlation identifier for the user request.
- `proposal_id: UUID`: Proposal correlation identifier.
- `argv: tuple[str, ...]`: Non-empty argument vector where `argv[0]` is the executable. Must not contain NUL bytes.
- `requested_at: datetime`: UTC timezone-aware timestamp when execution was requested.
- `approval_decision_id: UUID | None`: Optional correlation identifier linking to user approval.
- `working_directory: str | None`: Optional absolute or relative directory path. Must not contain NUL bytes.
- `timeout_seconds: float`: Finite, strictly positive number (default: `30.0`). Rejects `0`, negative numbers, `inf`, and `nan`.
- `environment: tuple[tuple[str, str], ...]`: Immutable key-value pairs representing the complete child environment. Rejects duplicate keys and NUL bytes.

### 2. `ExecutionResult` Domain Contract
An immutable dataclass recording the complete, structured outcome:
- `result_id: UUID`: Unique execution result identifier.
- `request_id: UUID`: Correlated root request identifier.
- `execution_request_id: UUID`: Correlated execution request identifier.
- `status: ExecutionStatus`: One of `SUCCEEDED`, `FAILED`, `START_FAILED`, `TIMED_OUT`, or `CANCELLED`.
- `started_at: datetime | None`: UTC wall-clock time when process spawn succeeded (`None` if start failed).
- `finished_at: datetime`: UTC wall-clock time when execution and cleanup completed.
- `exit_code: int | None`: Process exit return code (`0` for success, positive integer for non-zero exit, negative integer for POSIX termination signals, or `None` if the process failed to spawn).
- `stdout: str`: Captured standard output, decoded as UTF-8 with replacement characters.
- `stderr: str`: Captured standard error, decoded as UTF-8 with replacement characters.
- `duration_ms: int`: Monotonic execution elapsed time in milliseconds, measured from before spawn to final cleanup.
- `error: str | None`: Adapter error detail (required for `START_FAILED`, `TIMED_OUT`, and `CANCELLED`; prohibited for `SUCCEEDED`).
- `stdout_truncated: bool`: `True` if stdout reached `max_output_bytes` limit.
- `stderr_truncated: bool`: `True` if stderr reached `max_output_bytes` limit.

---

## Process Mechanism and Execution Lifecycle

### Process Spawn Configuration
The adapter uses `subprocess.Popen` with the following mandatory parameters:
1. `request.argv`: Passed directly as a sequence. No string concatenation or `shlex.split`.
2. `shell=False`: Hardcoded to prevent shell expansion, metacharacter interpretation, and command injection.
3. `stdin=subprocess.DEVNULL`: Closes child input stream immediately to prevent hanging on interactive prompts.
4. `stdout=subprocess.PIPE` & `stderr=subprocess.PIPE`: Dedicated unmixed anonymous OS pipes.
5. `text=False`: Raw bytes are read by background threads and decoded with `utf-8` and `errors="replace"` to protect against decode crashes.
6. `cwd=request.working_directory`: Passed directly to OS spawn; never calls `os.chdir` in parent process.
7. `env=dict(request.environment)`: Fully replaces child environment; parent environment variables are not inherited by default.
8. `start_new_session=True` (POSIX): Spawns child as a new session leader and process group leader (`setsid()`).

### Execution Lifecycle Steps

```text
[1. Validate Request] ---> [2. Record Monotonic Start] ---> [3. Spawn subprocess.Popen]
                                                                     |
                                      +------------------------------+
                                      |
                                      v
                          [4. Start Stream Reader Threads]
                          (stdout & stderr drained to memory buffers)
                                      |
                                      v
                          [5. Wait on Process (timeout)]
                                      |
             +------------------------+------------------------+
             |                                                 |
             v (Process Exits)                                 v (Timeout Expired)
  [6A. Drain Remaining Output]                    [6B. Graceful SIGTERM to Process Group]
             |                                                 |
             v                                                 v
  [7A. Record Exit Status]                        [7B. Wait Grace Period (0.2s)]
             |                                                 |
             |                                                 v
             |                                    [7C. Force SIGKILL if Still Alive]
             |                                                 |
             |                                                 v
             +------------------------+------------------------+
                                      |
                                      v
                          [8. Join Reader Threads & Close Pipes]
                                      |
                                      v
                          [9. Decode Output (UTF-8 Replace)]
                                      |
                                      v
                          [10. Compute Monotonic duration_ms]
                                      |
                                      v
                          [11. Construct Immutable ExecutionResult]
```

---

## Stream Capture and Memory Boundedness

To protect against memory exhaustion from high-volume output (e.g. infinite loops or large log dumps):
1. **Per-Stream Byte Limits**: `SubprocessExecutor` enforces `max_output_bytes` (default: 1 MiB) independently for `stdout` and `stderr`.
2. **Non-Blocking Pipe Draining**: Dedicated reader threads read in `8192`-byte chunks. Once the byte limit is reached, bytes are discarded while the reader thread continues draining the pipe until EOF. This prevents the OS pipe buffer (typically 64 KiB) from filling up and deadlocking the child process.
3. **Truncation Flagging**: When output exceeds `max_output_bytes`, `stdout_truncated` or `stderr_truncated` is set to `True`, alerting downstream consumers that captured output is incomplete.

---

## Timeout and Process Lifecycle Management

### POSIX Process Group Containment
1. On POSIX systems, `start_new_session=True` creates a new process group where `pgid == child.pid`.
2. On timeout:
   - `SIGTERM` is dispatched to the entire process group (`os.killpg(process.pid, signal.SIGTERM)`).
   - The executor waits for a configurable grace period (`termination_grace_seconds`, default: `0.2s`).
   - If processes in the group ignore `SIGTERM` or remain alive after the grace period, `SIGKILL` is sent to the group (`os.killpg(process.pid, signal.SIGKILL)`).
   - The direct child process is reaped via `process.wait()`.

### Known Process-Tree Limitations
1. **Detached Grandchildren (Escaped Process Groups)**:
   If a child process explicitly calls `setsid()` or `setpgrp()` to start its own new session, or daemonizes, it leaves the parent's process group. Signals sent to `process.pid` will not reach escaped grandchildren.
2. **Descendant Pipe Inheritance Deadlock**:
   If a grandchild inherits the stdout/stderr file descriptors and outlives the direct child process, the write end of the OS pipe remains open. Reader threads must use bounded timeouts or parent pipe closures to prevent hanging waiting for EOF.
3. **Windows Process Tree Containment**:
   On Windows (`os.name == "nt"`), `CREATE_NEW_PROCESS_GROUP` does not automatically terminate child process trees. Terminating child trees on Windows requires Windows Job Objects (`AssignProcessToJobObject` with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`). Direct child termination via `TerminateProcess` is the baseline guarantee.

---

## Error Taxonomy

| Failure Mode | Result Status | Exit Code | Stdout / Stderr | Error Field | Semantics |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Normal Success** | `SUCCEEDED` | `0` | Captured | `None` | Command ran to completion and reported success. |
| **Non-Zero Exit** | `FAILED` | `1..255` | Captured | `None` | Command ran and completed, but reported non-zero status. |
| **Signal Termination** | `FAILED` | Negative int (e.g. `-15`) | Captured | `None` | Command was killed by an external OS signal. |
| **Executable Not Found** | `START_FAILED` | `None` | `""` | `"FileNotFoundError: ..."` | OS failed to locate binary at spawn time. |
| **Permission Denied** | `START_FAILED` | `None` | `""` | `"PermissionError: ..."` | Binary is not marked executable or path forbidden. |
| **Invalid CWD / Env** | `START_FAILED` | `None` | `""` | `"OSError: ..."` | CWD is missing or environment key contains invalid chars. |
| **Execution Timeout** | `TIMED_OUT` | Retcode / Signal | Captured prefix | `"process exceeded its timeout"` | Execution exceeded deadline; child terminated and reaped. |
| **Internal / Bug** | *Raised* | N/A | N/A | N/A | Unexpected Python exceptions clean up child and re-raise. |

---

## Security Invariants and Assumptions

1. **Direct Argv Only**: `shell=False` is immutable and cannot be overridden by untrusted inputs.
2. **Explicit Environment Replacement**: Environment variables are passed explicitly. Parent process secrets (e.g., API keys, auth tokens, ambient environment variables) are not leaked to the child.
3. **Standard Input Closure**: `stdin=DEVNULL` ensures children cannot hang waiting for input.
4. **Parent Directory Isolation**: `working_directory` is passed to `Popen(cwd=...)`; `os.chdir` is never invoked, preventing directory race conditions in multithreaded runtimes.
5. **NUL Byte Rejection**: `ExecutionRequest` rejects NUL (`\0`) characters in `argv`, `environment`, and `working_directory` before invoking OS system calls.
6. **PID Recycling Safety**: Signals must only be dispatched to process groups while ownership of the process group is established.

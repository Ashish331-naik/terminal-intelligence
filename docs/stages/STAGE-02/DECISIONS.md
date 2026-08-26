# Stage 2 Architectural Decisions

This document records the architectural decisions, trade-offs, and design rationales established during the development of Stage 2 (Deterministic Command Execution).

---

## 1. Direct Argument Vector Execution (`shell=False`) vs Shell Invocation

### Context
Executing shell commands can be done either by passing a concatenated string to a system shell (`/bin/sh -c "..."` or `cmd.exe /c "..."`) or by passing an argument vector directly to the OS kernel (`execve` / `CreateProcess`).

### Decision
`SubprocessExecutor` mandates `shell=False` and passes `request.argv` directly as a tuple of strings. No shell string conversion or `shlex.split` is performed.

### Rationale
- **Injection Immunity**: Passing arguments directly treats all parameters as literal data. Metacharacters (`;`, `|`, `&&`, `$()`, backticks, redirection symbols) cannot execute arbitrary commands.
- **Predictable Tokenization**: Eliminates quoting inconsistencies across POSIX shells, dash, bash, zsh, and Windows cmd.exe/PowerShell.
- **Process Ownership**: The spawned process is the actual target binary, not an intermediary shell process, ensuring signals, resource limits, and return codes map directly to the target program.

---

## 2. Explicit Environment Replacement vs Ambient Inheritance

### Context
When spawning a child process, the environment can either inherit the parent application's full `os.environ` dictionary or be explicitly supplied.

### Decision
`ExecutionRequest` uses an immutable `environment: tuple[tuple[str, str], ...]`. An empty tuple `()` signifies an explicitly empty environment. The adapter passes `env=dict(request.environment)` to `Popen`.

### Rationale
- **Credential Leakage Prevention**: Prevents parent process secrets, tokens, and ambient developer credentials from leaking to untrusted or third-party child binaries.
- **Execution Determinism**: Ambient variables (like `LD_LIBRARY_PATH`, locale settings, or user aliases) can alter binary behavior. Explicit environments ensure repeatable results.
- **Explicit Policy**: If future use cases require inheriting specific parent variables, that inheritance must be an intentional, upstream policy decision rather than a hidden default.

---

## 3. Monotonic Duration Measurement (`duration_ms`) vs Wall-Clock Deltas

### Context
Process execution duration can be measured by comparing wall-clock timestamps (`finished_at - started_at`) or via monotonic timer deltas (`time.monotonic()`).

### Decision
Stage 2 adds `duration_ms: int` to `ExecutionResult`, measured strictly using `time.monotonic()`. `started_at` and `finished_at` remain UTC wall-clock timestamps for audit logging.

### Rationale
- **Clock Slew and Stepping**: Wall-clock timestamps (`datetime.now(UTC)`) are subject to NTP adjustments, daylight saving transitions, and leap seconds, which can cause elapsed time calculations to be negative or grossly inaccurate.
- **Monotonic Guarantee**: `time.monotonic()` is guaranteed to be non-decreasing, providing an accurate, jitter-free measurement of elapsed execution duration.

---

## 4. Non-Zero Exit Code as Structured Data vs Exception Raising

### Context
When a child process exits with a non-zero exit code (e.g. `1` or `127`), execution frameworks often raise a `CalledProcessError` exception.

### Decision
Non-zero exit codes are mapped to `ExecutionStatus.FAILED` with `exit_code: int` and captured stdout/stderr, returned as a valid `ExecutionResult`.

### Rationale
- **Non-Zero Exit is an Observation**: In command orchestration, non-zero exit is normal operational data (e.g. `grep` returning `1` when a pattern is not found, or `diff` returning `1` when differences exist).
- **Audit Completeness**: Raising an exception would lose structured stdout, stderr, and duration metadata needed by downstream diagnosis and verification layers.
- **Exception Purity**: Exceptions in `SubprocessExecutor` are reserved strictly for internal adapter failures, not command outcomes.

---

## 5. Bounded Memory Stream Draining with Reader Threads vs Unbounded `communicate()`

### Context
Reading output from a subprocess can use `Popen.communicate()` (which buffers unbounded output in memory) or dedicated reader threads that enforce byte limits.

### Decision
`SubprocessExecutor` implements custom background reader threads that read pipe chunks, enforce a configurable `max_output_bytes` (default 1 MiB) limit, set truncation flags, and continue draining discarded bytes until EOF.

### Rationale
- **Memory Denial of Service Protection**: An errant process emitting gigabytes of output (e.g. `cat /dev/zero` or infinite loops) would exhaust host memory if buffered unboundedly.
- **Deadlock Prevention**: OS pipe buffers are small (typically 64 KiB). If reading stops once a byte limit is reached, the pipe buffer fills up and the child blocks forever trying to write. Discarding subsequent bytes while draining ensures the child runs to completion without deadlocking.

---

## 6. Synchronous Single-Call Ownership for Stage 2

### Context
Command execution can be synchronous (blocking until complete) or asynchronous (returning a task handle or future).

### Decision
Stage 2 implements a synchronous `execute(request: ExecutionRequest) -> ExecutionResult` protocol.

### Rationale
- **Single-Call Invariant**: A single invocation owns the child from spawn through output drain and final reap; it never returns while the child process is still running.
- **Simplicity and Reliability**: Stage 2 focuses on core execution correctness without the complexity of async event loops, task cancellation queues, or streaming state machines.

---

## 7. Process Group Termination Strategy on POSIX vs Windows Job Objects

### Context
Terminating a timed-out process should ideally terminate all child processes spawned by that target.

### Decision
- On POSIX, use `start_new_session=True` and dispatch `SIGTERM`/`SIGKILL` to the process group (`os.killpg`).
- On Windows, pass `CREATE_NEW_PROCESS_GROUP` and document that descendant containment requires Windows Job Objects.

### Rationale
- **POSIX Standardization**: Process groups are the standard Unix containment mechanism for session-isolated command trees.
- **Portability Honesty**: Setting process group flags on Windows does not automatically kill descendant trees on `TerminateProcess`. Documenting this platform distinction prevents false security assumptions.

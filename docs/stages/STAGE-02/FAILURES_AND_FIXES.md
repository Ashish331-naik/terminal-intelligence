# Stage 2 Failures and Fixes

Recording failures and defects discovered during architecture, implementation, systems review, and testing ensures the engineering history reflects evidence-based refinement rather than fabricated immediate success.

---

## 1. Descendant Pipe Inheritance Hang (Unbounded Reader Thread Join)

### Failure Discovered
When testing commands that spawn detached background workers (e.g. `python3 -c "import subprocess; subprocess.Popen(['sleep', '10']); print('done')"`), the direct child process exited in 20ms. However, `SubprocessExecutor.execute()` hung for 10 seconds before returning `status=SUCCEEDED`.

### Cause
Reader threads were spawned with `daemon=False` and joined via `capture.thread.join()` with no timeout. Because the detached grandchild process inherited the stdout/stderr pipe file descriptors, the OS pipe's write end remained open. The reader thread blocked in `stream.read(_READ_SIZE)` waiting for EOF, causing `execute()` to hang for the full duration of the grandchild process, completely bypassing `request.timeout_seconds`.

### Fix and Remediation Strategy
1. Mark reader threads as `daemon=True` so they do not block interpreter shutdown.
2. Deriving thread join deadlines from the remaining execution timeout.
3. Explicitly closing parent read pipe descriptors during cleanup to unblock pending reads.
4. Ensuring POSIX process group cleanup is enforced across all completion paths.

---

## 2. POSIX PID Recycling Race Condition on Forced Termination

### Failure Discovered
In `SubprocessExecutor._terminate_after_timeout`, after `SIGTERM` was sent, `process.wait(timeout=grace)` reaped the direct child process. Line 175 evaluated `if os.name == "posix" or process.poll() is None:` which evaluated to `True` on POSIX even after the child was reaped. The executor then called `_send_termination_signal(process, _FORCE_KILL)`, invoking `os.killpg(process.pid, SIGKILL)` on an already-reaped PID.

### Cause
On POSIX systems, once a process is reaped by `waitpid`, its PID is returned to the OS allocator. In high-churn systems, the kernel can immediately reallocate that PID to a new, unrelated process group, causing `SIGKILL` to be dispatched to an innocent process.

### Fix and Remediation Strategy
Check whether graceful termination already reaped the child (`process.poll() is not None`) before attempting forced signal escalation. Avoid calling `os.killpg` on reaped PIDs, and adopt `pidfd` on modern Linux where available.

---

## 3. Overbroad Error Handling Masking Post-Spawn Failures as `START_FAILED`

### Failure Discovered
The outer `try...except (OSError, ValueError)` block in `execute` enclosed both `_start_process` and post-spawn operations (`_wait_for_process`, `_finish_capture`). If a stream decode or wait operation encountered an `OSError` or `ValueError` after a process ran for 10 seconds, the executor reported `START_FAILED`, set `started_at=None`, and discarded all captured output.

### Cause
Overly broad exception scope conflated OS spawn errors with post-spawn runtime and capture errors.

### Fix and Remediation Strategy
Confine `START_FAILED` exception mapping strictly to the `_start_process` call. Any exceptions occurring after `_start_process` succeeds are execution-time failures and must retain `started_at` timestamps and partial stream captures.

---

## 4. Windows Process Tree Containment Limitations

### Failure Discovered
Setting `creationflags=CREATE_NEW_PROCESS_GROUP` on Windows did not terminate descendant processes when the direct child was killed on timeout.

### Cause
On Windows, `TerminateProcess` operates solely on the specific process handle passed to it. Unlike POSIX process groups where `killpg` signals all descendants sharing the PGID, Windows requires Job Objects to enforce process tree containment.

### Fix and Remediation Strategy
Document the platform limitation clearly in the architecture specification: Stage 2 guarantees direct child process termination on Windows; full tree termination requires Windows Job Objects (`CreateJobObject` / `AssignProcessToJobObject`).

---

## 5. Domain Model Permitting Impossible States for `START_FAILED`

### Failure Discovered
Domain validation in `ExecutionResult.__post_init__` enforced that `START_FAILED` must contain an error string, but permitted non-None `exit_code`, non-None `started_at`, and non-empty `stdout`/`stderr`.

### Cause
Omission of negative invariant checks in `ExecutionResult.__post_init__`.

### Fix and Remediation Strategy
Add explicit validation guards in `ExecutionResult.__post_init__` enforcing that when `status == START_FAILED`, `exit_code` must be `None`, `started_at` must be `None`, and `stdout` and `stderr` must be empty strings.

---

## 6. Malformed UTF-8 Stream Decoding Crash Risk

### Failure Discovered
Child processes emitting invalid byte sequences (e.g. binary data or malformed UTF-8) caused standard `bytes.decode("utf-8")` to raise `UnicodeDecodeError`, crashing result creation.

### Cause
Default Python string decoding requires strict UTF-8 compliance.

### Fix and Remediation Strategy
Explicitly decode captured byte buffers with `decode("utf-8", errors="replace")`. Invalid byte sequences are safely replaced with Unicode replacement characters (`\ufffd`), preserving diagnostics without crashing.

---

## 7. NUL Character Injection in CWD and Environment Keys

### Failure Discovered
Passing paths or environment keys containing NUL characters (`\0`) caused low-level OS system calls (`execve`, `chdir`, `CreateProcess`) to fail with raw, unhandled `ValueError: embedded null byte`.

### Cause
C strings are null-terminated; Python strings containing `\0` cannot be safely converted to C-level string arguments by standard library wrappers.

### Fix and Remediation Strategy
Enforce domain-level validation in `_argv()`, `_environment()`, and `_optional_string()` in `models.py` to reject NUL characters immediately at domain model construction time, with clear `DomainValidationError` messages.

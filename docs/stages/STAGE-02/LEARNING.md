# Stage 2 Engineering Learnings

This document captures the systems engineering lessons and principles learned during the design, implementation, and review of Stage 2 (Deterministic Command Execution).

---

## 1. The Critical Distinction Between OS Processes and Shell Command Interpretation

A foundational lesson of Stage 2 is that the operating system kernel does not know what a "command string" is. At the kernel level (`execve` on Linux, `CreateProcess` on Windows), a program is executed with an array of distinct string pointers (`char *argv[]`).

Shells (`bash`, `zsh`, `cmd.exe`) are user-space interpreter programs that take a single string, parse it using grammar rules, split tokens on whitespace, perform variable expansion, and execute sub-commands. 

Treating arguments as an array of literal strings (`shell=False`) eliminates an entire class of security vulnerabilities (command injection, shell metacharacter expansion, accidental globbing). Direct argument vectors ensure that what was approved by policy is exactly what the kernel executes.

---

## 2. Pipe Buffers, Deadlocks, and EOF Propagation

Inter-process communication via anonymous OS pipes involves subtle concurrency semantics:
- **Buffer Exhaustion Deadlock**: OS pipe buffers are small (typically 64 KiB). If a child process writes more data than the pipe buffer can hold while the parent is waiting for the process to exit before reading, the child blocks on `write()` while the parent blocks on `wait()`. Draining pipes concurrently using separate reader threads (or `communicate`) is mandatory.
- **EOF Propagation**: An OS pipe only signals EOF to readers when **every** open file descriptor pointing to the pipe's write end is closed. If a child forks a detached grandchild that inherits the write end of stdout, the pipe will never reach EOF even if the direct child terminates. Systems software must account for surviving descendants holding open descriptors.

---

## 3. Process Group Lifecycle and the PID Recycling Hazard

Managing child processes on POSIX requires precise handling of process groups and signals:
- **Process Group Containment**: Setting `start_new_session=True` makes the child process the leader of a new process group, enabling group-wide signal delivery (`killpg`) to terminate worker subprocesses on timeout.
- **PID Recycling Hazard**: Once a process group leader exits and is reaped via `waitpid()`, its PID is released back to the OS allocator. Under high system load, the kernel can reassign that PID to an unrelated process. Dispatching signals to a PID after it has already been reaped can inadvertently kill innocent system processes. Systems software must never signal reaped PIDs.

---

## 4. Wall-Clock Timestamps vs Monotonic Clocks

Wall clocks (`datetime.now(UTC)`) and monotonic clocks (`time.monotonic()`) serve distinct architectural purposes:
- **Wall Clocks for Audit**: Wall-clock timestamps record *when in history* an event occurred. They are necessary for audit trails, compliance logs, and cross-system correlation.
- **Monotonic Clocks for Durations**: Wall clocks are subject to clock drift, NTP synchronization steps, leap seconds, and daylight saving adjustments. Calculating elapsed duration via `t1 - t0` with wall clocks can yield negative or inaccurate durations. `duration_ms` must always be calculated using a monotonic clock.

---

## 5. Memory Boundedness in Observable Systems

An AI execution layer must expect unpredictable child process output:
- Capturing unbounded output in memory (`read()` into an unlimited buffer) allows a command emitting continuous logs or infinite loops (`cat /dev/zero`) to exhaust host memory (OOM).
- Imposing a strict per-stream byte limit (`max_output_bytes`) protects host memory.
- However, simply stopping reading once the limit is reached causes a pipe buffer deadlock. The system must continue reading and discarding surplus bytes until EOF while explicitly flagging truncation (`stdout_truncated=True`) to downstream consumers.

---

## 6. Non-Zero Exit as Observability Data Rather Than Software Exceptions

In systems programming, a command exiting with a non-zero code is not an infrastructure error. Commands like `diff`, `grep`, `test`, and `git status` routinely exit non-zero to signal logical conditions (e.g. differences found, pattern absent). 

Mapping non-zero exits to structured domain results (`status=FAILED`, `exit_code=N`, `stdout="..."`, `stderr="..."`) provides downstream verification and diagnosis layers with the full diagnostic context needed to reason about failures.

---

## 7. The Necessity of Seams in Systems Testing

Testing systems code that interacts with the OS (processes, signals, clocks) requires a dual testing strategy:
- **Integration Tests**: Validate that real OS interactions work as expected on the target platform.
- **Unit Seams**: Without injectable seams for clock providers, process factories, and UUID generators, testing subtle edge cases (clock skew, thread starvation, signal races) becomes flaky or impossible. Incorporating test seams early in adapter designs ensures deterministic testability.

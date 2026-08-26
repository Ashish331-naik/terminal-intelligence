# Stage 2 Overview: Deterministic Command Execution

## Purpose

Stage 2 introduces the execution foundation of the Terminal Intelligence Layer. Its sole responsibility is to take an approved, immutable `ExecutionRequest` argument vector (`argv`), execute it directly on the operating system without an intermediary shell, capture standard streams deterministically with memory bounds, enforce strict timeouts, and return an immutable `ExecutionResult`.

Stage 2 does not generate commands, classify risk, request user approval, verify semantic intent, diagnose failures, or repair commands. It establishes the mechanical execution boundary that downstream workflows will rely upon.

```text
+------------------------+
|      Application       |
| (Stage 1 Request Prep) |
+-----------+------------+
            | ExecutionRequest (argv, env, cwd, timeout)
            v
+------------------------+
| ports.CommandExecutor  |  <--- Interface boundary
+-----------+------------+
            |
            v
+------------------------------------+
| adapters.process.SubprocessExecutor|  <--- Direct argv execution
+-----------+------------------------+
            |
    +-------+-------+
    |               |
    v               v
 [POSIX Session]  [Windows Group]
 [killpg tree  ]  [Process Handle]
    |               |
    +-------+-------+
            |
            v
     OS Child Process (stdin=DEVNULL, stdout/stderr captured)
            |
            v
     ExecutionResult (status, exit_code, stdout, stderr, duration_ms)
```

---

## Fundamentals of OS Process Execution

To understand the architecture and security boundaries of Stage 2, several core operating system concepts must be distinguished:

### 1. What OS Process Execution Means
An operating system process is an isolated execution environment containing its own virtual address space, memory mappings, file descriptor table, security credentials, and execution threads. Executing a program at the OS level involves:
1. Allocating an address space and process control block (PCB).
2. Loading the executable binary (ELF on Linux, Mach-O on macOS, PE on Windows) or passing an interpreter script via the shebang (`#!`) mechanism.
3. Initializing stack, heap, and CPU registers.
4. Setting up standard file descriptors (0: stdin, 1: stdout, 2: stderr).
5. Passing the argument array (`argv`) and environment mapping (`envp`) directly to the executable's entry point (`main(int argc, char *argv[])`).

### 2. Parent vs Child Process
When `SubprocessExecutor` executes a command:
- **Parent Process**: The running Python application. It owns the main loop, allocates memory, opens bidirectional pipe descriptors, and monitors child lifecycle.
- **Child Process**: The newly created OS process. It inherits specific configured resources, runs the target binary, and executes concurrently with the parent.
- **IPC (Inter-Process Communication)**: Unidirectional anonymous OS pipes connect the child's stdout/stderr to the parent's read handles. The parent process is responsible for draining these pipes to prevent pipe buffer exhaustion and deadlock.

### 3. Argument Vector (`argv`) vs Shell Command String
- **Argument Vector (`tuple[str, ...]`)**: An ordered sequence of distinct strings. `argv[0]` is the executable program name or path, and `argv[1:]` are literal parameters passed directly to the program. The operating system kernel performs no interpretation, splitting, globbing, or substitution on these elements. Spaces, quotes, dollar signs (`$`), semicolons (`;`), and pipes (`|`) remain literal data.
- **Shell Command String (`str`)**: A single string passed to `/bin/sh -c "string"` or `cmd.exe /c "string"`. A shell program parses this string into tokens, expands environment variables (`$VAR`), executes subshells (`$(cmd)` or `` `cmd` ``), expands wildcards (`*.txt`), interprets control operators (`&&`, `||`, `;`), and sets up redirections (`>`, `<`).

### 4. Why `shell=False` Matters
Passing `shell=False` directly executes the target binary with the exact `argv` elements. This is the primary security defense against command injection:
- If `shell=True` were used, an argument vector containing untrusted inputs like `["cat", "file; rm -rf /"]` would be concatenated into a string and parsed by the shell, executing `rm -rf /` as a second command.
- With `shell=False`, the OS passes `"file; rm -rf /"` as a single literal filename parameter to `cat`. `cat` attempts to open that literal file and fails safely with `No such file or directory`.

### 5. Standard Streams (`stdin`, `stdout`, `stderr`)
- **`stdin` (Standard Input)**: Configured as `subprocess.DEVNULL`. The child process receives immediate EOF if it attempts to read interactive input. This prevents children from blocking the executor waiting for terminal keyboard input.
- **`stdout` (Standard Output)**: Captured via an anonymous OS pipe. Drained asynchronously by a dedicated reader thread into memory up to a configurable byte limit (default: 1 MiB).
- **`stderr` (Standard Error)**: Captured via a separate anonymous OS pipe. Drained independently from `stdout` to ensure diagnostics and logs remain unmixed.

### 6. Exit Codes
When an OS process terminates, its exit status is preserved in the kernel until reaped by the parent via `waitpid` (POSIX) or `GetExitCodeProcess` (Windows):
- **Exit Code `0`**: Standard convention for successful execution. Mapped to `ExecutionStatus.SUCCEEDED`.
- **Exit Code `> 0`**: Process-specific non-zero exit code indicating an application-level failure, syntax error, or runtime condition. Mapped to `ExecutionStatus.FAILED`.
- **Exit Code `< 0` (POSIX)**: Process terminated by an unhandled signal (e.g., `-15` for `SIGTERM`, `-9` for `SIGKILL`). Preserved in `ExecutionResult.exit_code`.

### 7. Non-Zero Exit Code is Data, Not Application Failure
In command execution engines, a non-zero exit code from a child process is an expected observation, not a failure of the execution engine. For example, running `grep "foo" file.txt` returning exit code `1` means "pattern not found", which is a valid result. The executor must record this as `status=FAILED` with `exit_code=1` and all captured stderr/stdout, rather than raising a Python exception.

---

## What Stage 2 Introduces

1. **Domain Request/Result Extensions**:
   - `ExecutionRequest`: Added finite positive `timeout_seconds` and immutable `environment: tuple[tuple[str, str], ...]`.
   - `ExecutionResult`: Added monotonic `duration_ms`, `stdout_truncated`, and `stderr_truncated`.
2. **`ports.CommandExecutor`**:
   - A clean protocol defining `execute(request: ExecutionRequest) -> ExecutionResult`.
3. **`adapters.process.SubprocessExecutor`**:
   - Synchronous, direct-argv process execution using `subprocess.Popen`.
   - Bounded memory capture with non-deadlocking stream drain threads.
   - UTF-8 decoding with `errors="replace"` to ensure malformed output cannot crash the application.
   - POSIX process group isolation (`start_new_session=True`) and graceful-then-forced timeout termination.
   - Working directory enforcement without mutating parent process directory (`os.chdir`).
   - Clean separation between OS spawn failures (`START_FAILED`) and command exit outcomes (`SUCCEEDED`, `FAILED`, `TIMED_OUT`).

---

## Non-Goals (What Stage 2 Intentionally Cannot Do)

Stage 2 deliberately excludes:
- **No Shell Interpreter**: Does not support shell syntax, pipelines (`|`), logical chaining (`&&`, `||`), redirection (`>`, `<`), or globbing (`*`).
- **No Natural Language / LLM Logic**: Does not convert user prompts to commands.
- **No Risk Classification or Approval**: Assumes the `ExecutionRequest` has already been analyzed and authorized upstream.
- **No Interactive Sessions (PTY / TTY)**: Does not provide terminal emulation, password prompts, or interactive REPLs.
- **No Background Daemon Management**: Does not manage detached services across request lifecycles.
- **No Command Repair or Verification**: Does not inspect stdout to decide whether a command achieved its semantic goal.

---

## Definition of Done

Stage 2 is complete when:
1. `ExecutionRequest` and `ExecutionResult` domain models support timeouts, explicit environments, and monotonic duration.
2. `CommandExecutor` port is defined in `terminal_intelligence.ports`.
3. `SubprocessExecutor` implements `CommandExecutor` using `subprocess.Popen(shell=False)` with deterministic output, exit codes, timeout handling, and resource cleanup.
4. All unit, validation, serialization, and integration tests pass with 100% verification compliance (`make verify`).
5. Process management edge cases, security assumptions, and platform limitations are comprehensively documented.

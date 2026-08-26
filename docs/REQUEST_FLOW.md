# Terminal Intelligence: Request and Execution Flow

This document details the end-to-end lifecycle of a request as it progresses through the Terminal Intelligence Layer.

---

## High-Level Sequence Diagram

```text
User / Caller                 Application Use Case                ports.CommandExecutor              SubprocessExecutor                 OS Kernel
     |                                 |                                    |                                 |                             |
     | 1. Submit text request          |                                    |                                 |                             |
     |-------------------------------->|                                    |                                 |                             |
     |                                 |                                    |                                 |                             |
     |                                 | 2. Create UserRequest              |                                 |                             |
     |                                 | 3. Propose CommandProposal (argv)  |                                 |                             |
     |                                 | 4. Record ApprovalDecision         |                                 |                             |
     |                                 | 5. Construct ExecutionRequest      |                                 |                             |
     |                                 |                                    |                                 |                             |
     |                                 | 6. execute(request)                |                                 |                             |
     |                                 |----------------------------------->|                                 |                             |
     |                                 |                                    | 7. execute(request)             |                             |
     |                                 |                                    |-------------------------------->|                             |
     |                                 |                                    |                                 | 8. time.monotonic() start   |
     |                                 |                                    |                                 | 9. Popen(argv, shell=False) |
     |                                 |                                    |                                 |---------------------------->|
     |                                 |                                    |                                 |                             |--+ 10. Fork & execve
     |                                 |                                    |                                 |                             |  | (stdin=DEVNULL)
     |                                 |                                    |                                 |                             |<-+
     |                                 |                                    |                                 | 11. Start reader threads    |
     |                                 |                                    |                                 |=============================|
     |                                 |                                    |                                 | [Async Pipe Drain stdout/err|
     |                                 |                                    |                                 | 12. process.wait(timeout)   |
     |                                 |                                    |                                 |---------------------------->|
     |                                 |                                    |                                 |                             |
     |                                 |                                    |                                 |  (Process executes/exits)   |
     |                                 |                                    |                                 |<----------------------------|
     |                                 |                                    |                                 | 13. Reaped & Return code    |
     |                                 |                                    |                                 | 14. Join reader threads     |
     |                                 |                                    |                                 | 15. Decode streams (UTF-8)  |
     |                                 |                                    |                                 | 16. Calculate duration_ms   |
     |                                 |                                    |                                 | 17. Construct ExecutionResult|
     |                                 |                                    |<--------------------------------|                             |
     |                                 |<-----------------------------------|                                 |                             |
     |                                 | 18. Return ExecutionResult         |                                 |                             |
     |                                 | 19. Create VerificationResult      |                                 |                             |
     |                                 |                                    |                                 |                             |
     | 20. Structured Response         |                                    |                                 |                             |
     |<--------------------------------|                                    |                                 |                             |
```

---

## Detailed Step-by-Step Flow

### Step 1: Request Submission & Domain Ingestion
1. The user provides a natural-language prompt (e.g. `"find processes on port 8000"`).
2. The application constructs an immutable [`UserRequest`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/models.py#L193-L224):
   - Generates a fresh `request_id: UUID`.
   - Records UTC `submitted_at: datetime`.
   - Validates that `text` is non-empty.

### Step 2: Proposal Planning (Future Stage 3)
1. The planning subsystem parses intent and generates a candidate argument vector `argv: ("lsof", "-i", ":8000")`.
2. Constructs an immutable [`CommandProposal`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/models.py#L225-L276):
   - Generates a fresh `proposal_id: UUID`.
   - Assigns a [`CommandRisk`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/enums.py#L6-L14) level (e.g. `LOW`).
   - Validates that `argv` contains no NUL bytes and has a valid executable.

### Step 3: Approval and Policy Check (Future Stage 4)
1. The proposed command is reviewed by human or automated policy.
2. Constructs an [`ApprovalDecision`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/models.py#L277-L335):
   - Generates a `decision_id: UUID`.
   - Outcome is set to `ApprovalOutcome.APPROVED` or `REJECTED`.

### Step 4: Execution Request Preparation
1. The application transforms the approved proposal into an [`ExecutionRequest`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/models.py#L337-L422):
   - Generates an `execution_request_id: UUID`.
   - Copies `argv` from the proposal.
   - Sets execution environment (`environment: tuple[tuple[str, str], ...]`).
   - Sets working directory (`working_directory: str | None`).
   - Sets timeout limit (`timeout_seconds: float`).
   - Validates all invariants via `ExecutionRequest.__post_init__`.

### Step 5: Port Invocation
1. The application use case calls `executor.execute(request)` where `executor` satisfies the [`CommandExecutor`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/ports/execution.py#L8-L13) protocol.

### Step 6: Subprocess Execution Lifecycle ([`SubprocessExecutor`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/adapters/process/subprocess_executor.py#L35-L50))
1. **Clock Initialization**: Records `started_clock = time.monotonic()` and `attempted_at = datetime.now(UTC)`.
2. **Process Spawn ([`_start_process`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/adapters/process/subprocess_executor.py#L100-L115))**:
   - Calls `subprocess.Popen(request.argv, shell=False, stdin=DEVNULL, stdout=PIPE, stderr=PIPE, env=..., cwd=..., start_new_session=True)`.
   - If spawn fails (`FileNotFoundError`, `PermissionError`, `OSError`), execution immediately returns `ExecutionStatus.START_FAILED`.
3. **Capture Threads Started ([`_start_capture_threads`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/adapters/process/subprocess_executor.py#L117-L134))**:
   - Spawns two background reader threads to drain stdout and stderr concurrently into memory bytearrays up to `max_output_bytes`.
4. **Process Wait & Timeout Management ([`_wait_for_process`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/adapters/process/subprocess_executor.py#L163-L170))**:
   - Calls `process.wait(timeout=request.timeout_seconds)`.
   - If the timeout expires:
     - Sends `SIGTERM` to the process group (`os.killpg`).
     - Waits for grace period (`0.2s`).
     - Sends `SIGKILL` if still running.
     - Sets status to `ExecutionStatus.TIMED_OUT`.
5. **Stream Capture Finalization ([`_finish_capture`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/adapters/process/subprocess_executor.py#L150-L161))**:
   - Joins reader threads once pipes reach EOF.
   - Decodes captured bytes as UTF-8 with `errors="replace"`.
   - Notes whether output exceeded limits (`stdout_truncated`, `stderr_truncated`).
6. **Result Assembly ([`_result`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/adapters/process/subprocess_executor.py#L209-L243))**:
   - Computes monotonic `duration_ms = round((time.monotonic() - started_clock) * 1000)`.
   - Records UTC `finished_at = datetime.now(UTC)`.
   - Maps return code `0` to `SUCCEEDED`, non-zero to `FAILED`.
   - Instantiates and returns the immutable [`ExecutionResult`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/models.py#L424-L595).

### Step 7: Post-Execution Verification (Future Stage 5)
1. Downstream verification compares the `ExecutionResult` against expected success criteria and generates a [`VerificationResult`](file:///home/ashish/Projects/Terminal%20Intelligence/src/terminal_intelligence/domain/models.py#L596-L655).

# Stage 2 Test Report

## Verification Overview

Stage 2 was validated through automated verification gates covering formatting, linting, strict type checking, unit and integration tests, dependency vulnerability auditing, pre-commit hygiene, and isolated wheel build/import testing.

### Verification Commands Run

```bash
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy
uv run --locked pytest
uv run --locked pip-audit
uv run --locked pre-commit run --all-files
make build-wheel-test
```

### Actual Verification Results

```text
uv run --locked ruff format --check .
38 files already formatted

uv run --locked ruff check .
All checks passed!

uv run --locked mypy
Success: no issues found in 16 source files

uv run --locked pytest
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/ashish/Projects/Terminal Intelligence
configfile: pyproject.toml
testpaths: tests
plugins: cov-6.3.0
collected 68 items

tests/unit/adapters/test_subprocess_executor.py ............................... [ 45%]
tests/unit/adapters/test_subprocess_executor_unit.py ....                       [ 51%]
tests/unit/domain/test_models.py ........                                      [ 63%]
tests/unit/domain/test_serialization.py ........                               [ 75%]
tests/unit/domain/test_validation.py ................                          [ 98%]
tests/unit/test_package.py .                                                   [100%]

============================== 68 passed in 2.22s ==============================

uv run --locked pip-audit
No known vulnerabilities found

uv run --locked pre-commit run --all-files
trim trailing whitespace.................................................Passed
fix end of files.........................................................Passed
check yaml...............................................................Passed
check toml...............................................................Passed
ruff check...............................................................Passed
ruff format..............................................................Passed
mypy.....................................................................Passed

uv build --out-dir dist
Building source distribution...
Building wheel from source distribution...
Successfully built dist/terminal_intelligence-0.1.0.tar.gz
Successfully built dist/terminal_intelligence-0.1.0-py3-none-any.whl
Installed 1 package in 1ms (verified isolated import outside workspace)
```

---

## Test Category Breakdown

Total Test Count: **68 Tests**

| Test Module | Category | Count | Focus |
| :--- | :--- | :--- | :--- |
| `tests/unit/adapters/test_subprocess_executor.py` | Subprocess Integration & Process Control | 31 | Real OS process execution, timeouts, signals, stream capture, bounds, encoding, environment, cwd |
| `tests/unit/adapters/test_subprocess_executor_unit.py` | Subprocess Unit & Seam Tests | 4 | Injected clock, mock process, and protocol conformance tests |
| `tests/unit/domain/test_validation.py` | Domain Invariant Validation | 16 | Input validation, NUL byte rejection, finite timeouts, duplicate env keys, impossible states |
| `tests/unit/domain/test_models.py` | Model Construction & Immutability | 8 | Dataclass defaults, slot immutability, timestamp ordering, exit code constraints |
| `tests/unit/domain/test_serialization.py` | Schema & Serialization | 8 | JSON round-trip, RFC 3339 timestamps, UUID conversion, unknown field rejection |
| `tests/unit/test_package.py` | Package Foundation | 1 | Importability and packaging integrity |

---

## Key Adversarial and Edge-Case Tests

### 1. Shell Syntax Passed as Literal Data
- **Test**: `test_argument_vector_preserves_shell_syntax_as_data`
- **Vectors Tested**: `;`, `&&`, `||`, `|`, `>`, `>>`, `<`, `$(echo injected)`, `` `echo injected` ``, `*.txt`, `$STAGE2_TEST_VALUE`, `'single quoted'`, `'"double quoted"'`, `"line one\nline two"`.
- **Assertion**: Each argument is received by the target binary as an exact, unparsed, unexpanded string literal. Proves `shell=False` non-injection invariant.

### 2. Stream Deadlock Resistance with High Volume Output
- **Test**: `test_large_stdout_and_stderr_are_drained_without_deadlock`
- **Vectors Tested**: 128 KiB written concurrently to stdout and stderr (exceeding standard 64 KiB OS pipe buffer).
- **Assertion**: The reader threads drain both streams concurrently without deadlocking the child process or parent execution.

### 3. Memory Bound Enforcement and Truncation Flagging
- **Test**: `test_output_capture_is_bounded_and_reports_truncation`
- **Vectors Tested**: Process emits 4096 bytes on stdout and stderr with `max_output_bytes=128`.
- **Assertion**: Output length is exactly capped at 128 characters, reader threads drain remaining bytes to EOF, and `stdout_truncated=True` and `stderr_truncated=True`.

### 4. Malformed and Invalid UTF-8 Stream Decoding
- **Test**: `test_output_decodes_unicode_and_replaces_invalid_utf8`
- **Vectors Tested**: Process emits raw invalid byte sequences `b'bad\xff\xfe\n'` and `b'err\x80\n'`.
- **Assertion**: Bytes are decoded using UTF-8 replacement characters (`\ufffd`) without raising `UnicodeDecodeError` or crashing result creation.

### 5. Descendant Process-Group Termination on Timeout
- **Test**: `test_timeout_terminates_descendants_in_the_process_group`
- **Vectors Tested**: Parent spawns a child that spawns a background worker (`time.sleep(0.4)`) and sleeps 10s. Request timeout is 0.05s.
- **Assertion**: On timeout, `SIGTERM` is dispatched to the entire process group, terminating both parent and descendant, preventing marker file creation.

### 6. Force-Kill Escalation for SIGTERM-Ignoring Descendants
- **Test**: `test_timeout_force_kills_descendant_ignoring_sigterm`
- **Vectors Tested**: Descendant sets `signal.signal(signal.SIGTERM, signal.SIG_IGN)`.
- **Assertion**: After `termination_grace_seconds=0.02s` expires, `_FORCE_KILL` (`SIGKILL`) is dispatched to the process group, terminating the uncooperative process.

### 7. Environment Isolation and Leakage Prevention
- **Test**: `test_empty_environment_does_not_inherit_parent_environment`
- **Vectors Tested**: Parent environment contains `STAGE2_PARENT_ONLY_VALUE` and ambient `PATH`. Command executed with `environment=()`.
- **Assertion**: Child reports `<missing>` for both variables. Parent process environment is completely shielded.

### 8. Directory Injection and CWD Space Safety
- **Test**: `test_cwd_with_spaces_is_passed_as_one_value` & `test_nul_working_directory_is_a_structured_start_failure`
- **Vectors Tested**: Directory path containing spaces; path containing NUL byte (`"invalid\0directory"`).
- **Assertion**: Space-containing CWD is passed intact as a single path; NUL-containing CWD is caught at spawn time and safely mapped to `START_FAILED`.

### 9. Input Disconnection (`stdin=DEVNULL`)
- **Test**: `test_stdin_is_closed_instead_of_inherited`
- **Vectors Tested**: Target executable attempts `sys.stdin.read()`.
- **Assertion**: Receives immediate EOF (`''`), ensuring the child cannot block waiting for interactive terminal input.

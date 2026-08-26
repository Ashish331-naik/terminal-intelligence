"""Deterministic subprocess execution tests."""

import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from terminal_intelligence.adapters.process import SubprocessExecutor
from terminal_intelligence.domain import ExecutionRequest, ExecutionStatus
from terminal_intelligence.ports import CommandExecutor

REQUEST_ID = UUID("00000000-0000-0000-0000-000000000001")
PROPOSAL_ID = UUID("00000000-0000-0000-0000-000000000002")
EXECUTION_ID = UUID("00000000-0000-0000-0000-000000000004")
REQUESTED_AT = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)


def test_subprocess_executor_satisfies_command_executor_protocol() -> None:
    executor: CommandExecutor = SubprocessExecutor()

    assert callable(executor.execute)


def request(
    *argv: str,
    timeout_seconds: float = 2.0,
    working_directory: str | None = None,
    environment: tuple[tuple[str, str], ...] = (),
) -> ExecutionRequest:
    return ExecutionRequest(
        EXECUTION_ID,
        REQUEST_ID,
        PROPOSAL_ID,
        argv,
        REQUESTED_AT,
        working_directory=working_directory,
        timeout_seconds=timeout_seconds,
        environment=environment,
    )


def python_request(
    code: str,
    *arguments: str,
    timeout_seconds: float = 2.0,
    working_directory: str | None = None,
    environment: tuple[tuple[str, str], ...] = (),
) -> ExecutionRequest:
    return request(
        sys.executable,
        "-c",
        code,
        *arguments,
        timeout_seconds=timeout_seconds,
        working_directory=working_directory,
        environment=environment,
    )


def test_successful_command() -> None:
    result = SubprocessExecutor().execute(python_request("raise SystemExit(0)"))

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.exit_code == 0
    assert result.error is None
    assert result.duration_ms >= 0


def test_command_returning_nonzero() -> None:
    result = SubprocessExecutor().execute(python_request("raise SystemExit(7)"))

    assert result.status is ExecutionStatus.FAILED
    assert result.exit_code == 7


def test_stdout_capture() -> None:
    result = SubprocessExecutor().execute(python_request("print('standard output')"))

    assert result.stdout == "standard output\n"
    assert result.stderr == ""


def test_stderr_capture() -> None:
    result = SubprocessExecutor().execute(
        python_request("import sys; print('standard error', file=sys.stderr)")
    )

    assert result.stdout == ""
    assert result.stderr == "standard error\n"


def test_empty_output_is_preserved() -> None:
    result = SubprocessExecutor().execute(python_request("raise SystemExit(0)"))

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.stdout == ""
    assert result.stderr == ""


def test_nonexistent_executable() -> None:
    result = SubprocessExecutor().execute(request("/definitely/not/a/real/executable"))

    assert result.status is ExecutionStatus.START_FAILED
    assert result.exit_code is None
    assert result.error is not None


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission semantics are under test")
def test_non_executable_file_is_a_start_failure(tmp_path: Path) -> None:
    executable = tmp_path / "not-executable"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o600)

    result = SubprocessExecutor().execute(request(str(executable)))

    assert result.status is ExecutionStatus.START_FAILED
    assert result.exit_code is None
    assert result.stdout == ""
    assert result.stderr == ""


def test_invalid_working_directory_is_a_start_failure(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    file_path = tmp_path / "regular-file"
    file_path.write_text("not a directory", encoding="utf-8")

    for working_directory in (str(missing), str(file_path)):
        result = SubprocessExecutor().execute(
            python_request("raise SystemExit(0)", working_directory=working_directory)
        )

        assert result.status is ExecutionStatus.START_FAILED
        assert result.exit_code is None
        assert result.stdout == ""
        assert result.stderr == ""


def test_malformed_environment_key_is_a_structured_start_failure() -> None:
    result = SubprocessExecutor().execute(
        python_request("raise SystemExit(0)", environment=(("BAD=KEY", "value"),))
    )

    assert result.status is ExecutionStatus.START_FAILED
    assert result.exit_code is None
    assert result.stdout == ""
    assert result.stderr == ""
    assert result.error is not None


def test_nul_working_directory_is_a_structured_start_failure() -> None:
    result = SubprocessExecutor().execute(
        python_request("raise SystemExit(0)", working_directory="invalid\0directory")
    )

    assert result.status is ExecutionStatus.START_FAILED
    assert result.exit_code is None
    assert result.stdout == ""
    assert result.stderr == ""
    assert result.error is not None


def test_immediate_crash_is_a_failed_child_not_a_start_failure() -> None:
    result = SubprocessExecutor().execute(python_request("raise RuntimeError('crash')"))

    assert result.status is ExecutionStatus.FAILED
    assert result.exit_code != 0
    assert "RuntimeError" in result.stderr


def test_timeout_terminates_process() -> None:
    result = SubprocessExecutor().execute(
        python_request(
            "import time; print('before timeout', flush=True); time.sleep(10)",
            timeout_seconds=0.1,
        )
    )

    assert result.status is ExecutionStatus.TIMED_OUT
    assert result.error == "process exceeded its timeout"
    assert result.stdout == "before timeout\n"
    assert result.duration_ms >= 0


def test_timeout_preserves_partial_stdout_and_stderr() -> None:
    result = SubprocessExecutor().execute(
        python_request(
            "import sys, time; print('stdout prefix', flush=True); "
            "print('stderr prefix', file=sys.stderr, flush=True); time.sleep(10)",
            timeout_seconds=0.1,
        )
    )

    assert result.status is ExecutionStatus.TIMED_OUT
    assert result.stdout == "stdout prefix\n"
    assert result.stderr == "stderr prefix\n"
    assert result.error is not None


def test_extremely_small_timeout_is_enforced() -> None:
    result = SubprocessExecutor().execute(
        python_request("import time; time.sleep(0.2)", timeout_seconds=0.01)
    )

    assert result.status is ExecutionStatus.TIMED_OUT
    assert result.error == "process exceeded its timeout"


def test_repeated_timeouts_return_after_reaping_each_child() -> None:
    executor = SubprocessExecutor()

    results = [
        executor.execute(python_request("import time; time.sleep(0.2)", timeout_seconds=0.01))
        for _ in range(3)
    ]

    assert [result.status for result in results] == [
        ExecutionStatus.TIMED_OUT,
        ExecutionStatus.TIMED_OUT,
        ExecutionStatus.TIMED_OUT,
    ]
    assert all(result.exit_code is not None for result in results)


@pytest.mark.skipif(os.name != "posix", reason="process-group semantics are POSIX-specific")
def test_timeout_terminates_descendants_in_the_process_group(tmp_path: Path) -> None:
    marker = tmp_path / "descendant-survived"
    descendant_code = (
        "import pathlib, sys, time; time.sleep(0.4); "
        "pathlib.Path(sys.argv[1]).write_text('survived', encoding='utf-8')"
    )
    parent_code = (
        "import subprocess, sys, time; "
        "subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]]); "
        "print('parent started', flush=True); time.sleep(10)"
    )

    result = SubprocessExecutor().execute(
        python_request(
            parent_code,
            descendant_code,
            str(marker),
            timeout_seconds=0.05,
        )
    )

    assert result.status is ExecutionStatus.TIMED_OUT
    assert result.stdout == "parent started\n"
    time.sleep(0.6)
    assert not marker.exists()


@pytest.mark.skipif(os.name != "posix", reason="process-group semantics are POSIX-specific")
def test_timeout_force_kills_descendant_ignoring_sigterm(tmp_path: Path) -> None:
    marker = tmp_path / "ignoring-descendant-survived"
    descendant_code = (
        "import pathlib, signal, sys, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "time.sleep(0.4); pathlib.Path(sys.argv[1]).write_text('survived', encoding='utf-8')"
    )
    parent_code = (
        "import subprocess, sys, time; "
        "subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]]); "
        "time.sleep(10)"
    )

    result = SubprocessExecutor(termination_grace_seconds=0.02).execute(
        python_request(
            parent_code,
            descendant_code,
            str(marker),
            timeout_seconds=0.05,
        )
    )

    assert result.status is ExecutionStatus.TIMED_OUT
    time.sleep(0.6)
    assert not marker.exists()


def test_cwd_handling(tmp_path: Path) -> None:
    parent_cwd = os.getcwd()
    result = SubprocessExecutor().execute(
        python_request("import os; print(os.getcwd())", working_directory=str(tmp_path))
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.stdout == f"{tmp_path}{os.linesep}"
    assert os.getcwd() == parent_cwd


def test_cwd_with_spaces_is_passed_as_one_value(tmp_path: Path) -> None:
    directory = tmp_path / "directory with spaces"
    directory.mkdir()

    result = SubprocessExecutor().execute(
        python_request("import os; print(os.getcwd())", working_directory=str(directory))
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.stdout == f"{directory}{os.linesep}"


def test_environment_handling() -> None:
    result = SubprocessExecutor().execute(
        python_request(
            "import os; print(os.environ['STAGE2_TEST_VALUE'])",
            environment=(("STAGE2_TEST_VALUE", "controlled-value"),),
        )
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.stdout == "controlled-value\n"


def test_empty_environment_does_not_inherit_parent_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = "STAGE2_PARENT_ONLY_VALUE"
    monkeypatch.setenv(key, "parent-value")

    result = SubprocessExecutor().execute(
        python_request(
            "import os; print(os.getenv('STAGE2_PARENT_ONLY_VALUE', '<missing>')); "
            "print(os.getenv('PATH', '<missing>'))"
        )
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.stdout == "<missing>\n<missing>\n"
    assert os.environ[key] == "parent-value"


def test_environment_overrides_parent_without_mutating_it(monkeypatch: pytest.MonkeyPatch) -> None:
    key = "STAGE2_OVERRIDE_VALUE"
    monkeypatch.setenv(key, "parent-value")

    result = SubprocessExecutor().execute(
        python_request(
            "import os; print(os.environ['STAGE2_OVERRIDE_VALUE'])",
            environment=((key, "child-value"),),
        )
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.stdout == "child-value\n"
    assert os.environ[key] == "parent-value"


def test_controlled_path_can_resolve_a_bare_executable() -> None:
    executable_name = Path(sys.executable).name
    executable_directory = str(Path(sys.executable).parent)

    result = SubprocessExecutor().execute(
        request(
            executable_name,
            "-c",
            "print('resolved through controlled path')",
            environment=(("PATH", executable_directory),),
        )
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.stdout == "resolved through controlled path\n"


def test_stdin_is_closed_instead_of_inherited() -> None:
    result = SubprocessExecutor().execute(
        python_request("import sys; print(repr(sys.stdin.read()))")
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.stdout == "''\n"


def test_arguments_containing_spaces_are_not_split() -> None:
    result = SubprocessExecutor().execute(
        python_request("import sys; print(sys.argv[1])", "argument with spaces")
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.stdout == "argument with spaces\n"


def test_argument_vector_preserves_shell_syntax_as_data() -> None:
    arguments = (
        ";",
        "&&",
        "||",
        "|",
        ">",
        ">>",
        "<",
        "$(echo injected)",
        "`echo injected`",
        "*.txt",
        "$STAGE2_TEST_VALUE",
        "'single quoted'",
        '"double quoted"',
        "line one\nline two",
    )
    result = SubprocessExecutor().execute(
        python_request(
            "import json, sys; print(json.dumps(sys.argv[1:], ensure_ascii=False))",
            *arguments,
        )
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.exit_code == 0
    assert result.stdout == f"{json.dumps(list(arguments), ensure_ascii=False)}\n"


def test_argument_vector_preserves_empty_unicode_quotes_and_flags() -> None:
    arguments = ("", "привет мир", "--flag=value", "path with spaces/file.txt", 'a"b')
    result = SubprocessExecutor().execute(
        python_request(
            "import json, sys; print(json.dumps(sys.argv[1:], ensure_ascii=False))",
            *arguments,
        )
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.stdout == f"{json.dumps(list(arguments), ensure_ascii=False)}\n"


def test_large_stdout_and_stderr_are_drained_without_deadlock() -> None:
    size = 128 * 1024
    result = SubprocessExecutor().execute(
        python_request(
            "import sys; sys.stdout.write('o' * int(sys.argv[1])); "
            "sys.stderr.write('e' * int(sys.argv[1]))",
            str(size),
        )
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.stdout == "o" * size
    assert result.stderr == "e" * size


def test_output_capture_is_bounded_and_reports_truncation() -> None:
    result = SubprocessExecutor(max_output_bytes=128).execute(
        python_request("import sys; sys.stdout.write('o' * 4096); sys.stderr.write('e' * 4096)")
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert len(result.stdout) == 128
    assert len(result.stderr) == 128
    assert result.stdout == "o" * 128
    assert result.stderr == "e" * 128
    assert result.stdout_truncated is True
    assert result.stderr_truncated is True


def test_output_decodes_unicode_and_replaces_invalid_utf8() -> None:
    result = SubprocessExecutor().execute(
        python_request(
            "import os; os.write(1, 'π\\n'.encode()); os.write(1, b'bad\\xff\\xfe\\n'); "
            "os.write(2, b'err\\x80\\n')"
        )
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.stdout == "π\nbad��\n"
    assert result.stderr == "err�\n"

"""Pure unit tests for executor lifecycle seams."""

import signal
import subprocess
import threading
from datetime import UTC, datetime
from io import BytesIO
from typing import IO, cast
from uuid import UUID

import pytest

from terminal_intelligence.adapters.process.subprocess_executor import (
    PopenFactory,
    SubprocessExecutor,
)
from terminal_intelligence.domain import ExecutionRequest, ExecutionStatus

REQUEST_ID = UUID("00000000-0000-0000-0000-000000000001")
PROPOSAL_ID = UUID("00000000-0000-0000-0000-000000000002")
EXECUTION_ID = UUID("00000000-0000-0000-0000-000000000004")
RESULT_ID = UUID("00000000-0000-0000-0000-000000000005")
REQUESTED_AT = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)


class FakeProcess:
    """Small Popen-shaped fake for tests that do not need an OS process."""

    pid = 1234

    def __init__(self, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.stdout: IO[bytes] = BytesIO(stdout)
        self.stderr: IO[bytes] = BytesIO(stderr)
        self.returncode: int | None = 0
        self.wait_calls: list[float | None] = []

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls.append(timeout)
        assert self.returncode is not None
        return self.returncode

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.returncode = -int(signal.SIGTERM)

    def kill(self) -> None:
        self.returncode = -int(getattr(signal, "SIGKILL", signal.SIGTERM))


def make_request() -> ExecutionRequest:
    return ExecutionRequest(
        EXECUTION_ID,
        REQUEST_ID,
        PROPOSAL_ID,
        ("fake-command",),
        REQUESTED_AT,
        timeout_seconds=1.0,
    )


def test_executor_uses_injected_factory_clock_and_id() -> None:
    process = FakeProcess(b"output\n", b"warning\n")
    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def factory(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        calls.append((cast(tuple[str, ...], args[0]), kwargs))
        return cast(subprocess.Popen[bytes], process)

    executor = SubprocessExecutor(
        monotonic_clock=lambda: 10.0,
        time_provider=lambda: REQUESTED_AT,
        id_generator=lambda: RESULT_ID,
        popen_factory=cast(PopenFactory, factory),
    )

    result = executor.execute(make_request())

    assert result.result_id == RESULT_ID
    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.stdout == "output\n"
    assert result.stderr == "warning\n"
    assert calls[0][0] == ("fake-command",)
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["stdin"] == subprocess.DEVNULL
    assert calls[0][1]["env"] == {}


def test_timeout_does_not_force_signal_after_direct_child_is_reaped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = FakeProcess()
    signals: list[signal.Signals] = []

    def record_signal(_process: subprocess.Popen[bytes], signum: signal.Signals) -> None:
        signals.append(signum)

    monkeypatch.setattr(
        SubprocessExecutor,
        "_send_termination_signal",
        staticmethod(record_signal),
    )

    SubprocessExecutor()._terminate_after_timeout(cast(subprocess.Popen[bytes], process))

    assert signals == [signal.SIGTERM]
    assert process.wait_calls == [0]


def test_post_spawn_oserror_is_not_reported_as_start_failure() -> None:
    class WaitFailureProcess(FakeProcess):
        def wait(self, timeout: float | None = None) -> int:
            self.wait_calls.append(timeout)
            raise OSError("capture wait failed")

    process = WaitFailureProcess(b"output\n")

    def factory(*_args: object, **_kwargs: object) -> subprocess.Popen[bytes]:
        return cast(subprocess.Popen[bytes], process)

    executor = SubprocessExecutor(popen_factory=cast(PopenFactory, factory))

    with pytest.raises(OSError, match="capture wait failed"):
        executor.execute(make_request())


def test_capture_join_is_bounded_and_closes_stuck_streams() -> None:
    class BlockingStream:
        def __init__(self) -> None:
            self.closed = False
            self.released = threading.Event()

        def read(self, _size: int) -> bytes:
            self.released.wait()
            raise ValueError("stream closed")

        def close(self) -> None:
            self.closed = True
            self.released.set()

    process = FakeProcess()
    process.stdout = cast(IO[bytes], BlockingStream())
    process.stderr = cast(IO[bytes], BlockingStream())

    def factory(*_args: object, **_kwargs: object) -> subprocess.Popen[bytes]:
        return cast(subprocess.Popen[bytes], process)

    request = ExecutionRequest(
        EXECUTION_ID,
        REQUEST_ID,
        PROPOSAL_ID,
        ("fake-command",),
        REQUESTED_AT,
        timeout_seconds=0.01,
    )
    result = SubprocessExecutor(
        termination_grace_seconds=0.01,
        popen_factory=cast(PopenFactory, factory),
    ).execute(request)

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.stdout_truncated is True
    assert result.stderr_truncated is True

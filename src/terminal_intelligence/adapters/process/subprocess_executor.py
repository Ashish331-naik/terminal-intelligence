"""Deterministic direct-argv subprocess execution."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import IO
from uuid import UUID, uuid4

from terminal_intelligence.domain import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
)

_DEFAULT_MAX_OUTPUT_BYTES = 1024 * 1024
_READ_SIZE = 8192
_FORCE_KILL = getattr(signal, "SIGKILL", signal.SIGTERM)
PopenFactory = Callable[..., subprocess.Popen[bytes]]


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class _StreamCapture:
    stream: IO[bytes]
    data: bytearray = field(default_factory=bytearray)
    truncated: bool = False
    thread: threading.Thread | None = None


class SubprocessExecutor:
    """Execute argv directly without a shell and reap every spawned process."""

    def __init__(
        self,
        *,
        termination_grace_seconds: float = 0.2,
        max_output_bytes: int = _DEFAULT_MAX_OUTPUT_BYTES,
        monotonic_clock: Callable[[], float] = time.monotonic,
        time_provider: Callable[[], datetime] = _utc_now,
        id_generator: Callable[[], UUID] = uuid4,
        popen_factory: PopenFactory = subprocess.Popen,
    ) -> None:
        if termination_grace_seconds <= 0:
            raise ValueError("termination_grace_seconds must be positive")
        if max_output_bytes < 0:
            raise ValueError("max_output_bytes must be non-negative")
        self._termination_grace_seconds = termination_grace_seconds
        self._max_output_bytes = max_output_bytes
        self._monotonic_clock = monotonic_clock
        self._time_provider = time_provider
        self._id_generator = id_generator
        self._popen_factory = popen_factory

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute a request and return a structured result."""
        attempted_at = self._time_provider()
        started_clock = self._monotonic_clock()
        try:
            process = self._start_process(request)
        except (OSError, ValueError) as error:
            return self._result(
                request,
                status=ExecutionStatus.START_FAILED,
                attempted_at=None,
                started_clock=started_clock,
                stdout="",
                stderr="",
                error=f"{type(error).__name__}: {error}",
            )

        captures: tuple[_StreamCapture, _StreamCapture] | None = None
        try:
            captures = self._start_capture_threads(process)
            timed_out = self._wait_for_process(process, request.timeout_seconds)
            stdout, stderr, stdout_truncated, stderr_truncated = self._finish_capture(
                captures, request.timeout_seconds
            )
        except BaseException:
            self._cleanup_after_exception(process)
            if captures is not None:
                self._finish_capture(captures, request.timeout_seconds)
            raise

        return self._result(
            request,
            status=ExecutionStatus.TIMED_OUT if timed_out else self._status(process.returncode),
            attempted_at=attempted_at,
            started_clock=started_clock,
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            error="process exceeded its timeout" if timed_out else None,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
        )

    def _start_process(self, request: ExecutionRequest) -> subprocess.Popen[bytes]:
        if os.name == "posix":
            return self._popen_factory(
                request.argv,
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
                cwd=request.working_directory,
                env=dict(request.environment),
                start_new_session=True,
            )
        if os.name == "nt":
            return self._popen_factory(
                request.argv,
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
                cwd=request.working_directory,
                env=dict(request.environment),
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        return self._popen_factory(
            request.argv,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            cwd=request.working_directory,
            env=dict(request.environment),
        )

    def _start_capture_threads(
        self, process: subprocess.Popen[bytes]
    ) -> tuple[_StreamCapture, _StreamCapture]:
        if process.stdout is None or process.stderr is None:
            raise RuntimeError("subprocess pipes were not created")
        captures = (
            _StreamCapture(process.stdout),
            _StreamCapture(process.stderr),
        )
        for capture in captures:
            capture.thread = threading.Thread(
                target=self._read_stream,
                args=(capture,),
                daemon=True,
            )
            capture.thread.start()
        return captures

    def _read_stream(self, capture: _StreamCapture) -> None:
        try:
            while chunk := capture.stream.read(_READ_SIZE):
                remaining = self._max_output_bytes - len(capture.data)
                if remaining > 0:
                    capture.data.extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        capture.truncated = True
                else:
                    capture.truncated = True
        except (OSError, ValueError):
            capture.truncated = True
        finally:
            with suppress(OSError, ValueError):
                capture.stream.close()

    def _finish_capture(
        self,
        captures: tuple[_StreamCapture, _StreamCapture],
        join_timeout_seconds: float,
    ) -> tuple[str, str, bool, bool]:
        deadline = self._monotonic_clock() + min(
            self._termination_grace_seconds, join_timeout_seconds
        )
        for capture in captures:
            if capture.thread is not None:
                remaining = max(0.0, deadline - self._monotonic_clock())
                capture.thread.join(timeout=remaining)
        for capture in captures:
            if capture.thread is not None and capture.thread.is_alive():
                capture.truncated = True
                with suppress(OSError, ValueError):
                    capture.stream.close()
                capture.thread.join(timeout=0.01)
        stdout_capture, stderr_capture = captures
        stdout = bytes(stdout_capture.data).decode("utf-8", errors="replace")
        stderr = bytes(stderr_capture.data).decode("utf-8", errors="replace")
        return stdout, stderr, stdout_capture.truncated, stderr_capture.truncated

    def _wait_for_process(self, process: subprocess.Popen[bytes], timeout: float) -> bool:
        try:
            process.wait(timeout=timeout)
            return False
        except subprocess.TimeoutExpired:
            self._terminate_after_timeout(process)
            return True

    def _terminate_after_timeout(self, process: subprocess.Popen[bytes]) -> None:
        self._send_termination_signal(process, signal.SIGTERM)
        try:
            # Probe before reaping so a force signal is never sent to a PID
            # after the direct child has exited.
            process.wait(timeout=0)
        except subprocess.TimeoutExpired:
            self._send_termination_signal(process, _FORCE_KILL)
            process.wait()

    @staticmethod
    def _send_termination_signal(process: subprocess.Popen[bytes], signum: signal.Signals) -> None:
        try:
            if os.name == "posix":
                os.killpg(process.pid, signum)
            elif signum is signal.SIGTERM:
                process.terminate()
            else:
                process.kill()
        except ProcessLookupError:
            pass
        except OSError:
            if signum is signal.SIGTERM:
                with suppress(OSError):
                    process.terminate()
            else:
                with suppress(OSError):
                    process.kill()

    def _cleanup_after_exception(self, process: subprocess.Popen[bytes]) -> None:
        if process.poll() is None:
            self._send_termination_signal(process, _FORCE_KILL)
        with suppress(OSError):
            process.wait()

    @staticmethod
    def _status(return_code: int | None) -> ExecutionStatus:
        return ExecutionStatus.SUCCEEDED if return_code == 0 else ExecutionStatus.FAILED

    def _result(
        self,
        request: ExecutionRequest,
        *,
        status: ExecutionStatus,
        attempted_at: datetime | None,
        started_clock: float,
        stdout: str,
        stderr: str,
        error: str | None,
        exit_code: int | None = None,
        stdout_truncated: bool = False,
        stderr_truncated: bool = False,
    ) -> ExecutionResult:
        finished_at = self._time_provider()
        started_at = attempted_at
        if started_at is not None and finished_at < started_at:
            finished_at = started_at
        duration_ms = max(0, round((self._monotonic_clock() - started_clock) * 1000))
        return ExecutionResult(
            result_id=self._id_generator(),
            request_id=request.request_id,
            execution_request_id=request.execution_request_id,
            status=status,
            finished_at=finished_at,
            started_at=started_at,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            error=error,
            duration_ms=duration_ms,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
        )

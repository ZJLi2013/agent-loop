from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from harness.journal import write_artifact
from harness.storage import utc_now


def _kill_process_tree(proc: subprocess.Popen[Any]) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            proc.kill()
    else:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=5)


def execute_process(
    root: Path,
    argv: list[str],
    *,
    timeout_seconds: float,
    run_dir: Path,
    max_output_bytes: int,
    is_paused: Callable[[], bool],
) -> dict[str, Any]:
    started_at = utc_now()
    start = time.monotonic()
    timed_out = False
    pause_detected = False
    error: str | None = None
    exit_code: int | None = None

    with tempfile.TemporaryDirectory(prefix="agent-loop-harness-") as temp_dir:
        raw_stdout = Path(temp_dir) / "stdout"
        raw_stderr = Path(temp_dir) / "stderr"
        try:
            with raw_stdout.open("wb") as stdout_fh, raw_stderr.open(
                "wb"
            ) as stderr_fh:
                kwargs: dict[str, Any] = {
                    "cwd": root,
                    "stdout": stdout_fh,
                    "stderr": stderr_fh,
                    "stdin": subprocess.DEVNULL,
                }
                if os.name == "nt":
                    kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
                else:
                    kwargs["start_new_session"] = True
                proc = subprocess.Popen(argv, **kwargs)
                deadline = start + timeout_seconds
                while proc.poll() is None:
                    if is_paused():
                        pause_detected = True
                        _kill_process_tree(proc)
                        break
                    if time.monotonic() >= deadline:
                        timed_out = True
                        _kill_process_tree(proc)
                        break
                    time.sleep(0.1)
                exit_code = proc.returncode
        except OSError as exc:
            error = str(exc)
            raw_stdout.touch(exist_ok=True)
            raw_stderr.touch(exist_ok=True)

        duration = time.monotonic() - start
        stdout_hash, stdout_truncated = write_artifact(
            run_dir / "stdout.log", raw_stdout, max_output_bytes
        )
        stderr_hash, stderr_truncated = write_artifact(
            run_dir / "stderr.log", raw_stderr, max_output_bytes
        )

    pause_detected = pause_detected or is_paused()
    outcome = (
        "paused"
        if pause_detected
        else "timeout"
        if timed_out
        else "error"
        if error
        else "pass"
        if exit_code == 0
        else "fail"
    )
    return {
        "started_at": started_at,
        "finished_at": utc_now(),
        "duration_seconds": round(duration, 6),
        "timeout_seconds": timeout_seconds,
        "timed_out": timed_out,
        "paused": pause_detected,
        "exit_code": exit_code,
        "error": error,
        "outcome": outcome,
        "stdout_sha256": stdout_hash,
        "stderr_sha256": stderr_hash,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
    }

